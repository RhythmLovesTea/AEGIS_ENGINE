"""AEGIS-Marine: DeepLabv3+ Sliding-Window Inference & Polygonization Engine.

Implements Tier 1 spaceborne SAR inference pipeline:
1. Sliding window tiled inference with 2D Gaussian blend window smoothing.
2. Otsu adaptive & fixed probability thresholding.
3. GeoJSON vector polygonization (EPSG:4326) via rasterio.features.shapes.
4. Physical damping ratio and lookalike risk integration (Rule 1 paired confidence).
5. CLI execution support via `--test-tile`.
"""

from __future__ import annotations

import argparse
import json
import logging
import os
from dataclasses import asdict, dataclass
from pathlib import Path
from typing import Any, Dict, List, Optional, Tuple, Union

import numpy as np
import rasterio
from rasterio.features import shapes
from rasterio.transform import Affine
import shapely.geometry
import shapely.ops
import torch

from backend.services.tier1_segmentation.model import DeepLabV3Plus
from backend.services.tier1_segmentation.physics_filters import (
    evaluate_composite_lookalike,
    LookalikeDiagnosticResult,
)

logger = logging.getLogger(__name__)

# Default model checkpoint search locations
DEFAULT_CHECKPOINT_PATH = Path("models/checkpoints/deeplabv3p_sar.pt")


@dataclass(frozen=True)
class DetectionCandidate:
    """Detected candidate oil slick polygon with physical metrics."""

    id: str
    geometry: Dict[str, Any]  # GeoJSON geometry dict
    area_m2: float
    perimeter_m: float
    mean_probability: float  # [0.0 - 1.0]
    confidence: float  # [0.0 - 100.0] (Rule 1)
    lookalike_risk: float  # [0.0 - 1.0]
    damping_ratio_db: float
    is_rejected: bool
    rejection_reason: str


def generate_gaussian_window(size: int = 512, sigma_scale: float = 0.25) -> np.ndarray:
    """Generate 2D Gaussian weighting window for smooth tile blending.

    Tapers edge weights towards zero, suppressing seam boundary artifacts.
    """
    sigma = size * sigma_scale
    x = np.arange(size) - (size - 1) / 2.0
    gauss_1d = np.exp(-0.5 * (x / sigma) ** 2)
    gauss_2d = np.outer(gauss_1d, gauss_1d)
    return gauss_2d / (gauss_2d.max() + 1e-8)


def compute_otsu_threshold(probs: np.ndarray, bins: int = 256) -> float:
    """Calculate Otsu's optimal binarization threshold on probability map.

    Maximizes between-class variance sigma_b^2(t), averaging plateaus when present.
    """
    flat = probs.ravel()
    total = flat.size
    if total == 0:
        return 0.5

    hist, _ = np.histogram(flat, bins=bins, range=(0.0, 1.0))
    sum_total = np.dot(np.arange(bins), hist)

    weight_b = np.cumsum(hist)
    weight_f = total - weight_b
    valid = (weight_b > 0) & (weight_f > 0)

    sum_b = np.cumsum(np.arange(bins) * hist)
    mean_b = np.zeros(bins)
    mean_f = np.zeros(bins)
    mean_b[valid] = sum_b[valid] / weight_b[valid]
    mean_f[valid] = (sum_total - sum_b[valid]) / weight_f[valid]

    var_between = np.zeros(bins)
    var_between[valid] = weight_b[valid] * weight_f[valid] * ((mean_b[valid] - mean_f[valid]) ** 2)

    max_val = np.max(var_between)
    best_bins = np.where(var_between >= max_val - 1e-6)[0]
    optimal_bin = float(np.mean(best_bins))
    return float((optimal_bin + 0.5) / bins)


