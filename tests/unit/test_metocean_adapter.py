"""Unit tests for Met-Ocean Data Ingestion Adapter (TASK-017).

Verifies CMEMS GLO12 currents and ERA5 winds ingestion, coordinate normalization,
spatial-temporal subsetting, point & vectorized interpolation, NetCDF persistence,
and resilient synthetic fallback.
"""

from __future__ import annotations

import math
import shutil
import tempfile
import unittest
from datetime import UTC, datetime
from pathlib import Path

import numpy as np

from backend.services.data_adapters.metocean_adapter import (
    MetoceanAdapter,
    MetoceanDatasetMetadata,
    MetoceanQuery,
    MetoceanVelocityPoint,
    calculate_current_bearing,
    calculate_wind_direction_from,
    generate_synthetic_metocean_dataset,
    load_dataset_from_netcdf,
    sample_forcing,
    sample_forcing_vectorized,
    save_dataset_to_netcdf,
    subset_dataset,
)


class TestMetoceanAdapter(unittest.TestCase):
    """Test suite for MetoceanAdapter and hydrodynamic forcing functions."""

    def setUp(self) -> None:
        self.temp_dir = tempfile.mkdtemp()
        self.cache_dir = Path(self.temp_dir) / "metocean_cache"
        self.cache_dir.mkdir(parents=True, exist_ok=True)

        # Reference bounding box (Bombay High offshore region)
        self.bbox = (72.10, 18.70, 72.60, 19.10)
        self.time_start = datetime(2026, 9, 6, 6, 0, tzinfo=UTC)
        self.time_end = datetime(2026, 9, 7, 18, 0, tzinfo=UTC)

    def tearDown(self) -> None:
        shutil.rmtree(self.temp_dir, ignore_errors=True)

    def test_current_bearing_calculation(self) -> None:
        """Verify oceanographic current direction (degrees towards which flow travels)."""
        # Northward current (u=0, v>0) -> 0°
        self.assertAlmostEqual(calculate_current_bearing(0.0, 1.0), 0.0, places=3)

        # Eastward current (u>0, v=0) -> 90°
        self.assertAlmostEqual(calculate_current_bearing(1.0, 0.0), 90.0, places=3)

        # Southward current (u=0, v<0) -> 180°
        self.assertAlmostEqual(calculate_current_bearing(0.0, -1.0), 180.0, places=3)

        # Westward current (u<0, v=0) -> 270°
        self.assertAlmostEqual(calculate_current_bearing(-1.0, 0.0), 270.0, places=3)

        # Benchmark Bombay High synthetic current (u=0.28, v=0.12) -> ~66.8°
        bearing = calculate_current_bearing(0.28, 0.12)
        self.assertAlmostEqual(bearing, 66.8, places=1)

    def test_wind_direction_from_calculation(self) -> None:
        """Verify meteorological wind direction (degrees FROM which wind blows)."""
        # Wind blowing toward North (u=0, v>0), so FROM South -> 180°
        self.assertAlmostEqual(calculate_wind_direction_from(0.0, 1.0), 180.0, places=3)

        # Wind blowing toward East (u>0, v=0), so FROM West -> 270°
        self.assertAlmostEqual(calculate_wind_direction_from(1.0, 0.0), 270.0, places=3)

        # Wind blowing toward South (u=0, v<0), so FROM North -> 0°
        self.assertAlmostEqual(calculate_wind_direction_from(0.0, -1.0), 0.0, places=3)

        # Wind blowing toward West (u<0, v=0), so FROM East -> 90°
        self.assertAlmostEqual(calculate_wind_direction_from(-1.0, 0.0), 90.0, places=3)

        # Benchmark Bombay High synthetic wind (u10=6.5, v10=3.0) -> ~245.2°
        wind_dir = calculate_wind_direction_from(6.5, 3.0)
        self.assertAlmostEqual(wind_dir, 245.2, places=1)

    def test_synthetic_dataset_generation(self) -> None:
        """Verify synthetic met-ocean dataset dimensions, variables, and attributes."""
        ds = generate_synthetic_metocean_dataset(
            bbox=self.bbox,
            time_start=self.time_start,
            time_end=self.time_end,
            grid_res_deg=0.1,
            time_step_hours=1.0,
        )

        # Check required variables
        self.assertIn("uo", ds.data_vars)
        self.assertIn("vo", ds.data_vars)
        self.assertIn("u10", ds.data_vars)
        self.assertIn("v10", ds.data_vars)

        # Check required coordinates
        self.assertIn("time", ds.coords)
        self.assertIn("lat", ds.coords)
        self.assertIn("lon", ds.coords)

        # Check dimensions
        self.assertGreaterEqual(ds.sizes["time"], 24)  # 36 hours span
        self.assertGreater(ds.sizes["lat"], 2)
        self.assertGreater(ds.sizes["lon"], 2)

        # Rule 1: Confidence score present and bounded [0.0, 100.0]
        conf = float(ds.attrs.get("confidence_pct", -1.0))
        self.assertGreaterEqual(conf, 0.0)
        self.assertLessEqual(conf, 100.0)

        # Rule 4: Data source is explicitly tagged
        self.assertEqual(ds.attrs.get("data_source"), "synthetic")

        # Physical bounds check
        uo_vals = ds["uo"].values
        vo_vals = ds["vo"].values
        curr_speed = np.hypot(uo_vals, vo_vals)
        self.assertTrue(np.all(curr_speed >= 0.05))
        self.assertTrue(np.all(curr_speed <= 1.00))

        u10_vals = ds["u10"].values
        v10_vals = ds["v10"].values
        wind_speed = np.hypot(u10_vals, v10_vals)
        self.assertTrue(np.all(wind_speed >= 1.0))
        self.assertTrue(np.all(wind_speed <= 20.0))

    def test_subset_dataset(self) -> None:
        """Verify spatial-temporal subsetting with boundary buffer."""
        ds = generate_synthetic_metocean_dataset(
            bbox=(71.5, 18.0, 73.0, 20.0),
            time_start=datetime(2026, 9, 6, 0, 0, tzinfo=UTC),
            time_end=datetime(2026, 9, 8, 0, 0, tzinfo=UTC),
        )

        sub_bbox = (72.1, 18.7, 72.5, 19.0)
        t_sub_start = datetime(2026, 9, 6, 12, 0, tzinfo=UTC)
        t_sub_end = datetime(2026, 9, 7, 12, 0, tzinfo=UTC)

        subset = subset_dataset(
            ds,
            bbox=sub_bbox,
            time_start=t_sub_start,
            time_end=t_sub_end,
            buffer_deg=0.1,
        )

        self.assertGreater(subset.sizes["time"], 0)
        self.assertGreater(subset.sizes["lat"], 0)
        self.assertGreater(subset.sizes["lon"], 0)

        # Subset should be smaller than parent dataset
        self.assertLessEqual(subset.sizes["time"], ds.sizes["time"])
        self.assertLessEqual(subset.sizes["lat"], ds.sizes["lat"])
        self.assertLessEqual(subset.sizes["lon"], ds.sizes["lon"])

    def test_sample_forcing_point(self) -> None:
        """Verify continuous interpolation of forcing fields at arbitrary point and time."""
        ds = generate_synthetic_metocean_dataset(
            bbox=self.bbox,
            time_start=self.time_start,
            time_end=self.time_end,
        )

        query_lon = 72.35
        query_lat = 18.85
        query_time = datetime(2026, 9, 6, 15, 30, tzinfo=UTC)

        sample: MetoceanVelocityPoint = sample_forcing(ds, query_lon, query_lat, query_time)

        self.assertIsInstance(sample, MetoceanVelocityPoint)
        self.assertAlmostEqual(sample.lon, query_lon, places=2)
        self.assertAlmostEqual(sample.lat, query_lat, places=2)
        self.assertEqual(sample.timestamp, query_time)

        # Verify physics
        expected_curr_speed = math.hypot(sample.u_curr, sample.v_curr)
        self.assertAlmostEqual(sample.current_speed_mps, expected_curr_speed, places=3)

        expected_wind_speed = math.hypot(sample.u10, sample.v10)
        self.assertAlmostEqual(sample.wind_speed_mps, expected_wind_speed, places=3)

        # Rule 1: Confidence
        self.assertGreaterEqual(sample.confidence_pct, 0.0)
        self.assertLessEqual(sample.confidence_pct, 100.0)

        # Rule 4: Data source
        self.assertIn(sample.data_source, ["live", "cached", "synthetic"])

    def test_sample_forcing_vectorized(self) -> None:
        """Verify vectorized interpolation for N >= 1,000 particle positions."""
        ds = generate_synthetic_metocean_dataset(
            bbox=self.bbox,
            time_start=self.time_start,
            time_end=self.time_end,
        )

        n_particles = 1000
        lons = np.random.uniform(72.15, 72.55, n_particles)
        lats = np.random.uniform(18.75, 19.05, n_particles)
        t_query = datetime(2026, 9, 6, 12, 0, tzinfo=UTC)

        uo, vo, u10, v10 = sample_forcing_vectorized(ds, lons, lats, t_query)

        self.assertEqual(len(uo), n_particles)
        self.assertEqual(len(vo), n_particles)
        self.assertEqual(len(u10), n_particles)
        self.assertEqual(len(v10), n_particles)
        self.assertFalse(np.isnan(uo).any())
        self.assertFalse(np.isnan(u10).any())

    def test_netcdf_save_and_load_roundtrip(self) -> None:
        """Verify serialization to NetCDF4 and subsequent lossless loading."""
        ds_orig = generate_synthetic_metocean_dataset(
            bbox=self.bbox,
            time_start=self.time_start,
            time_end=self.time_end,
            confidence_pct=88.5,
        )

        nc_path = self.cache_dir / "test_roundtrip.nc"
        saved_path = save_dataset_to_netcdf(ds_orig, nc_path)
        self.assertTrue(saved_path.exists())

        ds_loaded = load_dataset_from_netcdf(saved_path)
        self.assertIn("uo", ds_loaded.data_vars)
        self.assertIn("v10", ds_loaded.data_vars)
        self.assertEqual(ds_loaded.sizes["lat"], ds_orig.sizes["lat"])
        self.assertEqual(ds_loaded.sizes["lon"], ds_orig.sizes["lon"])
        self.assertEqual(float(ds_loaded.attrs["confidence_pct"]), 88.5)

    def test_adapter_fallback_and_metadata(self) -> None:
        """Verify MetoceanAdapter synthetic fallback cascade and metadata generation."""
        adapter = MetoceanAdapter(cache_dir=self.cache_dir)
        query = MetoceanQuery(
            bbox=self.bbox,
            time_start=self.time_start,
            time_end=self.time_end,
        )

        # 1. Fetch forcing field without credentials -> triggers synthetic generation & caches it
        ds = adapter.fetch_forcing_field(query, force_synthetic=False, cache_synthetic=True)
        self.assertEqual(ds.attrs.get("data_source"), "synthetic")

        # Verify a cached file was written
        cached_files = list(self.cache_dir.glob("*.nc"))
        self.assertGreaterEqual(len(cached_files), 1)

        # 2. Query again within bounds -> hits cache
        cached_ds = adapter.fetch_forcing_field(query, force_synthetic=False)
        self.assertEqual(cached_ds.attrs.get("data_source"), "cached")

        # 3. Metadata inspection
        metadata: MetoceanDatasetMetadata = adapter.get_metadata(cached_ds)
        self.assertIsInstance(metadata, MetoceanDatasetMetadata)
        self.assertGreaterEqual(metadata.confidence_pct, 0.0)
        self.assertLessEqual(metadata.confidence_pct, 100.0)
        self.assertIn(metadata.data_source, ["cached", "synthetic"])
        self.assertGreater(metadata.n_time_steps, 0)
        self.assertGreater(metadata.n_lats, 0)
        self.assertGreater(metadata.n_lons, 0)


if __name__ == "__main__":
    unittest.main()
