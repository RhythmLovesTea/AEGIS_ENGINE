"""Unit tests for DeepLabv3+ segmentation model and sliding-window inference engine (TASK-011)."""

import json
import tempfile
import unittest
from pathlib import Path

import numpy as np
import rasterio
from rasterio.transform import Affine
import shapely.geometry
import torch

from backend.services.tier1_segmentation.inference import (
    DEFAULT_CHECKPOINT_PATH,
    DetectionCandidate,
    SlickInferenceEngine,
    compute_otsu_threshold,
    create_mock_test_tile,
    generate_gaussian_window,
    run_inference_on_geotiff,
)
from backend.services.tier1_segmentation.model import (
    ASPP,
    BinaryFocalLoss,
    BinaryLovaszLoss,
    CompoundLoss,
    DeepLabV3Plus,
)


class TestDeepLabV3PlusModel(unittest.TestCase):
    """Test suite for DeepLabv3+ model architecture and compound loss functions."""

    def test_aspp_module(self):
        """Test ASPP multi-dilation rates (6, 12, 18) and output dimension."""
        aspp = ASPP(in_channels=512, out_channels=256, atrous_rates=(6, 12, 18))
        x = torch.randn(2, 512, 32, 32)
        out = aspp(x)
        self.assertEqual(out.shape, (2, 256, 32, 32))

    def test_model_forward_pass_single_channel(self):
        """Test DeepLabv3+ forward pass on single-channel SAR input (VV)."""
        model = DeepLabV3Plus(in_channels=1, num_classes=1)
        model.eval()
        x = torch.randn(2, 1, 128, 128)
        with torch.no_grad():
            logits = model(x)
        self.assertEqual(logits.shape, (2, 1, 128, 128))

    def test_model_forward_pass_dual_channel(self):
        """Test DeepLabv3+ forward pass on dual-pol SAR input (VV + VH)."""
        model = DeepLabV3Plus(in_channels=2, num_classes=1)
        model.eval()
        x = torch.randn(1, 2, 128, 128)
        with torch.no_grad():
            logits = model(x)
        self.assertEqual(logits.shape, (1, 1, 128, 128))

    def test_compound_loss(self):
        """Test compound loss combining Focal Loss and Lovasz-Hinge Loss."""
        criterion = CompoundLoss(lambda_focal=1.0, lambda_lovasz=1.0)
        logits = torch.randn(2, 1, 64, 64)
        targets = (torch.rand(2, 1, 64, 64) > 0.7).float()

        loss_dict = criterion(logits, targets)
        self.assertIn("total_loss", loss_dict)
        self.assertIn("focal_loss", loss_dict)
        self.assertIn("lovasz_loss", loss_dict)
        self.assertGreater(loss_dict["total_loss"].item(), 0.0)
        self.assertGreater(loss_dict["focal_loss"].item(), 0.0)
        self.assertGreater(loss_dict["lovasz_loss"].item(), 0.0)


class TestInferenceEngine(unittest.TestCase):
    """Test suite for sliding window inference and polygonization."""

    def test_gaussian_window(self):
        """Test 2D Gaussian blend window generation."""
        window = generate_gaussian_window(size=512)
        self.assertEqual(window.shape, (512, 512))
        # Center peak should be ~1.0
        self.assertAlmostEqual(float(window[256, 256]), 1.0, places=2)
        # Corners should taper near 0.0
        self.assertLess(float(window[0, 0]), 0.05)
        self.assertLess(float(window[511, 511]), 0.05)

    def test_otsu_threshold(self):
        """Test Otsu adaptive threshold calculation on bimodal probability distribution."""
        probs = np.concatenate([
            np.random.normal(0.1, 0.05, 5000),
            np.random.normal(0.9, 0.05, 5000),
        ])
        probs = np.clip(probs, 0.0, 1.0)
        threshold = compute_otsu_threshold(probs)
        # Threshold should separate 0.1 and 0.9 modes (~0.4 - 0.6)
        self.assertGreaterEqual(threshold, 0.35)
        self.assertLessEqual(threshold, 0.65)

    def test_sliding_window_prediction_shape(self):
        """Test full scene sliding window tiled prediction."""
        engine = SlickInferenceEngine()
        scene = np.random.normal(-8.0, 2.0, (600, 600)).astype(np.float32)
        probs = engine.predict_sliding_window(scene)
        self.assertEqual(probs.shape, (600, 600))
        self.assertGreaterEqual(float(probs.min()), 0.0)
        self.assertLessEqual(float(probs.max()), 1.0)

    def test_candidate_extraction_and_rule1_compliance(self):
        """Test candidate polygon extraction, damping ratio, and Rule 1 confidence."""
        engine = SlickInferenceEngine()
        image_db = np.full((256, 256), -8.0, dtype=np.float32)
        prob_map = np.full((256, 256), 0.1, dtype=np.float32)

        # Create a synthetic slick blob in center: -16 dB, high prob 0.95
        y, x = np.ogrid[:256, :256]
        slick_mask = (x - 128) ** 2 + (y - 128) ** 2 <= 400  # radius 20
        image_db[slick_mask] = -16.0
        prob_map[slick_mask] = 0.95

        transform = Affine.translation(72.0, 19.0) @ Affine.scale(0.0001, -0.0001)
        candidates = engine.extract_slick_candidates(
            image_db=image_db,
            prob_map=prob_map,
            transform=transform,
            fixed_threshold=0.50,
            min_area_pixels=30,
            wind_speed_mps=6.5,
        )

        self.assertGreaterEqual(len(candidates), 1)
        cand = candidates[0]

        # Verify GeoJSON polygon validity
        poly = shapely.geometry.shape(cand.geometry)
        self.assertTrue(poly.is_valid)
        self.assertFalse(poly.is_empty)

        # Verify Rule 1: Paired confidence score exists and is bounded [0, 100]
        self.assertGreaterEqual(cand.confidence, 0.0)
        self.assertLessEqual(cand.confidence, 100.0)
        self.assertGreater(cand.confidence, 60.0)  # High confidence genuine slick

        # Verify physical metrics
        self.assertGreaterEqual(cand.damping_ratio_db, 4.5)  # Nominal threshold
        self.assertFalse(cand.is_rejected)
        self.assertEqual(cand.rejection_reason, "none")
        self.assertEqual(cand.lookalike_risk, 0.0)

    def test_end_to_end_geotiff_inference(self):
        """Test end-to-end inference on GeoTIFF fixture producing GeoJSON output."""
        with tempfile.TemporaryDirectory() as tmpdir:
            tif_path = Path(tmpdir) / "synthetic_tile.tif"
            geojson_path = Path(tmpdir) / "output.geojson"

            create_mock_test_tile(tif_path)
            self.assertTrue(tif_path.exists())

            result = run_inference_on_geotiff(
                tif_path=tif_path,
                output_geojson_path=geojson_path,
                wind_speed_mps=6.5,
            )

            self.assertEqual(result["type"], "FeatureCollection")
            self.assertIn("features", result)
            self.assertTrue(geojson_path.exists())

            # Read back saved GeoJSON
            with open(geojson_path, "r", encoding="utf-8") as f:
                saved_json = json.load(f)

            self.assertEqual(saved_json["type"], "FeatureCollection")
            if saved_json["features"]:
                first_feat = saved_json["features"][0]
                props = first_feat["properties"]
                self.assertIn("confidence", props)
                self.assertIn("lookalike_risk", props)
                self.assertIn("damping_ratio_db", props)
                self.assertIn("area_m2", props)


if __name__ == "__main__":
    unittest.main()