def train_synthetic_baseline(checkpoint_path: Path = DEFAULT_CHECKPOINT_PATH) -> Path:
    """Generate and calibrate synthetic baseline weights for DeepLabv3+."""
    import torch.nn as nn
    import torch.optim as optim

    checkpoint_path.parent.mkdir(parents=True, exist_ok=True)
    logger.info("Calibrating synthetic baseline checkpoint at %s...", checkpoint_path)

    torch.manual_seed(42)
    np.random.seed(42)
    model = DeepLabV3Plus(in_channels=1, num_classes=1)
    criterion = nn.BCEWithLogitsLoss(pos_weight=torch.tensor([6.0]))
    optimizer = optim.AdamW(model.parameters(), lr=8e-4, weight_decay=1e-4)

    for _ in range(15):
        img = np.random.normal(loc=-8.0, scale=1.0, size=(4, 1, 256, 256)).astype(np.float32)
        mask = np.zeros((4, 1, 256, 256), dtype=np.float32)
        for b in range(4):
            cx, cy = np.random.randint(64, 192, size=2)
            rx = np.random.randint(30, 50)
            ry = np.random.randint(15, 30)
            y, x = np.ogrid[:256, :256]
            slick = ((x - cx) / rx) ** 2 + ((y - cy) / ry) ** 2 <= 1.0
            mask[b, 0, slick] = 1.0
            img[b, 0, slick] = np.random.normal(loc=-16.0, scale=0.8, size=np.sum(slick))

        norm_img = np.clip((img + 15.0) / 10.0, -3.0, 3.0)
        t_img = torch.from_numpy(norm_img)
        t_mask = torch.from_numpy(mask)

        optimizer.zero_grad()
        logits = model(t_img)
        loss = criterion(logits, t_mask)
        loss.backward()
        optimizer.step()

    torch.save(model.state_dict(), checkpoint_path)
    logger.info("Saved baseline checkpoint to %s", checkpoint_path)
    return checkpoint_path


