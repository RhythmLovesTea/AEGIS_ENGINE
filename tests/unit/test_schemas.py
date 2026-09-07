"""Unit tests verifying TASK-006 Pydantic Data Contracts and Rule Enforcement."""

import unittest
import uuid
from datetime import datetime, timezone
from pydantic import ValidationError

from backend.app.schemas import (
    AHPConfigResponse,
    AISCoverageEnum,
    AlternativeExplanationBase,
    CaseCreateRequest,
    CaseDetailResponse,
    CaseStatusEnum,
    DataSourceEnum,
    GeoJSONPoint,
    GeoJSONPolygon,
    OriginEstimateBase,
    SlickCharacterizationBase,
    SlickDetectionBase,
    SubScores,
    VesselCandidateBase,
    WhatIfRequest,
)


class TestPydanticSchemas(unittest.TestCase):
    def setUp(self) -> None:
        self.sample_point = GeoJSONPoint(coordinates=(72.85, 18.95))
        self.sample_polygon = GeoJSONPolygon(
            coordinates=[
                [
                    (72.80, 18.90),
                    (72.90, 18.90),
                    (72.90, 19.00),
                    (72.80, 19.00),
                    (72.80, 18.90),
                ]
            ]
        )
        self.now = datetime.now(timezone.utc)

    def test_rule_1_confidence_validation_bounds(self) -> None:
        """Enforce Rule 1: Confidence values must be bounded within [0.0, 100.0]."""
        # Valid confidence 85.5%
        detection = SlickDetectionBase(
            polygon=self.sample_polygon,
            centroid=self.sample_point,
            area_m2=150000.0,
            confidence=85.5,
            lookalike_risk=0.05,
            sensor="Sentinel-1 SAR IW",
            detection_time=self.now,
            data_source=DataSourceEnum.LIVE,
        )
        self.assertEqual(detection.confidence, 85.5)

        # Negative confidence must fail
        with self.assertRaises(ValidationError):
            SlickDetectionBase(
                polygon=self.sample_polygon,
                centroid=self.sample_point,
                area_m2=150000.0,
                confidence=-5.0,  # Invalid
                sensor="Sentinel-1 SAR IW",
                detection_time=self.now,
            )

        # Confidence > 100.0 must fail
        with self.assertRaises(ValidationError):
            SlickDetectionBase(
                polygon=self.sample_polygon,
                centroid=self.sample_point,
                area_m2=150000.0,
                confidence=105.0,  # Invalid
                sensor="Sentinel-1 SAR IW",
                detection_time=self.now,
            )

    def test_rule_2_vessel_candidate_sub_scores_required(self) -> None:
        """Enforce Rule 2: Sub-scores {spatial, temporal, kinematic, anomaly, type} are mandatory."""
        sub_scores = SubScores(
            spatial=92.0,
            temporal=88.5,
            kinematic=75.0,
            anomaly=60.0,
            type=100.0,
        )
        vessel = VesselCandidateBase(
            mmsi=419000123,
            imo=9123456,
            name="OCEAN VOYAGER",
            vessel_type="Tanker",
            s_culprit=85.2,
            confidence=90.0,
            sub_scores=sub_scores,
            anomaly_flags=["speed_drop_dumping"],
            ais_coverage=AISCoverageEnum.FULL,
        )
        self.assertEqual(vessel.sub_scores.spatial, 92.0)
        self.assertEqual(vessel.sub_scores.type, 100.0)

        # Omission of sub_scores must raise ValidationError
        with self.assertRaises(ValidationError):
            VesselCandidateBase(
                mmsi=419000123,
                name="OCEAN VOYAGER",
                vessel_type="Tanker",
                s_culprit=85.2,
                confidence=90.0,
                # Missing sub_scores!
            )

    def test_rule_4_ais_coverage_dark_gap(self) -> None:
        """Enforce Rule 4: AIS coverage flags including dark_gap and non_ais_unknown."""
        sub_scores = SubScores(
            spatial=80.0, temporal=70.0, kinematic=60.0, anomaly=90.0, type=75.0
        )
        vessel = VesselCandidateBase(
            mmsi=419000999,
            name="UNKNOWN GHOST",
            vessel_type="Cargo",
            s_culprit=77.0,
            confidence=72.0,
            sub_scores=sub_scores,
            anomaly_flags=["dark_transponder_gap"],
            ais_coverage=AISCoverageEnum.DARK_GAP,
        )
        self.assertEqual(vessel.ais_coverage, "dark_gap")

    def test_rule_7_ahp_config_consistency_ratio(self) -> None:
        """Enforce Rule 7: Consistency ratio must be < 0.10."""
        valid_matrix = [
            [1.0, 2.0, 3.0, 2.0, 4.0],
            [0.5, 1.0, 2.0, 1.0, 3.0],
            [0.333, 0.5, 1.0, 0.5, 2.0],
            [0.5, 1.0, 2.0, 1.0, 3.0],
            [0.25, 0.333, 0.5, 0.333, 1.0],
        ]
        valid_weights = {
            "spatial": 0.30,
            "temporal": 0.25,
            "kinematic": 0.15,
            "anomaly": 0.20,
            "type": 0.10,
        }
        # CR = 0.0094 < 0.10
        ahp = AHPConfigResponse(
            version="v1.0",
            pairwise_matrix=valid_matrix,
            weights=valid_weights,
            consistency_ratio=0.0094,
            created_at=self.now,
        )
        self.assertLess(ahp.consistency_ratio, 0.10)

        # Inconsistent matrix (CR >= 0.10) must fail validation
        with self.assertRaises(ValidationError):
            AHPConfigResponse(
                version="v1.0-inconsistent",
                pairwise_matrix=valid_matrix,
                weights=valid_weights,
                consistency_ratio=0.15,  # Violates CR < 0.10!
                created_at=self.now,
            )

    def test_case_create_and_what_if_schemas(self) -> None:
        """Verify CaseCreateRequest and WhatIfRequest parameter overrides."""
        create_req = CaseCreateRequest(
            region=self.sample_polygon,
            source_scene_ref="S1A_IW_GRDH_1SDV_20260907",
            created_by="lead_investigator",
        )
        self.assertEqual(create_req.created_by, "lead_investigator")

        whatif_req = WhatIfRequest(
            t_age_override_hours=18.5,
            wind_drift_factor=0.035,
            origin_search_sigma=2.5,
            custom_ahp_weights={"spatial": 0.40, "temporal": 0.20},
        )
        self.assertEqual(whatif_req.wind_drift_factor, 0.035)


if __name__ == "__main__":
    unittest.main()
