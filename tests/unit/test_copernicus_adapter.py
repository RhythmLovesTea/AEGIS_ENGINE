"""Unit tests verifying TASK-009 Copernicus SAR/EO Ingestion Adapter."""

import unittest
from datetime import datetime, timedelta, timezone
from pathlib import Path

import numpy as np

from backend.services.data_adapters.copernicus_adapter import (
    CopernicusAdapter,
    EOProductQuery,
    PreprocessedTile,
)


class TestCopernicusAdapter(unittest.TestCase):
    def setUp(self) -> None:
        self.adapter = CopernicusAdapter()
        self.now = datetime.now(timezone.utc)
        self.sample_query = EOProductQuery(
            bbox=(72.10, 18.70, 72.60, 19.10),
            start_time=self.now - timedelta(hours=12),
            end_time=self.now,
            satellite="Sentinel-1",
            polarization=["VV", "VH"],
        )

    def test_query_scenes_synthetic_fallback(self) -> None:
        """Verify query_scenes falls back gracefully to synthetic scene catalog."""
        results = self.adapter.query_scenes(self.sample_query)
        self.assertIsInstance(results, list)
        self.assertGreater(len(results), 0)
        self.assertEqual(results[0]["data_source"], "synthetic")
        self.assertIn("GeoFootprint", results[0])

    def test_calibrate_radiometric(self) -> None:
        """Verify conversion from Digital Numbers to sigma0 dB."""
        dn = np.array([[100.0, 200.0], [300.0, 500.0]], dtype=np.float32)
        sigma0 = CopernicusAdapter.calibrate_radiometric(dn, calibration_constant=300.0)

        # For DN=300 and A=300: sigma0 = 10*log10(1) = 0.0 dB
        self.assertAlmostEqual(sigma0[1, 0], 0.0, places=1)
        # Bounded between -35 dB and 0 dB
        self.assertTrue(np.all(sigma0 >= -35.0))
        self.assertTrue(np.all(sigma0 <= 0.0))

    def test_apply_lee_filter(self) -> None:
        """Verify 5x5 Lee adaptive speckle filter smooths speckle noise."""
        np.random.seed(42)
        # Create noisy synthetic image with a clear step edge
        base = np.zeros((64, 64), dtype=np.float32)
        base[:, 32:] = -10.0  # Background sea vs dark slick
        noise = np.random.normal(0.0, 2.0, size=(64, 64)).astype(np.float32)
        noisy = base + noise

        filtered = CopernicusAdapter.apply_lee_filter(noisy, window_size=5)
        self.assertEqual(filtered.shape, noisy.shape)
        # Variance of filtered image should be strictly lower than noisy image
        self.assertLess(np.var(filtered), np.var(noisy))

    def test_tile_swath_geometry(self) -> None:
        """Verify 1024x1024 image is tiled into 512x512 patches with 20% overlap."""
        image = np.ones((1024, 1024), dtype=np.float32)
        tiles = CopernicusAdapter.tile_swath(image, tile_size=512, overlap=0.20)

        self.assertGreater(len(tiles), 0)
        for tile_data, r_off, c_off in tiles:
            self.assertEqual(tile_data.shape, (512, 512))
            self.assertGreaterEqual(r_off, 0)
            self.assertGreaterEqual(c_off, 0)

    def test_load_and_preprocess_pipeline(self) -> None:
        """Verify full load_and_preprocess pipeline produces valid PreprocessedTile items."""
        tiles, metadata = self.adapter.load_and_preprocess(
            scene_ref="S1A_IW_GRDH_TEST_2026",
            swath_shape=(1024, 1024),
        )

        self.assertEqual(metadata["scene_ref"], "S1A_IW_GRDH_TEST_2026")
        self.assertEqual(metadata["data_source"], "synthetic")
        self.assertGreater(len(tiles), 0)

        first_tile = tiles[0]
        self.assertIsInstance(first_tile, PreprocessedTile)
        self.assertEqual(first_tile.data.shape, (1, 512, 512))
        self.assertEqual(first_tile.data_source, "synthetic")
        self.assertEqual(first_tile.sensor, "Sentinel-1 SAR IW GRD")

    def test_load_from_local_geotiff(self) -> None:
        """Verify loading and preprocessing from a local GeoTIFF file with rasterio."""
        local_tif = Path(__file__).resolve().parents[2] / "data" / "sar" / "sample_s1_iw_grd.tif"
        if local_tif.exists():
            tiles, metadata = self.adapter.load_and_preprocess(
                scene_ref="S1A_IW_GRDH_LOCAL_SAMPLE",
                local_file=local_tif,
            )
            self.assertEqual(metadata["data_source"], "cached")
            self.assertGreater(len(tiles), 0)
            self.assertEqual(tiles[0].data.shape, (1, 512, 512))


if __name__ == "__main__":
    unittest.main()

