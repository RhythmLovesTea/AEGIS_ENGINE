"""AEGIS-Marine: Unit tests for Alternative Explanation Engine (TASK-030).

Tests conform to:
- PRD Section 11 & Architecture Section 4.5 (Feature 7, P2)
- Constitutional Rules:
  - Rule 1: Mandatory confidence score in [0.0, 100.0] on all hypotheses
  - Rule 4: Surfacing unlisted and dark-ship contacts
  - Rule 5: Always persist at least one alternative explanation hypothesis before case is ready
  - Rule 6: Strictly zero occurrences of banned terms verified via check_content
"""

import unittest
import uuid
from pathlib import Path
from unittest.mock import MagicMock

import shapely.geometry
from geoalchemy2.shape import from_shape
from scripts.lint_banned_terms import check_content
from sqlalchemy.orm import Session

from backend.app.models.entities import (
    AISCoverage,
    AlternativeExplanation,
    Case,
    CaseStatus,
    DataSource,
    OriginEstimate,
    SlickDetection,
    VesselCandidate,
)
from backend.services.explainability.alternative_engine import (
    AlternativeExplanationEngine,
    assert_no_banned_terms,
    haversine_km,
    initial_bearing_deg,
)

BASE_DIR = Path(__file__).resolve().parent.parent.parent
GEOJSON_PATH = BASE_DIR / "data" / "geospatial" / "natural_seeps.geojson"


