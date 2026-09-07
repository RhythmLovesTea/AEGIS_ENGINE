"""Integration tests for Tier 3 Celery hindcast task and pipeline (TASK-022)."""

import unittest
import uuid
from datetime import UTC, datetime
from unittest.mock import MagicMock, patch

import shapely.affinity
import shapely.geometry
from geoalchemy2.shape import from_shape
from sqlalchemy.orm import Session

from backend.app.models.entities import (
    Case,
    CaseStatus,
    DataSource,
    ForwardForecast,
    OriginEstimate,
    ParticleTrajectory,
    SlickCharacterization,
    SlickDetection,
)
from backend.core.celery_app import celery_app
from backend.services.data_adapters.metocean_adapter import (
    generate_synthetic_metocean_dataset,
)
from backend.workers.tasks.tier3_tasks import run_tier3_hindcast


class TestTier3PipelineIntegration(unittest.TestCase):
    """Integration test suite for Tier 3 hydrodynamic hindcast & forecast Celery task."""

    def setUp(self) -> None:
        """Set up mock case, detection, characterization, and metocean forcing."""
        self.case_id = str(uuid.uuid4())
        self.case_uuid = uuid.UUID(self.case_id)

        self.mock_case = Case(
            id=self.case_uuid,
            status=CaseStatus.HINDCASTING,
            created_by="analyst_test",
        )

        # Create realistic slick polygon (elongated ellipse in Bombay High)
        center_lon, center_lat = 72.0, 19.0
        circle = shapely.geometry.Point(center_lon, center_lat).buffer(0.015)
        ellipse = shapely.affinity.scale(circle, xfact=2.5, yfact=0.9)
        poly = shapely.affinity.rotate(ellipse, 40.0, origin=(center_lon, center_lat))

        self.detection_time = datetime(2026, 9, 7, 12, 0, 0, tzinfo=UTC)

        self.mock_detection = SlickDetection(
            id=uuid.uuid4(),
            case_id=self.case_uuid,
            polygon=from_shape(poly, srid=4326),
            centroid=from_shape(poly.centroid, srid=4326),
            area_m2=750000.0,
            confidence=82.0,  # Rule 1
            lookalike_risk=0.05,
            sensor="Sentinel-1 SAR IW",
            detection_time=self.detection_time,
            data_source=DataSource.SYNTHETIC,
        )

        self.mock_characterization = SlickCharacterization(
            id=uuid.uuid4(),
            case_id=self.case_uuid,
            perimeter_m=4200.0,
            principal_axis_deg=40.0,
            baoac_code=3,
            estimated_volume_m3=125.0,
            t_age_hours=6.0,
            age_confidence=78.5,  # Rule 1
        )

        # Pre-generate compact synthetic met-ocean forcing dataset
        min_lon, min_lat, max_lon, max_lat = poly.bounds
        self.forcing_ds = generate_synthetic_metocean_dataset(
            bbox=(min_lon - 0.5, min_lat - 0.5, max_lon + 0.5, max_lat + 0.5),
            time_start=datetime(2026, 9, 7, 0, 0, 0, tzinfo=UTC),
            time_end=datetime(2026, 9, 10, 18, 0, 0, tzinfo=UTC),
            grid_res_deg=0.1,
            time_step_hours=2.0,
        )

        # Mock database session
        self.mock_db = MagicMock(spec=Session)
        self.stored_objects = []

        def mock_add(obj):
            self.stored_objects.append(obj)

        def mock_add_all(objs):
            self.stored_objects.extend(objs)

        self.mock_db.add.side_effect = mock_add
        self.mock_db.add_all.side_effect = mock_add_all

        # Configure query returns
        def mock_query(model):
            q = MagicMock()
            if model == Case:
                q.filter.return_value.first.return_value = self.mock_case
            elif model == SlickDetection:
                q.filter.return_value.order_by.return_value.first.return_value = self.mock_detection
            elif model == SlickCharacterization:
                q.filter.return_value.order_by.return_value.first.return_value = (
                    self.mock_characterization
                )
            elif model in (ParticleTrajectory, OriginEstimate, ForwardForecast):
                q.filter.return_value.delete.return_value = 1
            return q

        self.mock_db.query.side_effect = mock_query

    def test_celery_task_registration_and_routing(self) -> None:
        """Verify task is registered in Celery app with correct tier3 routing."""
        self.assertIn("tier3.run_tier3_hindcast", celery_app.tasks)
        task = celery_app.tasks["tier3.run_tier3_hindcast"]
        self.assertEqual(task.name, "tier3.run_tier3_hindcast")

    def test_run_tier3_hindcast_pipeline_execution(self) -> None:
        """Test full Tier 3 pipeline execution: hindcast, KDE, forecast, and database persistence."""
        with patch.object(run_tier3_hindcast, "update_progress") as mock_progress:
            result = run_tier3_hindcast(
                case_id=self.case_id,
                db_session=self.mock_db,
                forcing_dataset=self.forcing_ds,
                n_hindcast_particles=1000,
                n_forecast_particles=500,
                include_forecast=True,
            )

        # 1. Assert result structure and values
        self.assertEqual(result["status"], "success")
        self.assertEqual(result["case_id"], self.case_id)
        self.assertEqual(result["stage"], "correlating")
        self.assertIsNotNone(result["origin_estimate_id"])
        self.assertEqual(len(result["origin_centroid"]), 2)
        self.assertGreater(result["region_area_km2"], 0.0)

        # Rule 1 compliance: confidence score in [0.0, 100.0]
        self.assertGreaterEqual(result["confidence_pct"], 0.0)
        self.assertLessEqual(result["confidence_pct"], 100.0)

        # Forecast output
        self.assertIsNotNone(result["forecast_id"])
        self.assertGreater(result["trajectories_persisted"], 0)

        # 2. Assert case state transition
        self.assertEqual(self.mock_case.status, CaseStatus.CORRELATING)

        # 3. Assert OriginEstimate database entity persistence
        origin_objs = [obj for obj in self.stored_objects if isinstance(obj, OriginEstimate)]
        self.assertEqual(len(origin_objs), 1)
        origin = origin_objs[0]
        self.assertEqual(origin.case_id, self.case_uuid)
        self.assertIn("var_lat", origin.covariance_matrix)
        self.assertIn("var_lon", origin.covariance_matrix)
        self.assertGreaterEqual(origin.confidence_pct, 0.0)
        self.assertLessEqual(origin.confidence_pct, 100.0)
        self.assertIn("particle_trajectories", origin.particle_trajectory_ref)

        # 4. Assert ForwardForecast database entity persistence
        forecast_objs = [obj for obj in self.stored_objects if isinstance(obj, ForwardForecast)]
        self.assertEqual(len(forecast_objs), 1)
        forecast = forecast_objs[0]
        self.assertEqual(forecast.case_id, self.case_uuid)

        # 5. Assert ParticleTrajectory records persisted into TimescaleDB hypertable
        traj_objs = [obj for obj in self.stored_objects if isinstance(obj, ParticleTrajectory)]
        self.assertGreater(len(traj_objs), 100)
        sample_pt = traj_objs[0]
        self.assertEqual(sample_pt.case_id, self.case_uuid)
        self.assertIn(sample_pt.status, ["active", "beached"])
        self.assertGreaterEqual(sample_pt.mass_fraction, 0.0)
        self.assertLessEqual(sample_pt.mass_fraction, 1.0)

        # 6. Assert progress updates broadcasted over Redis (from 5% up to 100%)
        self.assertGreaterEqual(mock_progress.call_count, 5)
        final_call = mock_progress.call_args_list[-1]
        self.assertEqual(final_call.kwargs["percent"], 100.0)
        self.assertEqual(final_call.kwargs["stage"], "correlating")

    def test_run_tier3_hindcast_without_forecast(self) -> None:
        """Verify pipeline can run in hindcast-only mode when forecast is disabled."""
        result = run_tier3_hindcast(
            case_id=self.case_id,
            db_session=self.mock_db,
            forcing_dataset=self.forcing_ds,
            n_hindcast_particles=500,
            include_forecast=False,
        )

        self.assertEqual(result["status"], "success")
        self.assertEqual(result["stage"], "correlating")
        self.assertIsNone(result["forecast_id"])

        forecast_objs = [obj for obj in self.stored_objects if isinstance(obj, ForwardForecast)]
        self.assertEqual(len(forecast_objs), 0)

        origin_objs = [obj for obj in self.stored_objects if isinstance(obj, OriginEstimate)]
        self.assertEqual(len(origin_objs), 1)

    def test_run_tier3_hindcast_idempotency(self) -> None:
        """Verify prior estimates, forecasts, and trajectories are deleted on re-run."""
        run_tier3_hindcast(
            case_id=self.case_id,
            db_session=self.mock_db,
            forcing_dataset=self.forcing_ds,
            n_hindcast_particles=500,
            n_forecast_particles=200,
        )

        self.mock_db.query.assert_any_call(OriginEstimate)
        self.mock_db.query.assert_any_call(ForwardForecast)
        self.mock_db.query.assert_any_call(ParticleTrajectory)

    def test_run_tier3_hindcast_missing_detection_raises(self) -> None:
        """Verify task raises ValueError if no SlickDetection exists."""
        empty_db = MagicMock(spec=Session)

        def mock_query(model):
            q = MagicMock()
            if model == SlickDetection:
                q.filter.return_value.order_by.return_value.first.return_value = None
            return q

        empty_db.query.side_effect = mock_query

        with self.assertRaises(ValueError):
            run_tier3_hindcast(
                case_id=self.case_id,
                db_session=empty_db,
                forcing_dataset=self.forcing_ds,
            )

    def test_run_tier3_hindcast_missing_characterization_raises(self) -> None:
        """Verify task raises ValueError if no SlickCharacterization exists."""
        partial_db = MagicMock(spec=Session)

        def mock_query(model):
            q = MagicMock()
            if model == SlickDetection:
                q.filter.return_value.order_by.return_value.first.return_value = self.mock_detection
            elif model == SlickCharacterization:
                q.filter.return_value.order_by.return_value.first.return_value = None
            return q

        partial_db.query.side_effect = mock_query

        with self.assertRaises(ValueError):
            run_tier3_hindcast(
                case_id=self.case_id,
                db_session=partial_db,
                forcing_dataset=self.forcing_ds,
            )


if __name__ == "__main__":
    unittest.main()
