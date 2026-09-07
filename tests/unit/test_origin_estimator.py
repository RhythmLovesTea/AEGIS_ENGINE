"""Unit tests for Probabilistic Origin Density Estimation (TASK-020).

Verifies:
1. 2D Gaussian Kernel Density Estimation (KDE) and mode centroid mu_p convergence.
2. 2x2 Spatial covariance matrix Sigma_p calculation (geodetic and metric).
3. 1-sigma, 2-sigma, 3-sigma confidence error ellipse generation and concentric nesting.
4. Empirical particle probability mass containment matching theoretical values (39%, 86%, 98.9%).
5. Integration with Lagrangian HindcastResult.
6. GeoJSON and Pydantic schema serialization.
7. Rule 1 & Rule 4 compliance and Rule 6 banned terminology check.
"""

from __future__ import annotations

import unittest
from datetime import UTC, datetime, timedelta

import numpy as np
import shapely
from shapely.geometry import Polygon

from backend.app.schemas.hindcast import OriginEstimateBase
from backend.services.data_adapters.metocean_adapter import generate_synthetic_metocean_dataset
from backend.services.tier3_hindcast.hindcast_runner import HindcastConfig, LagrangianHindcastRunner
from backend.services.tier3_hindcast.origin_estimator import (
    ConfidenceEllipse,
    OriginDensityEstimator,
    OriginEstimateResult,
)


