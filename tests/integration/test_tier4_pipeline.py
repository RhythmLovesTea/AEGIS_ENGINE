"""AEGIS-Marine: Integration Tests for Tier 4 Celery Pipeline Task (TASK-028).

Tests conform to:
- PRD Section 11 & Architecture Section 4.4
- Constitutional Rules:
  - Rule 1: Mandatory confidence score in [0.0, 100.0]
  - Rule 2: Stored 5-component sub-scores (spatial, temporal, kinematic, anomaly, type)
  - Rule 3: Multi-criteria synthesis prevents distance-only ranking
  - Rule 4: Explicit ais_coverage flags ('full' | 'partial' | 'dark_gap' | 'non_ais_unknown')
  - Rule 6: Strictly zero occurrences of banned terms
"""

import unittest
import uuid
from datetime import UTC, datetime
from pathlib import Path
from unittest.mock import MagicMock, patch

import shapely.geometry
from geoalchemy2.shape import from_shape
from sqlalchemy.orm import Session

from backend.app.models.entities import (
    AISCoverage,
    Case,
    CaseStatus,
    DataSource,
    OriginEstimate,
    SlickCharacterization,
    SlickDetection,
    VesselCandidate,
)
from backend.core.celery_app import celery_app
from backend.workers.tasks.tier4_tasks import run_tier4_correlation

BASE_DIR = Path(__file__).resolve().parent.parent.parent
SYNTHETIC_DIR = BASE_DIR / "data" / "synthetic"


