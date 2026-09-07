"""Integration tests for Tier 1 Celery segmentation task and PostGIS pipeline (TASK-012)."""

import tempfile
import unittest
import uuid
from pathlib import Path
from unittest.mock import MagicMock, patch

import shapely.geometry
from geoalchemy2.shape import to_shape
from sqlalchemy.orm import Session

from backend.app.models.entities import Case, CaseStatus, DataSource, SlickDetection
from backend.core.celery_app import celery_app
from backend.services.tier1_segmentation.inference import create_mock_test_tile
from backend.workers.tasks.tier1_tasks import run_tier1_segmentation


class TestTier1PipelineIntegration(unittest.TestCase):
    """Integration test suite for Tier 1 segmentation task and persistence."""

    def setUp(self) -> None:
        """Set up test environment, fixtures, and mock database session."""
        self.temp_dir = tempfile.TemporaryDirectory()
        self.tile_path = Path(self.temp_dir.name) / "test_slick_scene.tif"
        create_mock_test_tile(self.tile_path)

        self.case_id = str(uuid.uuid4())
        self.mock_case = Case(
            id=uuid.UUID(self.case_id),
            status=CaseStatus.DETECTING,
            source_scene_ref=str(self.tile_path),
            created_by="analyst_test",
        )

        # Mock database session
        self.mock_db = MagicMock(spec=Session)
        self.stored_objects = []

        def mock_add(obj):
            self.stored_objects.append(obj)

        self.mock_db.add.side_effect = mock_add
        self.mock_db.query.return_value.filter.return_value.first.return_value = self.mock_case

    def tearDown(self) -> None:
        """Clean up temporary fixtures."""
        self.temp_dir.cleanup()

    def test_celery_task_registration_and_routing(self) -> None:
        """Verify task is registered in Celery app with correct tier1 routing."""
        self.assertIn("tier1.run_tier1_segmentation", celery_app.tasks)
        task = celery_app.tasks["tier1.run_tier1_segmentation"]
        self.assertEqual(task.name, "tier1.run_tier1_segmentation")

    def test_run_tier1_segmentation_pipeline_execution(self) -> None:
        """Test full Tier 1 pipeline execution from scene ingestion to PostGIS persistence."""
        with patch.object(run_tier1_segmentation, "update_progress") as mock_progress:
            result = run_tier1_segmentation(
                case_id=self.case_id,
                scene_ref=str(self.tile_path),
                wind_speed_mps=6.5,
                db_session=self.mock_db,
            )

        # 1. Assert task result structure
        self.assertEqual(result["status"], "success")
        self.assertEqual(result["case_id"], self.case_id)
        self.assertEqual(result["stage"], "characterizing")
        self.assertGreaterEqual(result["detections_count"], 1)
        self.assertGreater(result["primary_confidence"], 50.0)

        # 2. Assert case state transition
        self.assertEqual(self.mock_case.status, CaseStatus.CHARACTERIZING)

        # 3. Assert SlickDetection persistence in database
        detections = [obj for obj in self.stored_objects if isinstance(obj, SlickDetection)]
        self.assertEqual(len(detections), result["detections_count"])

        det = detections[0]
        self.assertEqual(str(det.case_id), self.case_id)
        self.assertGreater(det.area_m2, 10000.0)
        self.assertGreater(det.confidence, 0.0)  # Rule 1 compliance
        self.assertLessEqual(det.confidence, 100.0)
        self.assertEqual(det.sensor, "Sentinel-1 SAR IW")

        # 4. Assert PostGIS geometry validity
        poly = to_shape(det.polygon)
        self.assertTrue(poly.is_valid)
        self.assertFalse(poly.is_empty)

        centroid = to_shape(det.centroid)
        self.assertTrue(centroid.is_valid)
        self.assertTrue(poly.contains(centroid) or poly.touches(centroid))

        # 5. Assert progress updates were broadcasted
        self.assertGreaterEqual(mock_progress.call_count, 3)
        # Final broadcast should be 100%
        final_call = mock_progress.call_args_list[-1]
        self.assertEqual(final_call.kwargs["percent"], 100.0)
        self.assertEqual(final_call.kwargs["stage"], "characterizing")

    def test_run_tier1_segmentation_idempotency(self) -> None:
        """Test task idempotency: re-running clears prior detections before inserting fresh ones."""
        # First execution
        run_tier1_segmentation(
            case_id=self.case_id,
            scene_ref=str(self.tile_path),
            db_session=self.mock_db,
        )

        # Assert prior detections were cleared via query.delete()
        self.mock_db.query.return_value.filter.return_value.delete.assert_called()

    def test_run_tier1_segmentation_benchmark_fallback(self) -> None:
        """Test graceful fallback when scene_ref is None or invalid."""
        result = run_tier1_segmentation(
            case_id=self.case_id,
            scene_ref=None,  # Fallback to default fixture
            db_session=self.mock_db,
        )
        self.assertEqual(result["status"], "success")
        self.assertEqual(result["stage"], "characterizing")


if __name__ == "__main__":
    unittest.main()
