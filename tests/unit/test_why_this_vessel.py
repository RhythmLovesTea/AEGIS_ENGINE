"""AEGIS-Marine: Unit tests for Why-This-Vessel Composer (TASK-029).

Tests conform to:
- PRD Section 11 & Architecture Section 4.5 (Feature 1, D1)
- Constitutional Rules:
  - Rule 1: Mandatory confidence score in [0.0, 100.0]
  - Rule 2: Sub-scores and evidence breakdown directly derived from stored fields
  - Rule 3: Multi-criteria synthesis (not distance-only)
  - Rule 4: Explicit surfacing of transponder dark gaps and non-AIS targets
  - Rule 6: Strictly zero occurrences of banned terms verified via check_content
  - Rule 7: Transparent AHP weight breakdown in bar and radar charts
"""

import unittest
import uuid
from datetime import UTC, datetime
from pathlib import Path
from unittest.mock import MagicMock

import shapely.geometry
from geoalchemy2.shape import from_shape
from scripts.lint_banned_terms import check_content
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
from backend.services.explainability.why_this_vessel import (
    WhyThisVesselComposer,
    assert_no_banned_terms,
)


class TestWhyThisVesselComposer(unittest.TestCase):
    """Unit test suite for 'Why This Vessel?' Forensic Explainability Service."""

    def setUp(self) -> None:
        self.composer = WhyThisVesselComposer(tau_hours=1.5)
        self.case_uuid = uuid.uuid4()
        self.case_id = str(self.case_uuid)

        # Benchmark Suspect: Vessel A (PACIFIC PEARL, MMSI 419000101, Tanker)
        self.vessel_a_dict = {
            "mmsi": 419000101,
            "imo": 9234567,
            "name": "PACIFIC PEARL",
            "flag_state": "Panama",
            "vessel_type": "Tanker",
            "s_culprit": 88.5,
            "confidence": 89.0,
            "sub_scores": {
                "spatial": 98.2,
                "temporal": 94.5,
                "kinematic": 92.0,
                "anomaly": 40.0,
                "type": 100.0,
                "details": {
                    "d_m": 0.19,
                    "cpa_dist_km": 0.25,
                    "delta_hours": 0.09,
                    "cog_deg": 68.0,
                    "slick_orientation_deg": 65.0,
                    "heading_difference_deg": 3.0,
                    "speed_kts": 6.2,
                    "a_speed": 1.0,
                    "a_course": 0.0,
                    "a_dark": 0.0,
                },
            },
            "anomaly_flags": ["speed_drop_dumping"],
            "ais_coverage": "full",
            "rank": 1,
            "evidence_refs": [
                "Spatial CPA: d_CPA = 0.25 km (Mahalanobis D_M = 0.19)",
                "Discharge Band: Vessel slowed to 6.2 kts in [4, 8] kt dumping window",
            ],
        }

        # Benchmark Dark Gap Ship: Vessel D (SEA SHADOW, MMSI 419000104)
        self.vessel_d_dict = {
            "mmsi": 419000104,
            "imo": None,
            "name": "SEA SHADOW",
            "flag_state": "Unknown",
            "vessel_type": "Tanker",
            "s_culprit": 72.0,
            "confidence": 75.0,
            "sub_scores": {
                "spatial": 70.0,
                "temporal": 65.0,
                "kinematic": 60.0,
                "anomaly": 70.0,
                "type": 100.0,
                "details": {
                    "d_m": 0.85,
                    "cpa_dist_km": 1.15,
                    "delta_hours": 0.65,
                    "a_speed": 0.0,
                    "a_course": 0.0,
                    "a_dark": 1.0,
                    "gap_duration_hours": 3.5,
                },
            },
            "anomaly_flags": ["dark_transponder_gap"],
            "ais_coverage": "dark_gap",
            "rank": 2,
        }

        # Benchmark Innocent Vessel: Vessel B (MAERSK TAIPEI, Cargo, low score)
        self.vessel_b_dict = {
            "mmsi": 419000102,
            "imo": 9182736,
            "name": "MAERSK TAIPEI",
            "flag_state": "Singapore",
            "vessel_type": "Cargo",
            "s_culprit": 32.5,
            "confidence": 85.0,
            "sub_scores": {
                "spatial": 12.0,
                "temporal": 15.0,
                "kinematic": 10.0,
                "anomaly": 0.0,
                "type": 75.0,
                "details": {
                    "d_m": 2.05,
                    "cpa_dist_km": 2.8,
                    "delta_hours": 2.85,
                    "cog_deg": 145.0,
                    "slick_orientation_deg": 65.0,
                    "heading_difference_deg": 80.0,
                    "speed_kts": 16.5,
                    "a_speed": 0.0,
                    "a_course": 0.0,
                    "a_dark": 0.0,
                },
            },
            "anomaly_flags": [],
            "ais_coverage": "full",
            "rank": 3,
        }

    def test_spatial_breakdown_sigma_bands(self) -> None:
        """Verify spatial decomposition maps Mahalanobis D_M to 1-sigma, 2-sigma, 3-sigma bands."""
        # 1. Inside 1-sigma core (S_spatial = 98.2 -> D_M = 0.19 <= 1.0)
        payload = self.composer.compose_from_candidate(self.vessel_a_dict)
        spatial = payload.spatial_breakdown
        self.assertIsNotNone(spatial)
        self.assertEqual(spatial.sigma_band, "1sigma")
        self.assertTrue(spatial.inside_1sigma)
        self.assertTrue(spatial.inside_2sigma)
        self.assertTrue(spatial.inside_3sigma)
        self.assertLessEqual(spatial.mahalanobis_distance, 1.0)
        self.assertIn("1-sigma", spatial.rationale)

        # 2. Inside 2-sigma band (S_spatial = 13.53 -> D_M ~ 2.0)
        cand_2sigma = dict(self.vessel_a_dict)
        cand_2sigma["sub_scores"] = {
            "spatial": 13.53,
            "temporal": 50.0,
            "kinematic": 50.0,
            "anomaly": 0.0,
            "type": 50.0,
            "details": {"d_m": 1.8},
        }
        p2 = self.composer.compose_from_candidate(cand_2sigma)
        s2 = p2.spatial_breakdown
        self.assertIsNotNone(s2)
        self.assertEqual(s2.sigma_band, "2sigma")
        self.assertFalse(s2.inside_1sigma)
        self.assertTrue(s2.inside_2sigma)
        self.assertTrue(s2.inside_3sigma)
        self.assertIn("2-sigma", s2.rationale)

        # 3. Inside 3-sigma band (D_M ~ 2.6)
        cand_3sigma = dict(self.vessel_a_dict)
        cand_3sigma["sub_scores"] = {
            "spatial": 3.0,
            "temporal": 50.0,
            "kinematic": 50.0,
            "anomaly": 0.0,
            "type": 50.0,
            "details": {"d_m": 2.6},
        }
        p3 = self.composer.compose_from_candidate(cand_3sigma)
        s3 = p3.spatial_breakdown
        self.assertIsNotNone(s3)
        self.assertEqual(s3.sigma_band, "3sigma")
        self.assertFalse(s3.inside_1sigma)
        self.assertFalse(s3.inside_2sigma)
        self.assertTrue(s3.inside_3sigma)
        self.assertIn("3-sigma", s3.rationale)

        # 4. Outside 3-sigma boundary (D_M = 4.0)
        cand_out = dict(self.vessel_a_dict)
        cand_out["sub_scores"] = {
            "spatial": 0.03,
            "temporal": 50.0,
            "kinematic": 50.0,
            "anomaly": 0.0,
            "type": 50.0,
            "details": {"d_m": 4.0},
        }
        p_out = self.composer.compose_from_candidate(cand_out)
        s_out = p_out.spatial_breakdown
        self.assertIsNotNone(s_out)
        self.assertEqual(s_out.sigma_band, "outside_3sigma")
        self.assertFalse(s_out.inside_1sigma)
        self.assertFalse(s_out.inside_2sigma)
        self.assertFalse(s_out.inside_3sigma)

    def test_temporal_breakdown_decay(self) -> None:
        """Verify temporal decomposition calculates delta minutes and exponential decay factor."""
        payload = self.composer.compose_from_candidate(self.vessel_a_dict)
        temporal = payload.temporal_breakdown
        self.assertIsNotNone(temporal)
        self.assertEqual(temporal.sub_score, 94.5)
        self.assertGreater(temporal.decay_factor, 0.90)
        self.assertLess(temporal.delta_minutes, 15.0)
        self.assertEqual(temporal.tau_hours, 1.5)
        self.assertIn("temporal coincidence", temporal.rationale.lower())

        # Test larger time offset (Vessel B)
        payload_b = self.composer.compose_from_candidate(self.vessel_b_dict)
        tb = payload_b.temporal_breakdown
        self.assertIsNotNone(tb)
        self.assertGreater(tb.delta_minutes, 60.0)
        self.assertLess(tb.decay_factor, 0.30)

    def test_kinematic_breakdown_alignment(self) -> None:
        """Verify kinematic breakdown computes heading differences and speed wake modulation."""
        payload = self.composer.compose_from_candidate(self.vessel_a_dict)
        kinematic = payload.kinematic_breakdown
        self.assertIsNotNone(kinematic)
        self.assertEqual(kinematic.heading_difference_deg, 3.0)
        self.assertEqual(kinematic.vessel_speed_kts, 6.2)
        self.assertGreaterEqual(kinematic.speed_modulation_factor, 0.9)
        self.assertIn("aligned", kinematic.rationale.lower())

    def test_anomaly_breakdown_flags(self) -> None:
        """Verify anomaly decomposition handles speed dumping drops and transponder gaps."""
        # Vessel A: speed drop
        pa = self.composer.compose_from_candidate(self.vessel_a_dict)
        anom_a = pa.anomaly_breakdown
        self.assertIsNotNone(anom_a)
        self.assertTrue(anom_a.speed_loitering_detected)
        self.assertFalse(anom_a.dark_gap_detected)
        self.assertEqual(anom_a.speed_anomaly_score, 1.0)
        self.assertIn("speed reduction", anom_a.rationale.lower())

        # Vessel D: dark transponder gap
        pd = self.composer.compose_from_candidate(self.vessel_d_dict)
        anom_d = pd.anomaly_breakdown
        self.assertIsNotNone(anom_d)
        self.assertFalse(anom_d.speed_loitering_detected)
        self.assertTrue(anom_d.dark_gap_detected)
        self.assertEqual(anom_d.dark_gap_score, 1.0)
        self.assertGreater(len(anom_d.dark_gap_intervals), 0)
        self.assertIn("transponder silence", anom_d.rationale.lower())

        # Vessel B: no anomalies
        pb = self.composer.compose_from_candidate(self.vessel_b_dict)
        anom_b = pb.anomaly_breakdown
        self.assertIsNotNone(anom_b)
        self.assertFalse(anom_b.speed_loitering_detected)
        self.assertFalse(anom_b.dark_gap_detected)
        self.assertEqual(anom_b.sub_score, 0.0)

    def test_type_breakdown_and_imo(self) -> None:
        """Verify vessel type category, prior risk, and IMO registry references."""
        pa = self.composer.compose_from_candidate(self.vessel_a_dict)
        v_type = pa.type_breakdown
        self.assertIsNotNone(v_type)
        self.assertEqual(v_type.vessel_type, "Tanker")
        self.assertEqual(v_type.prior_risk_score, 100.0)
        self.assertEqual(v_type.imo, 9234567)
        self.assertEqual(v_type.flag_state, "Panama")
        self.assertIn("IMO 9234567", v_type.registry_reference)

    def test_radar_chart_payload(self) -> None:
        """Verify 5-axis polar coordinates for radar chart visualization."""
        pa = self.composer.compose_from_candidate(self.vessel_a_dict)
        radar = pa.radar_data
        self.assertEqual(len(radar), 5)
        keys = [p["key"] for p in radar]
        self.assertEqual(keys, ["spatial", "temporal", "kinematic", "anomaly", "type"])
        weights_sum = sum(p["weight"] for p in radar)
        self.assertAlmostEqual(weights_sum, 1.0, places=2)

        # Check values match sub-scores
        self.assertEqual(radar[0]["value"], 98.2)
        self.assertEqual(radar[1]["value"], 94.5)
        self.assertEqual(radar[4]["value"], 100.0)

    def test_bar_chart_payload(self) -> None:
        """Verify weighted contribution bar chart items match composite score sum."""
        pa = self.composer.compose_from_candidate(self.vessel_a_dict)
        bars = pa.bar_data
        self.assertEqual(len(bars), 5)
        total_weighted = sum(item.weighted_contribution for item in bars)
        # S_culprit is weighted sum
        expected_culprit = 0.30 * 98.2 + 0.25 * 94.5 + 0.15 * 92.0 + 0.20 * 40.0 + 0.10 * 100.0
        self.assertAlmostEqual(total_weighted, expected_culprit, delta=0.5)

    def test_evidence_checklist_generation(self) -> None:
        """Verify evidence checklist items and Rule 1 paired confidence."""
        pa = self.composer.compose_from_candidate(self.vessel_a_dict)
        checklist = pa.evidence_checklist
        self.assertEqual(len(checklist), 5)

        for item in checklist:
            self.assertIn(item.status, ["positive_indicator", "neutral", "unlikely"])
            # Rule 1: Confidence in [0.0, 100.0]
            self.assertGreaterEqual(item.confidence_pct, 0.0)
            self.assertLessEqual(item.confidence_pct, 100.0)

        # Vessel A spatial and temporal should be positive indicators
        spatial_item = next(c for c in checklist if "Spatial" in c.check)
        self.assertEqual(spatial_item.status, "positive_indicator")

        temporal_item = next(c for c in checklist if "Temporal" in c.check)
        self.assertEqual(temporal_item.status, "positive_indicator")

    def test_zero_banned_terms_guarantee(self) -> None:
        """Rule 6: Verify strictly zero occurrences of banned terms in all generated copy."""
        vessels_to_test = [
            ("Vessel A (Suspect Tanker)", self.vessel_a_dict),
            ("Vessel B (Innocent Cargo)", self.vessel_b_dict),
            ("Vessel D (Dark Gap Ship)", self.vessel_d_dict),
        ]

        dummy_path = Path("test_explainability.py")

        for label, candidate_dict in vessels_to_test:
            payload = self.composer.compose_from_candidate(candidate_dict)

            # 1. Check forensic summary
            v_summary = check_content(payload.forensic_summary, dummy_path)
            self.assertEqual(
                len(v_summary),
                0,
                f"Banned term violation in forensic summary for {label}: {[v.rule_name for v in v_summary]}",
            )
            assert_no_banned_terms(payload.forensic_summary, f"summary_{label}")

            # 2. Check each component rationale
            rationales = [
                payload.spatial_breakdown.rationale,
                payload.temporal_breakdown.rationale,
                payload.kinematic_breakdown.rationale,
                payload.anomaly_breakdown.rationale,
                payload.type_breakdown.rationale,
            ]
            for idx, rat in enumerate(rationales):
                v_rat = check_content(rat, dummy_path)
                self.assertEqual(
                    len(v_rat),
                    0,
                    f"Banned term violation in rationale #{idx} for {label}: {[v.rule_name for v in v_rat]}",
                )
                assert_no_banned_terms(rat, f"rationale_{idx}_{label}")

            # 3. Check checklist findings
            for item in payload.evidence_checklist:
                v_chk = check_content(item.finding, dummy_path)
                self.assertEqual(
                    len(v_chk),
                    0,
                    f"Banned term in checklist item '{item.check}' for {label}: {[v.rule_name for v in v_chk]}",
                )

    def test_compose_from_db_session(self) -> None:
        """Verify compose_from_db with mock database session loading real entities."""
        mock_db = MagicMock(spec=Session)

        # Mock Case
        mock_case = Case(
            id=self.case_uuid,
            status=CaseStatus.SCORING,
            region=from_shape(shapely.geometry.box(72.0, 18.5, 73.0, 19.5), srid=4326),
            created_by="analyst_test",
        )

        # Mock OriginEstimate
        origin_pt = shapely.geometry.Point(72.290, 18.865)
        mock_origin = OriginEstimate(
            id=uuid.uuid4(),
            case_id=self.case_uuid,
            centroid=from_shape(origin_pt, srid=4326),
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

        # Mock SlickCharacterization
        mock_char = SlickCharacterization(
            id=uuid.uuid4(),
            case_id=self.case_uuid,
            perimeter_m=8500.0,
            principal_axis_deg=65.0,
            baoac_code=3,
            estimated_volume_m3=180.0,
            t_age_hours=12.0,
            age_confidence=86.0,
        )

        # Mock SlickDetection
        slick_poly = shapely.geometry.box(72.43, 18.95, 72.44, 18.97)
        mock_det = SlickDetection(
            id=uuid.uuid4(),
            case_id=self.case_uuid,
            polygon=from_shape(slick_poly, srid=4326),
            centroid=from_shape(slick_poly.centroid, srid=4326),
            area_m2=5000000.0,
            confidence=88.5,
            lookalike_risk=0.03,
            sensor="Sentinel-1 SAR IW",
            detection_time=datetime(2026, 9, 7, 6, 0, tzinfo=UTC),
            data_source=DataSource.SYNTHETIC,
        )

        # Mock VesselCandidate
        mock_candidate = VesselCandidate(
            id=uuid.uuid4(),
            case_id=self.case_uuid,
            mmsi=419000101,
            imo=9234567,
            name="PACIFIC PEARL",
            flag_state="Panama",
            vessel_type="Tanker",
            s_culprit=88.5,
            confidence=89.0,
            sub_scores={
                "spatial": 98.2,
                "temporal": 94.5,
                "kinematic": 92.0,
                "anomaly": 40.0,
                "type": 100.0,
                "details": {
                    "d_m": 0.19,
                    "cpa_dist_km": 0.25,
                    "delta_hours": 0.09,
                    "cog_deg": 68.0,
                    "slick_orientation_deg": 65.0,
                    "heading_difference_deg": 3.0,
                    "speed_kts": 6.2,
                },
            },
            anomaly_flags=["speed_drop_dumping"],
            ais_coverage=AISCoverage.FULL,
        )

        def mock_query(model):
            q = MagicMock()
            if model == VesselCandidate:
                q.filter.return_value.first.return_value = mock_candidate
            elif model == OriginEstimate:
                q.filter.return_value.order_by.return_value.first.return_value = mock_origin
            elif model == SlickCharacterization:
                q.filter.return_value.order_by.return_value.first.return_value = mock_char
            elif model == SlickDetection:
                q.filter.return_value.order_by.return_value.first.return_value = mock_det
            elif model == Case:
                q.filter.return_value.first.return_value = mock_case
            return q

        mock_db.query.side_effect = mock_query

        payload = self.composer.compose_from_db(
            db=mock_db,
            case_id=self.case_id,
            mmsi=419000101,
        )

        self.assertEqual(payload.mmsi, 419000101)
        self.assertEqual(payload.vessel_name, "PACIFIC PEARL")
        self.assertEqual(payload.s_culprit, 88.5)
        self.assertEqual(payload.spatial_breakdown.sigma_band, "1sigma")
        self.assertAlmostEqual(payload.spatial_breakdown.origin_centroid[0], 72.290, places=3)
        self.assertAlmostEqual(payload.spatial_breakdown.origin_centroid[1], 18.865, places=3)

    def test_compose_from_db_missing_candidate_raises_error(self) -> None:
        """Verify compose_from_db raises ValueError if candidate vessel is not found."""
        mock_db = MagicMock(spec=Session)
        q = MagicMock()
        q.filter.return_value.first.return_value = None
        mock_db.query.return_value = q

        with self.assertRaises(ValueError):
            self.composer.compose_from_db(
                db=mock_db,
                case_id=self.case_id,
                mmsi=999999999,
            )


if __name__ == "__main__":
    unittest.main()
