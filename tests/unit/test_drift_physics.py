"""Unit tests for Total Drift Velocity Engine (TASK-018).

Verifies three-component hydrodynamic drift composition:
u_drift = u_current + c_w * R(theta_w) * u_wind + u_stokes
including Coriolis deflection, Stokes wave drift, uncertainty intervals,
point interpolation, vectorized particle advection, and full grid computation.
"""

from __future__ import annotations

import math
import unittest
from datetime import UTC, datetime

import numpy as np

from backend.services.data_adapters.metocean_adapter import generate_synthetic_metocean_dataset
from backend.services.tier3_hindcast.drift_physics import (
    DriftConfig,
    DriftPhysicsEngine,
    DriftVelocityResult,
    apply_coriolis_rotation,
    calculate_drift_vector,
    get_coriolis_deflection_angle,
)


class TestDriftPhysics(unittest.TestCase):
    """Test suite for hydrodynamic drift physics formulas and engine."""

    def setUp(self) -> None:
        self.config = DriftConfig(
            wind_drift_factor=0.030,
            coriolis_deflection_deg=12.0,
            stokes_drift_factor=0.012,
        )
        self.engine = DriftPhysicsEngine(self.config)

        # Bombay High benchmark coordinates
        self.bbox = (72.10, 18.70, 72.60, 19.10)
        self.t_start = datetime(2026, 9, 6, 6, 0, tzinfo=UTC)
        self.t_end = datetime(2026, 9, 7, 18, 0, tzinfo=UTC)

    def test_coriolis_deflection_hemispheric_behavior(self) -> None:
        """Verify Coriolis deflection angle theta_w across hemispheres."""
        # Northern Hemisphere (lat = 20°N): clockwise / positive angle
        theta_north = get_coriolis_deflection_angle(20.0, nominal_deg=12.0)
        self.assertAlmostEqual(theta_north, 12.0, places=1)
        self.assertGreater(theta_north, 0.0)

        # Southern Hemisphere (lat = -20°S): counter-clockwise / negative angle
        theta_south = get_coriolis_deflection_angle(-20.0, nominal_deg=12.0)
        self.assertAlmostEqual(theta_south, -12.0, places=1)
        self.assertLess(theta_south, 0.0)

        # Equator (lat = 0°): zero deflection
        theta_eq = get_coriolis_deflection_angle(0.0, nominal_deg=12.0)
        self.assertAlmostEqual(theta_eq, 0.0, places=3)

    def test_coriolis_vector_rotation(self) -> None:
        """Verify vector rotation direction (clockwise for positive theta)."""
        # Wind blowing due North (u=0, v=10)
        # Clockwise rotation (+90°) should point due East (u=10, v=0)
        u_rot, v_rot = apply_coriolis_rotation(0.0, 10.0, 90.0)
        self.assertAlmostEqual(u_rot, 10.0, places=3)
        self.assertAlmostEqual(v_rot, 0.0, places=3)

        # Counter-clockwise rotation (-90°) should point due West (u=-10, v=0)
        u_rot_ccw, v_rot_ccw = apply_coriolis_rotation(0.0, 10.0, -90.0)
        self.assertAlmostEqual(u_rot_ccw, -10.0, places=3)
        self.assertAlmostEqual(v_rot_ccw, 0.0, places=3)

    def test_pure_current_drift(self) -> None:
        """Verify that zero wind and waves yields total drift equal to ambient current."""
        u_curr = 0.45
        v_curr = -0.25
        u_tot, v_tot, curr_c, wind_c, stokes_c, _ = calculate_drift_vector(
            u_curr=u_curr,
            v_curr=v_curr,
            u_wind=0.0,
            v_wind=0.0,
            lat=19.0,
            config=self.config,
        )

        self.assertAlmostEqual(u_tot, u_curr, places=4)
        self.assertAlmostEqual(v_tot, v_curr, places=4)
        self.assertAlmostEqual(wind_c.speed_mps, 0.0, places=4)
        self.assertAlmostEqual(stokes_c.speed_mps, 0.0, places=4)

    def test_hand_computed_benchmark_accuracy(self) -> None:
        """Verify total drift velocity against exact analytical hand calculation.

        Benchmark conditions:
        - u_curr = 0.28 m/s, v_curr = 0.12 m/s
        - u_wind = 6.5 m/s, v_wind = 3.0 m/s
        - lat = 18.9° N (theta_w = +12.0°)
        - c_w = 0.030, c_stokes = 0.012

        Hand-computed exact analytical values:
        - u_tot = 0.567451 m/s
        - v_tot = 0.203491 m/s
        - speed = 0.602834 m/s
        - bearing = 70.27°
        """
        result: DriftVelocityResult = self.engine.evaluate_vectors(
            u_curr=0.28,
            v_curr=0.12,
            u_wind=6.5,
            v_wind=3.0,
            lat=18.9,
            lon=72.4,
            confidence_pct=88.0,
            data_source="synthetic",
        )

        self.assertAlmostEqual(result.u_drift, 0.5675, places=3)
        self.assertAlmostEqual(result.v_drift, 0.2035, places=3)
        self.assertAlmostEqual(result.drift_speed_mps, 0.6028, places=3)
        self.assertAlmostEqual(result.drift_bearing_deg, 70.27, places=1)

        # Decomposed components verification
        self.assertAlmostEqual(result.current.u, 0.28, places=2)
        self.assertAlmostEqual(result.current.v, 0.12, places=2)
        self.assertAlmostEqual(result.wind_drift.speed_mps, 0.030 * math.hypot(6.5, 3.0), places=3)
        self.assertAlmostEqual(result.stokes_drift.u, 0.012 * 6.5, places=3)
        self.assertAlmostEqual(result.stokes_drift.v, 0.012 * 3.0, places=3)

        # Rule 1: Confidence
        self.assertEqual(result.confidence_pct, 88.0)
        # Rule 4: Data source
        self.assertEqual(result.data_source, "synthetic")

    def test_wind_deflection_hemispheric_drift_direction(self) -> None:
        """Verify that wind drift deflects right in Northern Hemisphere and left in Southern."""
        # Wind blowing due North (u_wind=0, v_wind=10)
        # In Northern Hemisphere, deflection is clockwise (towards East, u_wind_drift > 0)
        res_north = self.engine.evaluate_vectors(
            u_curr=0.0,
            v_curr=0.0,
            u_wind=0.0,
            v_wind=10.0,
            lat=25.0,
        )
        self.assertGreater(res_north.wind_drift.u, 0.0)

        # In Southern Hemisphere, deflection is counter-clockwise (towards West, u_wind_drift < 0)
        res_south = self.engine.evaluate_vectors(
            u_curr=0.0,
            v_curr=0.0,
            u_wind=0.0,
            v_wind=10.0,
            lat=-25.0,
        )
        self.assertLess(res_south.wind_drift.u, 0.0)

    def test_drift_uncertainty_interval(self) -> None:
        """Verify physical uncertainty interval spanning c_w in [0.025, 0.035]."""
        result = self.engine.evaluate_vectors(
            u_curr=0.25,
            v_curr=0.10,
            u_wind=8.0,
            v_wind=4.0,
            lat=19.0,
            include_uncertainty=True,
        )

        self.assertIsNotNone(result.uncertainty)
        unc = result.uncertainty
        assert unc is not None
        self.assertGreater(unc.speed_max_mps, unc.speed_min_mps)
        self.assertGreaterEqual(result.drift_speed_mps, unc.speed_min_mps - 1e-4)
        self.assertLessEqual(result.drift_speed_mps, unc.speed_max_mps + 1e-4)
        self.assertGreaterEqual(unc.confidence_pct, 0.0)
        self.assertLessEqual(unc.confidence_pct, 100.0)

    def test_evaluate_point_with_dataset(self) -> None:
        """Verify evaluate_point using interpolated xarray Dataset."""
        ds = generate_synthetic_metocean_dataset(
            bbox=self.bbox,
            time_start=self.t_start,
            time_end=self.t_end,
            confidence_pct=91.5,
        )

        q_lon = 72.35
        q_lat = 18.85
        q_time = datetime(2026, 9, 6, 12, 0, tzinfo=UTC)

        result: DriftVelocityResult = self.engine.evaluate_point(ds, q_lon, q_lat, q_time)

        self.assertIsInstance(result, DriftVelocityResult)
        self.assertAlmostEqual(result.lon, q_lon, places=2)
        self.assertAlmostEqual(result.lat, q_lat, places=2)
        self.assertEqual(result.confidence_pct, 91.5)
        self.assertEqual(result.data_source, "synthetic")
        self.assertGreater(result.drift_speed_mps, 0.0)

    def test_evaluate_vectorized_particle_ensemble(self) -> None:
        """Verify vectorized drift velocity evaluation for N = 10,000 Lagrangian particles."""
        ds = generate_synthetic_metocean_dataset(
            bbox=self.bbox,
            time_start=self.t_start,
            time_end=self.t_end,
        )

        n_particles = 10000
        lons = np.random.uniform(72.15, 72.55, n_particles).astype(np.float32)
        lats = np.random.uniform(18.75, 19.05, n_particles).astype(np.float32)
        q_time = datetime(2026, 9, 6, 14, 0, tzinfo=UTC)

        u_drift, v_drift, speed, bearing = self.engine.evaluate_vectorized(ds, lons, lats, q_time)

        self.assertEqual(len(u_drift), n_particles)
        self.assertEqual(len(v_drift), n_particles)
        self.assertEqual(len(speed), n_particles)
        self.assertEqual(len(bearing), n_particles)

        # Assert no NaNs or Infinities
        self.assertFalse(np.isnan(u_drift).any())
        self.assertFalse(np.isnan(v_drift).any())
        self.assertFalse(np.isnan(speed).any())
        self.assertFalse(np.isnan(bearing).any())

        # Physical reasonableness check
        self.assertTrue(np.all(speed > 0.05))
        self.assertTrue(np.all(speed < 2.0))
        self.assertTrue(np.all(bearing >= 0.0))
        self.assertTrue(np.all(bearing < 360.0))

    def test_compute_drift_field_dataset(self) -> None:
        """Verify grid-level computation of drift velocity fields on xarray Dataset."""
        ds = generate_synthetic_metocean_dataset(
            bbox=self.bbox,
            time_start=self.t_start,
            time_end=self.t_end,
        )

        ds_drift = self.engine.compute_drift_field(ds)

        # Required variables added to dataset
        self.assertIn("u_drift", ds_drift.data_vars)
        self.assertIn("v_drift", ds_drift.data_vars)
        self.assertIn("drift_speed", ds_drift.data_vars)
        self.assertIn("drift_bearing", ds_drift.data_vars)

        # Dimensions preserved
        self.assertEqual(ds_drift["u_drift"].shape, ds["uo"].shape)
        self.assertEqual(ds_drift["v_drift"].shape, ds["vo"].shape)
        self.assertEqual(ds_drift.sizes["time"], ds.sizes["time"])
        self.assertEqual(ds_drift.sizes["lat"], ds.sizes["lat"])
        self.assertEqual(ds_drift.sizes["lon"], ds.sizes["lon"])


if __name__ == "__main__":
    unittest.main()