class TestAlternativeExplanationEngine(unittest.TestCase):
    """Unit test suite for Alternative Explanation Engine."""

    def setUp(self) -> None:
        self.engine = AlternativeExplanationEngine(seep_catalog_path=GEOJSON_PATH)
        self.case_uuid = uuid.uuid4()
        self.case_id = str(self.case_uuid)

    def test_seep_catalog_loading_from_geojson(self) -> None:
        """Verify natural seep catalog loads GeoJSON features correctly."""
        self.assertGreater(len(self.engine.seeps), 0)
        seep_ids = [s["seep_id"] for s in self.engine.seeps]
        self.assertIn("SEEP-IND-BH01", seep_ids)
        self.assertIn("SEEP-IND-BH02", seep_ids)
        self.assertIn("SEEP-IND-BH03", seep_ids)

        # Fallback catalog loading on missing file
        fallback_engine = AlternativeExplanationEngine(
            seep_catalog_path="/tmp/non_existent.geojson"
        )
        self.assertGreater(len(fallback_engine.seeps), 0)

    def test_natural_seep_proximity_scoring(self) -> None:
        """Verify distance-based exponential decay scoring for geological seeps."""
        # 1. Directly on top of SEEP-IND-BH03 (72.30, 18.88)
        res_direct = self.engine.evaluate_natural_seep(target_coords=(72.30, 18.88))
        self.assertEqual(res_direct["hypothesis"], "natural_seep")
        self.assertGreater(res_direct["score"], 95.0)
        self.assertLess(res_direct["evidence"]["distance_km"], 0.1)
        self.assertIn("Close proximity", res_direct["evidence"]["rationale"])

        # 2. Approximately 3.0 km away (1 tau decay -> ~36.8%)
        # 1 deg lat ~ 111 km -> 0.027 deg ~ 3.0 km
        res_3km = self.engine.evaluate_natural_seep(target_coords=(72.30, 18.907))
        self.assertAlmostEqual(res_3km["evidence"]["distance_km"], 3.0, delta=0.5)
        self.assertGreater(res_3km["score"], 25.0)
        self.assertLess(res_3km["score"], 50.0)

        # 3. Far away in open sea: (72.30, 18.00)
        res_far = self.engine.evaluate_natural_seep(target_coords=(72.30, 18.00))
        self.assertGreater(res_far["evidence"]["distance_km"], 50.0)
        self.assertLess(res_far["score"], 0.1)
        self.assertIn("Significant separation", res_far["evidence"]["rationale"])

    def test_imaging_artifact_evaluation(self) -> None:
        """Verify SAR false-alarm lookalike evaluation with incidence angle and wind factors."""
        # 1. Clean detection (low lookalike risk, nominal angle, stable wind)
        clean_art = self.engine.evaluate_imaging_artifact(
            lookalike_risk=0.03,
            incidence_angle_deg=34.0,
            wind_speed_ms=6.0,
        )
        self.assertEqual(clean_art["hypothesis"], "imaging_artifact")
        self.assertLess(clean_art["score"], 5.0)
        self.assertIn("Low imaging artifact", clean_art["evidence"]["rationale"])

        # 2. High lookalike risk
        high_art = self.engine.evaluate_imaging_artifact(
            lookalike_risk=0.75,
            incidence_angle_deg=34.0,
            wind_speed_ms=6.0,
        )
        self.assertGreater(high_art["score"], 70.0)

        # 3. Steep incidence angle (< 25 deg) and low wind (< 3 m/s) elevate score
        boosted_art = self.engine.evaluate_imaging_artifact(
            lookalike_risk=0.20,
            incidence_angle_deg=22.0,
            wind_speed_ms=2.2,
        )
        self.assertGreater(boosted_art["score"], 30.0)
        self.assertGreater(boosted_art["evidence"]["angle_factor"], 1.0)
        self.assertGreater(boosted_art["evidence"]["wind_factor"], 1.0)

    def test_non_ais_vessel_hypothesis(self) -> None:
        """Verify unlisted non-AIS and dark target hypothesis evaluation."""
        # 1. Baseline: clear corridor, full AIS, zero radar contacts
        res_baseline = self.engine.evaluate_non_ais_vessel(
            candidate_count=5,
            dark_gap_count=0,
            unidentified_radar_contacts=0,
            regional_ais_coverage="dense",
        )
        self.assertEqual(res_baseline["hypothesis"], "non_ais_vessel")
        self.assertLessEqual(res_baseline["score"], 20.0)

        # 2. Elevated: 1 dark-gap ship and partial coverage
        res_dark = self.engine.evaluate_non_ais_vessel(
            candidate_count=4,
            dark_gap_count=1,
            unidentified_radar_contacts=0,
            regional_ais_coverage="partial",
        )
        self.assertGreater(res_dark["score"], 40.0)

        # 3. Strong non-AIS indicator: unidentified radar contact present
        res_radar = self.engine.evaluate_non_ais_vessel(
            candidate_count=4,
            dark_gap_count=1,
            unidentified_radar_contacts=1,
            regional_ais_coverage="poor",
        )
        self.assertGreaterEqual(res_radar["score"], 75.0)
        self.assertIn("Significant non-AIS", res_radar["evidence"]["rationale"])

    def test_rule_5_always_produces_and_persists_hypotheses(self) -> None:
        """Rule 5: Verify all 3 alternative hypotheses are produced and persisted in DB."""
        mock_db = MagicMock(spec=Session)

        # Case entity
        mock_case = Case(
            id=self.case_uuid,
            status=CaseStatus.SCORING,
            region=from_shape(shapely.geometry.box(72.0, 18.5, 73.0, 19.5), srid=4326),
            created_by="analyst_test",
        )

        # Origin estimate
        origin_pt = shapely.geometry.Point(72.290, 18.865)
        mock_origin = OriginEstimate(
            id=uuid.uuid4(),
            case_id=self.case_uuid,
            centroid=from_shape(origin_pt, srid=4326),
            confidence_pct=89.2,
        )

        # Detection
        slick_poly = shapely.geometry.box(72.43, 18.95, 72.44, 18.97)
        mock_det = SlickDetection(
            id=uuid.uuid4(),
            case_id=self.case_uuid,
            polygon=from_shape(slick_poly, srid=4326),
            centroid=from_shape(slick_poly.centroid, srid=4326),
            lookalike_risk=0.04,
            confidence=88.5,
            sensor="Sentinel-1 SAR IW",
            data_source=DataSource.SYNTHETIC,
        )

        # Candidate with high attribution score (88.5)
        mock_cand = VesselCandidate(
            id=uuid.uuid4(),
            case_id=self.case_uuid,
            mmsi=419000101,
            name="PACIFIC PEARL",
            vessel_type="Tanker",
            s_culprit=88.5,
            confidence=89.0,
            sub_scores={
                "spatial": 98.2,
                "temporal": 94.5,
                "kinematic": 92.0,
                "anomaly": 40.0,
                "type": 100.0,
            },
            anomaly_flags=["speed_drop_dumping"],
            ais_coverage=AISCoverage.FULL,
        )

        stored_entities: list[AlternativeExplanation] = []

        def mock_add(obj):
            if isinstance(obj, AlternativeExplanation):
                stored_entities.append(obj)

        mock_db.add.side_effect = mock_add

        def mock_query(model):
            q = MagicMock()
            if model == Case:
                q.filter.return_value.first.return_value = mock_case
            elif model == OriginEstimate:
                q.filter.return_value.order_by.return_value.first.return_value = mock_origin
            elif model == SlickDetection:
                q.filter.return_value.order_by.return_value.first.return_value = mock_det
            elif model == VesselCandidate:
                q.filter.return_value.all.return_value = [mock_cand]
            elif model == AlternativeExplanation:
                q.filter.return_value.delete.return_value = 1
            return q

        mock_db.query.side_effect = mock_query

        # Execute evaluation and persistence
        results = self.engine.evaluate_and_persist_case(
            db=mock_db,
            case_id=self.case_id,
        )

        # Rule 5 check: at least 1 (and here all 3) alternative hypotheses produced
        self.assertGreaterEqual(len(results), 1)
        self.assertEqual(len(results), 3)

        hypotheses_names = [r.hypothesis for r in results]
        self.assertIn("natural_seep", hypotheses_names)
        self.assertIn("imaging_artifact", hypotheses_names)
        self.assertIn("non_ais_vessel", hypotheses_names)

        # Verify DB add and commit were invoked
        self.assertEqual(len(stored_entities), 3)
        mock_db.commit.assert_called()

    def test_rule_1_paired_confidence_bounds(self) -> None:
        """Rule 1: Verify mandatory confidence score in [0.0, 100.0] on every hypothesis."""
        hypotheses = self.engine.evaluate_case_hypotheses(
            origin_coords=(72.290, 18.865),
            lookalike_risk=0.05,
            incidence_angle_deg=34.0,
            wind_speed_ms=5.0,
        )
        self.assertEqual(len(hypotheses), 3)
        for h in hypotheses:
            self.assertIn("confidence", h)
            self.assertGreaterEqual(h["confidence"], 0.0)
            self.assertLessEqual(h["confidence"], 100.0)

    def test_rule_6_zero_banned_terms(self) -> None:
        """Rule 6: Verify strictly zero occurrences of banned terms in all rationales and text."""
        dummy_path = Path("test_alternatives.py")
        hypotheses = self.engine.evaluate_case_hypotheses(
            origin_coords=(72.290, 18.865),
            lookalike_risk=0.45,
            incidence_angle_deg=22.0,
            wind_speed_ms=2.0,
            candidate_count=4,
            dark_gap_count=2,
            unidentified_radar_contacts=1,
        )

        for h in hypotheses:
            rat = h["evidence"].get("rationale", "")
            self.assertGreater(len(rat), 0)
            violations = check_content(rat, dummy_path)
            self.assertEqual(
                len(violations),
                0,
                f"Banned term violation in {h['hypothesis']}: {[v.rule_name for v in violations]}",
            )
            assert_no_banned_terms(rat, h["hypothesis"])

    def test_haversine_and_bearing_helpers(self) -> None:
        """Verify mathematical helper functions for distance and initial bearing."""
        # Distance between (0, 0) and (0, 1) deg is ~ 111.2 km
        d = haversine_km(0.0, 0.0, 0.0, 1.0)
        self.assertAlmostEqual(d, 111.19, delta=0.5)

        # Bearing from (0, 0) due north (0, 1) is 0 deg
        b_north = initial_bearing_deg(0.0, 0.0, 0.0, 1.0)
        self.assertAlmostEqual(b_north, 0.0, places=1)

        # Bearing from (0, 0) due east (1, 0) is 90 deg
        b_east = initial_bearing_deg(0.0, 0.0, 1.0, 0.0)
        self.assertAlmostEqual(b_east, 90.0, places=1)


if __name__ == "__main__":
    unittest.main()