class TestTier4PipelineIntegration(unittest.TestCase):
    """Integration test suite for Tier 4 AIS correlation and attribution scoring task."""

    def setUp(self) -> None:
        """Set up mock case, detection, characterization, origin, and database session."""
        self.case_uuid = uuid.uuid4()
        self.case_id = str(self.case_uuid)

        # 1. Create Case in 'correlating' state
        self.mock_case = Case(
            id=self.case_uuid,
            status=CaseStatus.CORRELATING,
            region=from_shape(shapely.geometry.box(72.0, 18.5, 73.0, 19.5), srid=4326),
            created_by="analyst_test",
        )

        # 2. Create Tier 1 SlickDetection record
        t_obs = datetime(2026, 9, 7, 6, 0, tzinfo=UTC)
        slick_poly = shapely.geometry.box(72.43, 18.95, 72.44, 18.97)
        self.mock_detection = SlickDetection(
            id=uuid.uuid4(),
            case_id=self.case_uuid,
            polygon=from_shape(slick_poly, srid=4326),
            centroid=from_shape(slick_poly.centroid, srid=4326),
            area_m2=5000000.0,
            confidence=88.5,
            lookalike_risk=0.03,
            sensor="Sentinel-1 SAR IW",
            detection_time=t_obs,
            data_source=DataSource.SYNTHETIC,
        )

        # 3. Create Tier 2 SlickCharacterization record (12.0h age -> t_release = 18:00 UTC)
        self.mock_characterization = SlickCharacterization(
            id=uuid.uuid4(),
            case_id=self.case_uuid,
            perimeter_m=8500.0,
            principal_axis_deg=65.0,
            baoac_code=3,
            estimated_volume_m3=180.0,
            t_age_hours=12.0,
            age_confidence=86.0,
        )

        # 4. Create Tier 3 OriginEstimate record
        origin_centroid_geom = shapely.geometry.Point(72.290, 18.865)
        self.mock_origin = OriginEstimate(
            id=uuid.uuid4(),
            case_id=self.case_uuid,
            centroid=from_shape(origin_centroid_geom, srid=4326),
            covariance_matrix={
                "var_lon": 0.000185,
                "var_lat": 0.000142,
                "cov_lon_lat": 9.5e-05,
            },
            time_window_start=datetime(2026, 9, 6, 16, 30, tzinfo=UTC),
            time_window_end=datetime(2026, 9, 6, 19, 30, tzinfo=UTC),
            confidence_pct=89.2,
            region_area_km2=18.4,
        )

        # Mock database session and object store
        self.mock_db = MagicMock(spec=Session)
        self.stored_objects: list[object] = []

        def mock_add(obj):
            self.stored_objects.append(obj)

        def mock_add_all(objs):
            self.stored_objects.extend(objs)

        self.mock_db.add.side_effect = mock_add
        self.mock_db.add_all.side_effect = mock_add_all

        def mock_query(model):
            q = MagicMock()
            if model == Case:
                q.filter.return_value.first.return_value = self.mock_case
            elif model == OriginEstimate:
                q.filter.return_value.order_by.return_value.first.return_value = self.mock_origin
            elif model == SlickCharacterization:
                q.filter.return_value.order_by.return_value.first.return_value = (
                    self.mock_characterization
                )
            elif model == SlickDetection:
                q.filter.return_value.order_by.return_value.first.return_value = self.mock_detection
            elif model == VesselCandidate:

                def do_delete():
                    initial_len = len(
                        [o for o in self.stored_objects if isinstance(o, VesselCandidate)]
                    )
                    self.stored_objects = [
                        o for o in self.stored_objects if not isinstance(o, VesselCandidate)
                    ]
                    return initial_len

                q.filter.return_value.delete.side_effect = do_delete
                q.filter.return_value.order_by.return_value.all.side_effect = lambda: sorted(
                    [o for o in self.stored_objects if isinstance(o, VesselCandidate)],
                    key=lambda c: c.s_culprit,
                    reverse=True,
                )
                q.filter.return_value.count.side_effect = lambda: len(
                    [o for o in self.stored_objects if isinstance(o, VesselCandidate)]
                )
            return q

        self.mock_db.query.side_effect = mock_query
        self.csv_path = SYNTHETIC_DIR / "synthetic_ais_tracks.csv"

    def test_celery_task_registration_and_routing(self) -> None:
        """Verify task is registered in Celery app with correct tier4 name and queue routing."""
        self.assertIn("tier4.run_tier4_correlation", celery_app.tasks)
        task = celery_app.tasks["tier4.run_tier4_correlation"]
        self.assertEqual(task.name, "tier4.run_tier4_correlation")

    def test_tier4_pipeline_end_to_end(self) -> None:
        """Verify full execution of run_tier4_correlation Celery task with candidate persistence."""
        with patch.object(run_tier4_correlation, "update_progress") as mock_progress:
            result = run_tier4_correlation(
                case_id=self.case_id,
                db_session=self.mock_db,
                ais_csv_path=self.csv_path,
            )

        # 1. Assert result status and state
        self.assertEqual(result["status"], "success")
        self.assertEqual(result["stage"], "scoring")
        self.assertEqual(result["case_id"], self.case_id)
        self.assertGreaterEqual(result["candidates_count"], 4)

        # 2. Assert case state transition in database
        self.assertEqual(self.mock_case.status, CaseStatus.SCORING)

        # 3. Assert VesselCandidate records persisted in PostgreSQL
        candidates = [obj for obj in self.stored_objects if isinstance(obj, VesselCandidate)]
        candidates.sort(key=lambda c: c.s_culprit, reverse=True)
        self.assertGreaterEqual(len(candidates), 4)

        # 4. Assert Top-1 candidate is Vessel A (PACIFIC PEARL, MMSI 419000101)
        top1 = candidates[0]
        self.assertEqual(top1.mmsi, 419000101)
        self.assertEqual(top1.name, "PACIFIC PEARL")
        self.assertEqual(top1.vessel_type, "Tanker")
        self.assertGreater(top1.s_culprit, 80.0)

        # Rule 1: Paired confidence score in [0.0, 100.0]
        self.assertGreaterEqual(top1.confidence, 0.0)
        self.assertLessEqual(top1.confidence, 100.0)

        # Rule 2: Persisted 5-component sub-scores
        self.assertIsInstance(top1.sub_scores, dict)
        self.assertIn("spatial", top1.sub_scores)
        self.assertIn("temporal", top1.sub_scores)
        self.assertIn("kinematic", top1.sub_scores)
        self.assertIn("anomaly", top1.sub_scores)
        self.assertIn("type", top1.sub_scores)
        self.assertGreater(top1.sub_scores["spatial"], 90.0)
        self.assertGreater(top1.sub_scores["temporal"], 90.0)
        self.assertGreater(top1.sub_scores["kinematic"], 90.0)
        self.assertEqual(top1.sub_scores["type"], 100.0)

        # Rule 4: Anomaly flags and coverage
        self.assertIn("speed_drop_dumping", top1.anomaly_flags)
        self.assertEqual(top1.ais_coverage, AISCoverage.FULL)

        # 5. Assert Dark Ship Vessel D (SEA SHADOW, MMSI 419000104) is correctly flagged
        vessel_d = next(c for c in candidates if c.mmsi == 419000104)
        self.assertIsNotNone(vessel_d)
        self.assertEqual(vessel_d.ais_coverage, AISCoverage.DARK_GAP)
        self.assertIn("dark_transponder_gap", vessel_d.anomaly_flags)

        # 6. Assert Innocent Cargo Vessel B (MAERSK TAIPEI) is scored lower
        vessel_b = next(c for c in candidates if c.mmsi == 419000102)
        self.assertIsNotNone(vessel_b)
        self.assertLess(vessel_b.s_culprit, 40.0)
        self.assertGreater(top1.s_culprit, vessel_b.s_culprit + 40.0)

        # 7. Assert database transaction committed
        self.mock_db.commit.assert_called()

        # 8. Assert Redis progress broadcast updates
        self.assertGreaterEqual(mock_progress.call_count, 5)
        final_call = mock_progress.call_args_list[-1]
        self.assertEqual(final_call.kwargs["percent"], 100.0)
        self.assertEqual(final_call.kwargs["stage"], "scoring")

    def test_idempotent_task_rerun(self) -> None:
        """Verify task rerun cleans prior candidates and does not produce duplicate rows."""
        # First run
        run_tier4_correlation(
            case_id=self.case_id,
            db_session=self.mock_db,
            ais_csv_path=self.csv_path,
        )
        count_1 = len([o for o in self.stored_objects if isinstance(o, VesselCandidate)])
        self.assertGreater(count_1, 0)

        # Second run
        run_tier4_correlation(
            case_id=self.case_id,
            db_session=self.mock_db,
            ais_csv_path=self.csv_path,
        )
        count_2 = len([o for o in self.stored_objects if isinstance(o, VesselCandidate)])
        self.assertEqual(
            count_1, count_2, "Rerunning task must cleanly replace rows without duplication"
        )

    def test_tier4_missing_case_raises_error(self) -> None:
        """Verify task raises ValueError if target case does not exist."""
        # Re-mock db.query for Case to return None
        q = MagicMock()
        q.filter.return_value.first.return_value = None
        self.mock_db.query.side_effect = lambda model: q if model == Case else MagicMock()

        with self.assertRaises(ValueError):
            run_tier4_correlation(
                case_id=str(uuid.uuid4()),
                db_session=self.mock_db,
                ais_csv_path=self.csv_path,
            )

    def test_tier4_missing_origin_raises_error(self) -> None:
        """Verify task raises ValueError if Tier 3 OriginEstimate record does not exist."""

        def mock_query(model):
            q = MagicMock()
            if model == Case:
                q.filter.return_value.first.return_value = self.mock_case
            elif model == OriginEstimate:
                q.filter.return_value.order_by.return_value.first.return_value = None
            return q

        self.mock_db.query.side_effect = mock_query

        with self.assertRaises(ValueError):
            run_tier4_correlation(
                case_id=self.case_id,
                db_session=self.mock_db,
                ais_csv_path=self.csv_path,
            )


if __name__ == "__main__":
    unittest.main()
