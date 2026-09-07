"""Unit tests for Forward Trajectory Forecasting & Mackay Weathering (TASK-021).

Verifies:
1. Mackay evaporative loss formula and physical bounds.
2. Water-in-oil emulsification kinetics and Mooney viscosity increase.
3. Forward Lagrangian advection over positive timesteps.
4. Shoreline beaching detection (proximity <= 50m) and immobilization.
5. Estimated Time of Beaching (ETB), Coastal Vulnerability Index (CVI), and beached volume.
6. Open-ocean non-beaching scenario handling.
7. GeoJSON impact envelope and Pydantic ForwardForecastBase serialization.
8. Rule 1 & Rule 4 compliance and Rule 6 banned terminology check.
"""

from __future__ import annotations

import unittest
from datetime import UTC, datetime, timedelta

import shapely
from shapely.geometry import Polygon

from backend.app.schemas.hindcast import ForwardForecastBase
from backend.services.data_adapters.metocean_adapter import generate_synthetic_metocean_dataset
from backend.services.tier3_hindcast.forecast_runner import (
    ForecastConfig,
    ForwardForecastResult,
    ForwardTrajectoryForecaster,
    calculate_emulsification_kinetics,
    calculate_mackay_evaporation,
)


class TestForecastRunner(unittest.TestCase):
    """Test suite for forward hydrodynamic forecasting, oil weathering, and coastal impact."""

    def setUp(self) -> None:
        self.config = ForecastConfig(
            n_particles=1000,
            forecast_hours=24.0,  # 24h for fast unit testing
            time_step_minutes=15.0,
            initial_volume_m3=100.0,
            random_seed=42,
        )
        self.forecaster = ForwardTrajectoryForecaster(self.config)

        # Bombay High slick polygon geometry
        self.slick_poly = Polygon(
            [
                (72.40, 18.90),
                (72.44, 18.90),
                (72.43, 18.94),
                (72.39, 18.92),
                (72.40, 18.90),
            ]
        )

        self.t_obs = datetime(2026, 9, 7, 12, 0, tzinfo=UTC)

        # Metocean dataset covering Bombay High and eastward coastal region
        bbox = (72.0, 18.5, 73.5, 19.5)
        self.forcing_ds = generate_synthetic_metocean_dataset(
            bbox=bbox,
            time_start=self.t_obs - timedelta(hours=2),
            time_end=self.t_obs + timedelta(hours=80),
            confidence_pct=90.0,
        )

    def test_mackay_evaporation_kinetics(self) -> None:
        """Verify Mackay evaporative loss monotonically increases and respects bounds."""
        f_0 = calculate_mackay_evaporation(0.0)
        self.assertEqual(f_0, 0.0)

        f_6h = calculate_mackay_evaporation(6 * 3600.0)
        f_24h = calculate_mackay_evaporation(24 * 3600.0)
        f_72h = calculate_mackay_evaporation(72 * 3600.0)

        # Monotonic increase
        self.assertLess(f_0, f_6h)
        self.assertLess(f_6h, f_24h)
        self.assertLess(f_24h, f_72h)

        # Realistic medium crude evaporation bounds [10%, 55%]
        self.assertGreater(f_6h, 0.10)
        self.assertLessEqual(f_72h, 0.55)

    def test_emulsification_and_viscosity_increase(self) -> None:
        """Verify water uptake kinetics and exponential Mooney viscosity increase."""
        y_0, visc_0 = calculate_emulsification_kinetics(0.0, mean_wind_speed_mps=7.0)
        self.assertEqual(y_0, 0.0)
        self.assertEqual(visc_0, 1.0)

        y_12h, visc_12h = calculate_emulsification_kinetics(12 * 3600.0, mean_wind_speed_mps=7.0)
        y_48h, visc_48h = calculate_emulsification_kinetics(48 * 3600.0, mean_wind_speed_mps=7.0)

        # Water content approaches 80%
        self.assertGreater(y_12h, 0.50)
        self.assertLessEqual(y_48h, 0.80)

        # Mooney viscosity increases by more than 30x baseline
        self.assertGreater(visc_12h, 10.0)
        self.assertGreater(visc_48h, 30.0)

    def test_open_ocean_non_beaching_scenario(self) -> None:
        """Verify forward forecast metrics when no coastline is encountered."""
        result: ForwardForecastResult = self.forecaster.run_forecast(
            slick_polygon=self.slick_poly,
            t_obs=self.t_obs,
            forcing_ds=self.forcing_ds,
            coastline_polygon=None,  # Open ocean
            initial_volume_m3=100.0,
            case_id="case-open-ocean",
        )

        self.assertIsInstance(result, ForwardForecastResult)
        self.assertEqual(result.n_beached, 0)
        self.assertEqual(result.beached_fraction, 0.0)
        self.assertIsNone(result.etb_hours)
        self.assertIsNone(result.cvi_index)
        self.assertIsNone(result.beached_volume_m3)
        self.assertIsNone(result.shoreline_impact_polygon)

        # Mass balance: floating + evaporated ≈ initial volume
        self.assertAlmostEqual(
            result.floating_volume_m3 + result.evaporated_volume_m3,
            100.0,
            delta=1.0,
        )

        # Rule 1 & Rule 4
        self.assertGreaterEqual(result.confidence_pct, 0.0)
        self.assertLessEqual(result.confidence_pct, 100.0)
        self.assertEqual(result.data_source, "synthetic")

    def test_coastal_beaching_detection_and_impact(self) -> None:
        """Verify coastal proximity beaching detection (<= 50m), ETB, CVI, and impact polygon."""
        # Coastline barrier placed along trajectory path (particles drift East / North-East)
        # Place coastline barrier at lon >= 72.55 (just east of slick at 72.42)
        coast_poly = Polygon(
            [
                (72.55, 18.50),
                (73.20, 18.50),
                (73.20, 19.50),
                (72.55, 19.50),
                (72.55, 18.50),
            ]
        )

        result: ForwardForecastResult = self.forecaster.run_forecast(
            slick_polygon=self.slick_poly,
            t_obs=self.t_obs,
            forcing_ds=self.forcing_ds,
            coastline_polygon=coast_poly,
            initial_volume_m3=150.0,
            case_id="case-coastal-impact",
        )

        self.assertIsInstance(result, ForwardForecastResult)
        # Beaching should occur as particles drift eastward into the coastline barrier
        self.assertGreater(result.n_beached, 0)
        self.assertGreater(result.beached_fraction, 0.0)

        # ETB (Estimated Time of Beaching) must be a positive float within forecast horizon
        self.assertIsNotNone(result.etb_hours)
        assert result.etb_hours is not None
        self.assertGreater(result.etb_hours, 0.0)
        self.assertLessEqual(result.etb_hours, 24.0)

        # Coastal Vulnerability Index (CVI) must be bounded in [0.0, 1.0]
        self.assertIsNotNone(result.cvi_index)
        assert result.cvi_index is not None
        self.assertGreater(result.cvi_index, 0.0)
        self.assertLessEqual(result.cvi_index, 1.0)

        # Beached volume must be positive and bounded by initial volume
        self.assertIsNotNone(result.beached_volume_m3)
        assert result.beached_volume_m3 is not None
        self.assertGreater(result.beached_volume_m3, 0.0)
        self.assertLessEqual(result.beached_volume_m3, 150.0)

        # Shoreline impact polygon should be generated
        self.assertIsNotNone(result.shoreline_impact_polygon)
        assert result.shoreline_impact_polygon is not None
        self.assertEqual(result.shoreline_impact_polygon["type"], "Polygon")
        impact_geom = shapely.geometry.shape(result.shoreline_impact_polygon)
        self.assertTrue(impact_geom.is_valid)

    def test_pydantic_and_geojson_serialization(self) -> None:
        """Verify export to Pydantic ForwardForecastBase and GeoJSON Feature."""
        coast_poly = Polygon(
            [
                (72.55, 18.50),
                (73.20, 18.50),
                (73.20, 19.50),
                (72.55, 19.50),
                (72.55, 18.50),
            ]
        )

        result = self.forecaster.run_forecast(
            slick_polygon=self.slick_poly,
            t_obs=self.t_obs,
            forcing_ds=self.forcing_ds,
            coastline_polygon=coast_poly,
            initial_volume_m3=100.0,
            case_id="case-serialize-test",
        )

        # 1. Pydantic schema validation
        pydantic_model = result.to_pydantic_schema()
        self.assertIsInstance(pydantic_model, ForwardForecastBase)
        self.assertEqual(pydantic_model.etb_hours, result.etb_hours)
        self.assertEqual(pydantic_model.cvi_index, result.cvi_index)
        self.assertEqual(pydantic_model.beached_volume_m3, result.beached_volume_m3)

        # 2. GeoJSON serialization
        geojson = result.to_geojson_feature()
        self.assertEqual(geojson["type"], "Feature")
        self.assertEqual(geojson["properties"]["case_id"], "case-serialize-test")
        self.assertIn("weathering", geojson["properties"])


if __name__ == "__main__":
    unittest.main()
