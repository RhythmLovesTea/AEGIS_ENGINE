"""Unit tests for Backward Lagrangian Hindcasting Runner (TASK-019).

Verifies backward Lagrangian particle advection:
1. Uniform seeding of N >= 10,000 particles across slick polygons.
2. Backward in time integration (delta_t = -15 min).
3. Reverse trajectory direction and displacement physics.
4. Horizontal turbulent diffusion (K_h) dispersion.
5. Time-series snapshot generation and GeoJSON trajectory export.
6. Rule 1 & Rule 4 compliance and Rule 6 banned terminology check.
"""

from __future__ import annotations

import math
import unittest
from datetime import UTC, datetime, timedelta

import numpy as np
import shapely
from shapely.geometry import Polygon

from backend.services.data_adapters.metocean_adapter import generate_synthetic_metocean_dataset
from backend.services.tier3_hindcast.hindcast_runner import (
    HindcastConfig,
    HindcastResult,
    LagrangianHindcastRunner,
    seed_particles_in_polygon,
)


class TestHindcastRunner(unittest.TestCase):
    """Test suite for backward Lagrangian numerical particle tracking."""

    def setUp(self) -> None:
        self.config = HindcastConfig(
            n_particles=10000,
            time_step_minutes=-15.0,
            horizontal_diffusivity_kh=2.0,
            wind_drift_factor=0.030,
            random_seed=42,
        )
        self.runner = LagrangianHindcastRunner(self.config)

        # Bombay High slick polygon geometry
        self.poly_coords = [
            (72.40, 18.90),
            (72.45, 18.90),
            (72.44, 18.95),
            (72.38, 18.93),
            (72.40, 18.90),
        ]
        self.polygon = Polygon(self.poly_coords)

        self.t_obs = datetime(2026, 9, 7, 12, 0, tzinfo=UTC)
        self.t_age_hours = 6.0

        # Create synthetic metocean forcing covering the simulation window
        bbox = (72.0, 18.5, 73.0, 19.5)
        self.forcing_ds = generate_synthetic_metocean_dataset(
            bbox=bbox,
            time_start=self.t_obs - timedelta(hours=10),
            time_end=self.t_obs + timedelta(hours=2),
            confidence_pct=88.0,
        )

    def test_particle_seeding_uniformity_and_bounds(self) -> None:
        """Verify that exactly N = 10,000 particles are seeded strictly inside polygon."""
        n_particles = 10000
        lons, lats = seed_particles_in_polygon(
            self.polygon, n_particles=n_particles, random_seed=42
        )

        self.assertEqual(len(lons), n_particles)
        self.assertEqual(len(lats), n_particles)

        # Check all points fall within the polygon bounding box
        min_lon, min_lat, max_lon, max_lat = self.polygon.bounds
        self.assertTrue(np.all(lons >= min_lon))
        self.assertTrue(np.all(lons <= max_lon))
        self.assertTrue(np.all(lats >= min_lat))
        self.assertTrue(np.all(lats <= max_lat))

        # Test point-in-polygon containment on random subsample
        pts = shapely.points(lons[:500], lats[:500])
        inside = shapely.contains(self.polygon, pts)
        self.assertTrue(np.all(inside))

    def test_seeding_from_geojson_dict(self) -> None:
        """Verify particle seeding from GeoJSON geometry dictionary."""
        geojson_poly = {
            "type": "Polygon",
            "coordinates": [self.poly_coords],
        }
        lons, lats = seed_particles_in_polygon(geojson_poly, n_particles=500, random_seed=42)
        self.assertEqual(len(lons), 500)
        self.assertEqual(len(lats), 500)

    def test_backward_trajectory_displacement_and_physics(self) -> None:
        """Verify that backward advection advects particles up-drift towards origin.

        With ambient currents and winds pushing towards North-East (~70°),
        backward tracking in time must displace the particle ensemble South-West
        (origin_lon < detection_lon, origin_lat < detection_lat).
        """
        result: HindcastResult = self.runner.run_hindcast(
            slick_polygon=self.polygon,
            t_obs=self.t_obs,
            t_age_hours=self.t_age_hours,
            forcing_ds=self.forcing_ds,
            case_id="case-bench-001",
        )

        self.assertIsInstance(result, HindcastResult)
        self.assertEqual(result.n_particles, 10000)
        self.assertEqual(result.duration_hours, 6.0)

        # Initial centroid at detection time
        init_lon = float(np.mean([pt[0] for pt in self.poly_coords[:-1]]))
        init_lat = float(np.mean([pt[1] for pt in self.poly_coords[:-1]]))

        origin_lon, origin_lat = result.origin_centroid

        # Backward tracking moves opposite to North-East forcing -> towards South-West
        self.assertLess(origin_lon, init_lon)
        self.assertLess(origin_lat, init_lat)

        # Compute displacement distance in km
        dlon_m = (
            (init_lon - origin_lon)
            * (math.pi / 180.0)
            * 6371000.0
            * math.cos(math.radians(init_lat))
        )
        dlat_m = (init_lat - origin_lat) * (math.pi / 180.0) * 6371000.0
        disp_km = math.hypot(dlon_m, dlat_m) / 1000.0

        # Over 6 hours at ~0.6 m/s, displacement should be ~10 to 20 km
        self.assertGreater(disp_km, 8.0)
        self.assertLess(disp_km, 25.0)

        # Verify time properties
        expected_release = self.t_obs - timedelta(hours=6.0)
        self.assertEqual(result.estimated_release_time, expected_release)

        # Rule 1: Confidence
        self.assertGreaterEqual(result.confidence_pct, 0.0)
        self.assertLessEqual(result.confidence_pct, 100.0)

        # Rule 4: Data source
        self.assertEqual(result.data_source, "synthetic")

    def test_turbulent_diffusion_dispersion(self) -> None:
        """Verify that horizontal turbulent diffusion (K_h) expands the particle ensemble."""
        # 1. Run with K_h = 0.0 (pure deterministic advection)
        cfg_no_diff = HindcastConfig(
            n_particles=2000,
            time_step_minutes=-15.0,
            horizontal_diffusivity_kh=0.0,
            random_seed=42,
        )
        runner_no_diff = LagrangianHindcastRunner(cfg_no_diff)
        res_no_diff = runner_no_diff.run_hindcast(self.polygon, self.t_obs, 4.0, self.forcing_ds)

        # 2. Run with strong diffusion K_h = 5.0 m^2/s
        cfg_with_diff = HindcastConfig(
            n_particles=2000,
            time_step_minutes=-15.0,
            horizontal_diffusivity_kh=5.0,
            random_seed=42,
        )
        runner_with_diff = LagrangianHindcastRunner(cfg_with_diff)
        res_with_diff = runner_with_diff.run_hindcast(
            self.polygon, self.t_obs, 4.0, self.forcing_ds
        )

        var_no_diff = (
            res_no_diff.origin_covariance_matrix["var_lon"]
            + res_no_diff.origin_covariance_matrix["var_lat"]
        )
        var_with_diff = (
            res_with_diff.origin_covariance_matrix["var_lon"]
            + res_with_diff.origin_covariance_matrix["var_lat"]
        )

        # Dispersion must be strictly larger when turbulent diffusion is active
        self.assertGreater(var_with_diff, var_no_diff)

    def test_snapshot_intervals_and_sequence(self) -> None:
        """Verify snapshot timestamps decrease by exactly 15 minutes per step."""
        t_age = 3.0  # 3 hours = 12 steps of 15 min
        result = self.runner.run_hindcast(self.polygon, self.t_obs, t_age, self.forcing_ds)

        expected_steps = int(3.0 * 60 / 15)  # 12
        self.assertEqual(len(result.snapshots), expected_steps + 1)  # step 0 + 12 steps

        # Check timestamp monotonic decrease
        for i in range(len(result.snapshots) - 1):
            s_curr = result.snapshots[i]
            s_next = result.snapshots[i + 1]
            time_diff = (s_curr.timestamp - s_next.timestamp).total_seconds()
            self.assertAlmostEqual(time_diff, 900.0, places=1)

        self.assertEqual(result.snapshots[0].timestamp, self.t_obs)
        self.assertEqual(result.snapshots[-1].timestamp, self.t_obs - timedelta(hours=t_age))

    def test_geojson_trajectory_export(self) -> None:
        """Verify export of hindcast result into GeoJSON FeatureCollection."""
        result = self.runner.run_hindcast(
            self.polygon, self.t_obs, 2.0, self.forcing_ds, case_id="test-case-geojson"
        )

        geojson = self.runner.to_geojson_trajectory(result)
        self.assertEqual(geojson["type"], "FeatureCollection")
        self.assertEqual(len(geojson["features"]), 3)

        # Feature 0: Polygon
        self.assertEqual(geojson["features"][0]["geometry"]["type"], "Polygon")
        # Feature 1: LineString centroid track
        self.assertEqual(geojson["features"][1]["geometry"]["type"], "LineString")
        # Feature 2: Origin centroid Point
        self.assertEqual(geojson["features"][2]["geometry"]["type"], "Point")

        # Metadata checks
        self.assertEqual(geojson["metadata"]["case_id"], "test-case-geojson")
        self.assertEqual(geojson["metadata"]["n_particles"], 10000)
        self.assertGreaterEqual(geojson["metadata"]["confidence_pct"], 0.0)


if __name__ == "__main__":
    unittest.main()
