"""Integration tests for Tier 2 Celery characterization task and pipeline (TASK-016)."""

import unittest
import uuid
from datetime import datetime, timezone
from unittest.mock import MagicMock, patch

import shapely.affinity
import shapely.geometry
from geoalchemy2.shape import from_shape, to_shape
from sqlalchemy.orm import Session

from backend.app.models.entities import (
    Case,
    CaseStatus,
    DataSource,
    SlickCharacterization,
    SlickDetection,
)
from backend.core.celery_app import celery_app
from backend.workers.tasks.tier2_tasks import run_tier2_characterization


class TestTier2PipelineIntegration(unittest.TestCase):
    """Integration test suite for Tier 2 characterization Celery task."""

    def setUp(self) -> None:
        """Create mock database environment with Case and SlickDetection."""
        self.case_id = str(uuid.uuid4())
        self.case_uuid = uuid.UUID(self.case_id)

        self.mock_case = Case(
            id=self.case_uuid,
            status=CaseStatus.CHARACTERIZING,
            created_by="analyst_test",
        )

        # Create realistic slick polygon (elongated ellipse in Bombay High)
        center_lon, center_lat = 72.0, 19.0
        circle = shapely.geometry.Point(center_lon, center_lat).buffer(0.01)
        ellipse = shapely.affinity.scale(circle, xfact=3.0, yfact=0.8)
        poly = shapely.affinity.rotate(ellipse, 45.0, origin=(center_lon, center_lat))

        self.detection_id = uuid.uuid4()
        self.mock_detection = SlickDetection(
            id=self.detection_id,
            case_id=self.case_uuid,
            polygon=from_shape(poly, srid=4326),
            centroid=from_shape(poly.centroid, srid=4326),
            area_m2=725100.0,
            confidence=74.8,  # Rule 1
            lookalike_risk=0.0,
            sensor="Sentinel-1 SAR IW",
            detection_time=datetime.now(timezone.utc),
            data_source=DataSource.SYNTHETIC,
        )

        # Mock database session
        self.mock_db = MagicMock(spec=Session)
        self.stored_objects = []

        def mock_add(obj):
            self.stored_objects.append(obj)

        self.mock_db.add.side_effect = mock_add

        # Configure query returns
        def mock_query(model):
            q = MagicMock()
            if model == Case:
                q.filter.return_value.first.return_value = self.mock_case
            elif model == SlickDetection:
                q.filter.return_value.order_by.return_value.first.return_value = self.mock_detection
            elif model == SlickCharacterization:
                q.filter.return_value.delete.return_value = 1
            return q

        self.mock_db.query.side_effect = mock_query

    def test_celery_task_registration_and_routing(self) -> None:
        """Verify task is registered in Celery app with correct tier2 routing."""
        self.assertIn("tier2.run_tier2_characterization", celery_app.tasks)
        task = celery_app.tasks["tier2.run_tier2_characterization"]
        self.assertEqual(task.name, "tier2.run_tier2_characterization")

    def test_run_tier2_characterization_pipeline_execution(self) -> None:
        """Test full Tier 2 pipeline execution from morphometry to SlickCharacterization persistence."""
        with patch.object(run_tier2_characterization, "update_progress") as mock_progress:
            result = run_tier2_characterization(
                case_id=self.case_id,
                db_session=self.mock_db,
            )

        # 1. Assert result payload
        self.assertEqual(result["status"], "success")
        self.assertEqual(result["case_id"], self.case_id)
        self.assertEqual(result["stage"], "hindcasting")
        self.assertGreater(result["perimeter_m"], 1000.0)
        self.assertGreaterEqual(result["principal_axis_deg"], 0.0)
        self.assertLess(result["principal_axis_deg"], 360.0)
        self.assertIn(result["baoac_code"], [1, 2, 3, 4, 5])
        self.assertGreater(result["estimated_volume_m3"], 0.0)
        self.assertGreater(result["t_age_hours"], 0.0)
        self.assertGreater(result["age_confidence"], 0.0)

        # 2. Assert case state transition
        self.assertEqual(self.mock_case.status, CaseStatus.HINDCASTING)

        # 3. Assert SlickCharacterization database entity
        char_objs = [obj for obj in self.stored_objects if isinstance(obj, SlickCharacterization)]
        self.assertEqual(len(char_objs), 1)
        char = char_objs[0]

        self.assertEqual(char.case_id, self.case_uuid)
        self.assertAlmostEqual(char.perimeter_m, result["perimeter_m"])
        self.assertAlmostEqual(char.principal_axis_deg, result["principal_axis_deg"])
        self.assertEqual(char.baoac_code, result["baoac_code"])
        self.assertAlmostEqual(char.estimated_volume_m3, result["estimated_volume_m3"])
        self.assertAlmostEqual(char.t_age_hours, result["t_age_hours"])
        self.assertAlmostEqual(char.age_confidence, result["age_confidence"])

        # 4. Assert progress updates broadcasted (10% to 100%)
        self.assertGreaterEqual(mock_progress.call_count, 4)
        final_call = mock_progress.call_args_list[-1]
        self.assertEqual(final_call.kwargs["percent"], 100.0)
        self.assertEqual(final_call.kwargs["stage"], "hindcasting")

    def test_run_tier2_characterization_idempotency(self) -> None:
        """Test idempotency: prior characterizations are cleared before inserting new one."""
        run_tier2_characterization(
            case_id=self.case_id,
            db_session=self.mock_db,
        )

        # Query delete must have been invoked for SlickCharacterization
        self.mock_db.query.assert_any_call(SlickCharacterization)

    def test_run_tier2_characterization_missing_detection_raises(self) -> None:
        """Verify task raises ValueError if no SlickDetection exists for the case."""
        empty_db = MagicMock(spec=Session)

        def mock_empty_query(model):
            q = MagicMock()
            if model == SlickDetection:
                q.filter.return_value.order_by.return_value.first.return_value = None
            return q

        empty_db.query.side_effect = mock_empty_query

        with self.assertRaises(ValueError):
            run_tier2_characterization(
                case_id=self.case_id,
                db_session=empty_db,
            )


if __name__ == "__main__":
    unittest.main()