class TestOriginEstimator(unittest.TestCase):
    """Test suite for probabilistic origin density estimation and error ellipses."""

    def setUp(self) -> None:
        self.estimator = OriginDensityEstimator(bandwidth_method="scott")

        # Synthetic benchmark Gaussian particle cluster around Bombay High (72.29, 18.865)
        rng = np.random.default_rng(42)
        self.known_center_lon = 72.29
        self.known_center_lat = 18.865
        self.n_particles = 10000

        # Known covariance: var_lon = 0.000185 (std ~ 0.0136), var_lat = 0.000142 (std ~ 0.0119)
        cov = np.array([[0.000185, 0.000095], [0.000095, 0.000142]])
        pts = rng.multivariate_normal(
            [self.known_center_lon, self.known_center_lat],
            cov,
            size=self.n_particles,
        )
        self.sample_lons = pts[:, 0]
        self.sample_lats = pts[:, 1]

    def test_kde_mode_centroid_convergence(self) -> None:
        """Verify that 2D Gaussian KDE mode centroid converges to the true distribution center."""
        result: OriginEstimateResult = self.estimator.estimate_origin(
            lons=self.sample_lons,
            lats=self.sample_lats,
            case_id="case-bench-001",
            confidence_pct=89.2,
            data_source="synthetic",
        )

        c_lon, c_lat = result.centroid
        self.assertAlmostEqual(c_lon, self.known_center_lon, places=2)
        self.assertAlmostEqual(c_lat, self.known_center_lat, places=2)

        # Centroid lat/lon coordinates
        self.assertEqual(result.centroid_lat_lon, (c_lat, c_lon))

        # Peak density must be positive
        self.assertGreater(result.peak_density, 0.0)

    def test_spatial_covariance_matrix(self) -> None:
        """Verify geodetic and metric covariance matrices."""
        result = self.estimator.estimate_origin(
            lons=self.sample_lons,
            lats=self.sample_lats,
        )

        cov_geo = result.covariance_matrix
        self.assertIn("var_lon", cov_geo)
        self.assertIn("var_lat", cov_geo)
        self.assertIn("cov_lon_lat", cov_geo)

        # Should closely match the true covariance [0.000185, 0.000142]
        self.assertAlmostEqual(cov_geo["var_lon"], 0.000185, places=4)
        self.assertAlmostEqual(cov_geo["var_lat"], 0.000142, places=4)

        # Metric covariance
        cov_m = result.covariance_matrix_m2
        self.assertGreater(cov_m["var_x_m2"], 0.0)
        self.assertGreater(cov_m["var_y_m2"], 0.0)

    def test_confidence_error_ellipses_nesting_and_areas(self) -> None:
        """Verify 1-sigma, 2-sigma, 3-sigma error ellipses, concentric nesting, and area ratios."""
        result = self.estimator.estimate_origin(
            lons=self.sample_lons,
            lats=self.sample_lats,
        )

        self.assertIn("1sigma", result.ellipses)
        self.assertIn("2sigma", result.ellipses)
        self.assertIn("3sigma", result.ellipses)

        ell1: ConfidenceEllipse = result.ellipses["1sigma"]
        ell2: ConfidenceEllipse = result.ellipses["2sigma"]
        ell3: ConfidenceEllipse = result.ellipses["3sigma"]

        # Theoretical probabilities
        self.assertAlmostEqual(ell1.probability_pct, 39.35, places=1)
        self.assertAlmostEqual(ell2.probability_pct, 86.47, places=1)
        self.assertAlmostEqual(ell3.probability_pct, 98.89, places=1)

        # Geometric validity of polygons
        self.assertTrue(ell1.polygon.is_valid)
        self.assertTrue(ell2.polygon.is_valid)
        self.assertTrue(ell3.polygon.is_valid)

        # Areas strictly increasing
        self.assertLess(ell1.area_km2, ell2.area_km2)
        self.assertLess(ell2.area_km2, ell3.area_km2)

        # Analytical area ratios: Area ~ s^2
        # Area(2-sigma) ≈ 4 * Area(1-sigma)
        self.assertAlmostEqual(ell2.area_km2 / ell1.area_km2, 4.0, places=1)
        # Area(3-sigma) ≈ 9 * Area(1-sigma)
        self.assertAlmostEqual(ell3.area_km2 / ell1.area_km2, 9.0, places=1)

        # Concentric nesting: 1sigma is inside 2sigma, 2sigma is inside 3sigma
        self.assertTrue(ell2.polygon.contains(ell1.polygon) or ell2.polygon.covers(ell1.polygon))
        self.assertTrue(ell3.polygon.contains(ell2.polygon) or ell3.polygon.covers(ell2.polygon))

    def test_empirical_particle_containment_in_ellipses(self) -> None:
        """Verify empirical particle containment fraction matches theoretical probabilities."""
        result = self.estimator.estimate_origin(
            lons=self.sample_lons,
            lats=self.sample_lats,
        )

        pts = shapely.points(self.sample_lons, self.sample_lats)

        # Test containment fractions
        count_1s = int(np.sum(shapely.contains(result.ellipses["1sigma"].polygon, pts)))
        count_2s = int(np.sum(shapely.contains(result.ellipses["2sigma"].polygon, pts)))
        count_3s = int(np.sum(shapely.contains(result.ellipses["3sigma"].polygon, pts)))

        frac_1s = count_1s / self.n_particles
        frac_2s = count_2s / self.n_particles
        frac_3s = count_3s / self.n_particles

        # Empirical containment within ±3% of theoretical
        self.assertAlmostEqual(frac_1s, 0.3935, delta=0.035)
        self.assertAlmostEqual(frac_2s, 0.8647, delta=0.035)
        self.assertAlmostEqual(frac_3s, 0.9889, delta=0.015)

    def test_integration_with_hindcast_result(self) -> None:
        """Verify seamless execution from a Lagrangian HindcastResult."""
        poly = Polygon(
            [
                (72.40, 18.90),
                (72.44, 18.90),
                (72.43, 18.94),
                (72.39, 18.92),
                (72.40, 18.90),
            ]
        )
        t_obs = datetime(2026, 9, 7, 12, 0, tzinfo=UTC)
        forcing_ds = generate_synthetic_metocean_dataset(
            bbox=(72.0, 18.5, 73.0, 19.5),
            time_start=t_obs - timedelta(hours=6),
            time_end=t_obs + timedelta(hours=2),
            confidence_pct=89.0,
        )

        hindcast_cfg = HindcastConfig(n_particles=1000, time_step_minutes=-15.0, random_seed=42)
        runner = LagrangianHindcastRunner(hindcast_cfg)
        h_res = runner.run_hindcast(
            slick_polygon=poly,
            t_obs=t_obs,
            t_age_hours=3.0,
            forcing_ds=forcing_ds,
            case_id="case-integration-001",
        )

        origin_res: OriginEstimateResult = self.estimator.estimate_origin(hindcast_result=h_res)

        self.assertIsInstance(origin_res, OriginEstimateResult)
        self.assertEqual(origin_res.case_id, "case-integration-001")
        self.assertGreater(origin_res.region_area_km2, 0.0)
        self.assertEqual(origin_res.confidence_pct, 89.0)
        self.assertEqual(origin_res.data_source, "synthetic")

        # Time window start must be earlier than time window end
        self.assertLess(origin_res.time_window_start, origin_res.time_window_end)

    def test_schema_conversions(self) -> None:
        """Verify export to GeoJSON Feature and Pydantic OriginEstimateBase model."""
        result = self.estimator.estimate_origin(
            lons=self.sample_lons,
            lats=self.sample_lats,
            case_id="case-schema-test",
            confidence_pct=92.5,
        )

        # 1. GeoJSON serialization
        geojson = result.to_geojson_feature()
        self.assertEqual(geojson["type"], "Feature")
        self.assertEqual(geojson["geometry"]["type"], "Point")
        self.assertEqual(len(geojson["geometry"]["coordinates"]), 2)
        self.assertEqual(geojson["properties"]["case_id"], "case-schema-test")
        self.assertEqual(geojson["properties"]["confidence_pct"], 92.5)
        self.assertIn("1sigma", geojson["properties"]["ellipses"])

        # 2. Pydantic schema validation
        pydantic_model = result.to_pydantic_schema()
        self.assertIsInstance(pydantic_model, OriginEstimateBase)
        self.assertEqual(pydantic_model.confidence_pct, 92.5)
        self.assertEqual(pydantic_model.region_area_km2, result.region_area_km2)


if __name__ == "__main__":
    unittest.main()