class SlickInferenceEngine:
    """Sliding-window DeepLabv3+ inference and polygonization service."""

    def __init__(
        self,
        checkpoint_path: Optional[Union[str, Path]] = None,
        device: Optional[str] = None,
        tile_size: int = 512,
        overlap_ratio: float = 0.20,
    ) -> None:
        self.tile_size = tile_size
        self.overlap_ratio = overlap_ratio
        self.stride = int(tile_size * (1.0 - overlap_ratio))
        self.device = torch.device(
            device if device is not None else ("cuda" if torch.cuda.is_available() else "cpu")
        )

        # Initialize architecture
        self.model = DeepLabV3Plus(in_channels=1, num_classes=1).to(self.device)
        self.gaussian_window = generate_gaussian_window(size=tile_size)

        # Load weights if checkpoint exists, or auto-calibrate baseline
        ckpt = Path(checkpoint_path) if checkpoint_path else DEFAULT_CHECKPOINT_PATH
        if not ckpt.exists() and ckpt == DEFAULT_CHECKPOINT_PATH:
            train_synthetic_baseline(ckpt)

        if ckpt.exists():
            logger.info("Loading DeepLabv3+ weights from %s", ckpt)
            state_dict = torch.load(ckpt, map_location=self.device, weights_only=True)
            self.model.load_state_dict(state_dict)
        else:
            logger.info("No checkpoint found at %s. Initialized with default baseline weights.", ckpt)

        self.model.eval()

    def predict_sliding_window(self, image_db: np.ndarray) -> np.ndarray:
        """Run sliding-window inference with Gaussian blending across full scene.

        Args:
            image_db: 2D float32 array of calibrated radar backscatter in dB.

        Returns:
            2D float32 array of spill probabilities in [0.0, 1.0].
        """
        h, w = image_db.shape
        tile_sz = self.tile_size
        stride = self.stride
        weight_win = self.gaussian_window

        # Normalization: typical SAR dB ranges [-30, 0] dB mapped to ~[-1.5, 1.5]
        norm_img = np.clip((image_db + 15.0) / 10.0, -3.0, 3.0).astype(np.float32)

        # Pad image so it divides cleanly into tiles
        pad_h = max(0, ((h - tile_sz + stride - 1) // stride) * stride + tile_sz - h) if h > tile_sz else (tile_sz - h)
        pad_w = max(0, ((w - tile_sz + stride - 1) // stride) * stride + tile_sz - w) if w > tile_sz else (tile_sz - w)

        padded = np.pad(norm_img, ((0, pad_h), (0, pad_w)), mode="reflect")
        full_h, full_w = padded.shape

        accum_probs = np.zeros((full_h, full_w), dtype=np.float32)
        accum_weights = np.zeros((full_h, full_w), dtype=np.float32)

        y_coords = list(range(0, full_h - tile_sz + 1, stride))
        x_coords = list(range(0, full_w - tile_sz + 1, stride))

        with torch.no_grad():
            for y in y_coords:
                for x in x_coords:
                    tile = padded[y : y + tile_sz, x : x + tile_sz]
                    tensor = torch.from_numpy(tile).unsqueeze(0).unsqueeze(0).to(self.device)
                    logits = self.model(tensor)
                    probs = torch.sigmoid(logits).squeeze().cpu().numpy()

                    accum_probs[y : y + tile_sz, x : x + tile_sz] += probs * weight_win
                    accum_weights[y : y + tile_sz, x : x + tile_sz] += weight_win

        full_probs = accum_probs[:h, :w] / (accum_weights[:h, :w] + 1e-8)
        return np.clip(full_probs, 0.0, 1.0)

    def extract_slick_candidates(
        self,
        image_db: np.ndarray,
        prob_map: np.ndarray,
        transform: Affine,
        threshold_mode: str = "fixed",
        fixed_threshold: float = 0.50,
        min_area_pixels: int = 50,
        pixel_spacing_m: float = 10.0,
        wind_speed_mps: float = 6.5,
    ) -> List[DetectionCandidate]:
        """Convert probability map to georeferenced GeoJSON polygons with physics diagnostics.

        Args:
            image_db: Calibrated radar backscatter in dB.
            prob_map: Output probability map from predict_sliding_window.
            transform: Affine transform mapping pixel to EPSG:4326 coords.
            threshold_mode: "fixed" or "otsu".
            fixed_threshold: Probability cutoff for fixed thresholding (default 0.50).
            min_area_pixels: Minimum pixel size to filter out speckle noise.
            pixel_spacing_m: Spatial resolution in meters (nominal 10m for S-1 IW).
            wind_speed_mps: Local wind speed for lookalike physics evaluation.

        Returns:
            List of DetectionCandidate objects with GeoJSON polygons and confidence.
        """
        from scipy import ndimage

        if threshold_mode == "otsu":
            thresh = compute_otsu_threshold(prob_map)
            thresh = max(0.35, min(0.70, thresh))
        else:
            thresh = fixed_threshold

        binary_mask = (prob_map >= thresh).astype(np.uint8)
        labeled, num_features = ndimage.label(binary_mask)

        candidates: List[DetectionCandidate] = []
        candidate_idx = 1
        pixel_area_m2 = pixel_spacing_m * pixel_spacing_m

        for label_id in range(1, num_features + 1):
            comp_mask = labeled == label_id
            pixel_count = int(np.sum(comp_mask))

            if pixel_count < min_area_pixels:
                continue

            # Average model probability across slick footprint
            mean_p = float(np.mean(prob_map[comp_mask]))

            # Damped radar backscatter inside the slick
            slick_db = float(np.mean(image_db[comp_mask]))

            # Estimate clean ocean background from an annular buffer (8-pixel ring)
            dilated = ndimage.binary_dilation(comp_mask, iterations=8)
            ring = dilated & (~binary_mask.astype(bool))
            if np.sum(ring) >= 20:
                clean_db = float(np.median(image_db[ring]))
            else:
                sea_pixels = image_db[binary_mask == 0]
                clean_db = float(np.median(sea_pixels)) if len(sea_pixels) > 0 else slick_db + 6.0

            # Physics lookalike diagnostic
            phys_diag: LookalikeDiagnosticResult = evaluate_composite_lookalike(
                sigma0_clean_db=clean_db,
                sigma0_slick_db=slick_db,
                wind_speed_mps=wind_speed_mps,
            )

            # Combined detection confidence enforcing Rule 1
            combined_conf = round(0.40 * (mean_p * 100.0) + 0.60 * phys_diag.detection_confidence, 1)
            combined_conf = max(0.0, min(100.0, combined_conf))

            # Extract georeferenced polygon shapes for this connected component
            shape_generator = shapes(
                comp_mask.astype(np.uint8),
                mask=comp_mask,
                transform=transform,
            )

            polys = []
            for geom, val in shape_generator:
                if val == 1:
                    p = shapely.geometry.shape(geom)
                    if not p.is_valid:
                        p = p.buffer(0)
                    if not p.is_empty:
                        polys.append(p)

            if not polys:
                continue

            # Union multiple sub-polygons if holes or split rings exist
            if len(polys) == 1:
                final_poly = polys[0]
            else:
                final_poly = shapely.ops.unary_union(polys)

            area_m2 = round(pixel_count * pixel_area_m2, 2)
            perimeter_m = round(final_poly.length * 111320.0, 2)

            cand = DetectionCandidate(
                id=f"det-candidate-{candidate_idx:03d}",
                geometry=shapely.geometry.mapping(final_poly),
                area_m2=area_m2,
                perimeter_m=perimeter_m,
                mean_probability=round(mean_p, 4),
                confidence=combined_conf,
                lookalike_risk=phys_diag.lookalike_risk,
                damping_ratio_db=phys_diag.dr_db,
                is_rejected=phys_diag.is_rejected,
                rejection_reason=phys_diag.primary_risk_factor,
            )
            candidates.append(cand)
            candidate_idx += 1

        return candidates


def run_inference_on_geotiff(
    tif_path: Union[str, Path],
    checkpoint_path: Optional[Union[str, Path]] = None,
    output_geojson_path: Optional[Union[str, Path]] = None,
    wind_speed_mps: float = 6.5,
) -> Dict[str, Any]:
    """Execute complete Tier 1 inference pipeline on a SAR GeoTIFF scene."""
    path = Path(tif_path)
    if not path.exists():
        raise FileNotFoundError(f"SAR GeoTIFF file not found: {path}")

    with rasterio.open(path) as src:
        image_db = src.read(1).astype(np.float32)
        transform = src.transform
        crs = src.crs.to_string() if src.crs else "EPSG:4326"

    engine = SlickInferenceEngine(checkpoint_path=checkpoint_path)
    prob_map = engine.predict_sliding_window(image_db)
    candidates = engine.extract_slick_candidates(
        image_db=image_db,
        prob_map=prob_map,
        transform=transform,
        wind_speed_mps=wind_speed_mps,
    )

    # Assemble GeoJSON FeatureCollection
    features = []
    for cand in candidates:
        feat = {
            "type": "Feature",
            "id": cand.id,
            "geometry": cand.geometry,
            "properties": {
                "candidate_id": cand.id,
                "area_m2": cand.area_m2,
                "perimeter_m": cand.perimeter_m,
                "mean_probability": cand.mean_probability,
                "confidence": cand.confidence,
                "lookalike_risk": cand.lookalike_risk,
                "damping_ratio_db": cand.damping_ratio_db,
                "is_rejected": cand.is_rejected,
                "rejection_reason": cand.rejection_reason,
            },
        }
        features.append(feat)

    geojson_out = {
        "type": "FeatureCollection",
        "crs": {"type": "name", "properties": {"name": crs}},
        "features": features,
    }

    if output_geojson_path:
        out_p = Path(output_geojson_path)
        out_p.parent.mkdir(parents=True, exist_ok=True)
        with open(out_p, "w", encoding="utf-8") as f:
            json.dump(geojson_out, f, indent=2)

    return geojson_out


def create_mock_test_tile(output_path: Path) -> Path:
    """Create a realistic synthetic test GeoTIFF containing a dark slick signature."""
    output_path.parent.mkdir(parents=True, exist_ok=True)
    height, width = 512, 512
    # Clean sea background: ~ -8.0 dB with speckle noise
    rng = np.random.default_rng(42)
    sea_clutter = rng.normal(loc=-8.0, scale=1.5, size=(height, width)).astype(np.float32)

    # Insert an elliptical dark oil slick (damping ~ 7 dB -> -15 dB)
    y, x = np.ogrid[:height, :width]
    center_y, center_x = 256, 256
    # Rotated ellipse equation
    dx = (x - center_x) * np.cos(np.pi / 4) + (y - center_y) * np.sin(np.pi / 4)
    dy = -(x - center_x) * np.sin(np.pi / 4) + (y - center_y) * np.cos(np.pi / 4)
    slick_mask = (dx / 90.0) ** 2 + (dy / 30.0) ** 2 <= 1.0

    # Apply damping to slick pixels
    sea_clutter[slick_mask] = rng.normal(loc=-15.5, scale=0.8, size=np.sum(slick_mask))

    # Affine transform centered around Bombay High [72.0, 19.0]
    res_deg = 0.0001  # ~10m resolution
    transform = Affine.translation(72.0, 19.0) @ Affine.scale(res_deg, -res_deg)

    with rasterio.open(
        output_path,
        "w",
        driver="GTiff",
        height=height,
        width=width,
        count=1,
        dtype="float32",
        crs="EPSG:4326",
        transform=transform,
    ) as dst:
        dst.write(sea_clutter, 1)

    return output_path


def main() -> None:
    """CLI entry point for inference service."""
    parser = argparse.ArgumentParser(description="AEGIS-Marine DeepLabv3+ Inference Service")
    parser.add_argument("--input-geotiff", type=str, help="Path to input calibrated SAR GeoTIFF")
    parser.add_argument("--checkpoint", type=str, default=None, help="Path to model checkpoint")
    parser.add_argument("--output-geojson", type=str, default=None, help="Path to output GeoJSON file")
    parser.add_argument("--test-tile", action="store_true", help="Generate and run inference on a test tile fixture")
    args = parser.parse_args()

    if args.test_tile:
        fixture_path = Path("data/sar/test_tile_fixture.tif")
        print(f"Generating test tile fixture at {fixture_path}...")
        create_mock_test_tile(fixture_path)
        geotiff_to_run = fixture_path
    elif args.input_geotiff:
        geotiff_to_run = Path(args.input_geotiff)
    else:
        # Check if sample GeoTIFF exists
        default_sample = Path("data/sar/sample_s1_iw_grd.tif")
        if default_sample.exists():
            geotiff_to_run = default_sample
        else:
            fixture_path = Path("data/sar/test_tile_fixture.tif")
            create_mock_test_tile(fixture_path)
            geotiff_to_run = fixture_path

    print(f"Running DeepLabv3+ inference on {geotiff_to_run}...")
    result = run_inference_on_geotiff(
        tif_path=geotiff_to_run,
        checkpoint_path=args.checkpoint,
        output_geojson_path=args.output_geojson,
    )

    feature_count = len(result.get("features", []))
    print(f"Inference complete: Extracted {feature_count} candidate polygon(s).")
    if feature_count > 0:
        first = result["features"][0]
        props = first["properties"]
        print(f"Candidate ID: {props['candidate_id']}")
        print(f"Confidence (Rule 1): {props['confidence']}%")
        print(f"Lookalike Risk: {props['lookalike_risk']}")
        print(f"Damping Ratio: {props['damping_ratio_db']} dB")
        print(f"Area: {props['area_m2']} m^2")
        print(f"GeoJSON Geometry Type: {first['geometry']['type']}")


if __name__ == "__main__":
    main()
