"""AEGIS-Marine: Integration Tests for REST & WebSocket API Endpoints (TASK-036).

Tests conform to:
- Architecture Document Section 7 (API Surface) & Section 10 (RBAC)
- PRD Section 11 (Core Modules C1–C13)
- Constitutional Rules 1, 4, 6, and 7
"""

from __future__ import annotations

import unittest
import uuid
from datetime import UTC, datetime
from pathlib import Path
from unittest.mock import MagicMock

from fastapi import status
from fastapi.testclient import TestClient
from scripts.lint_banned_terms import check_content
from shapely.geometry import Point, Polygon

from backend.app.main import create_app
from backend.app.models.entities import (
    AISCoverage,
    AlternativeExplanation,
    Case,
    CaseStatus,
    DataSource,
    Dossier,
    ForwardForecast,
    OriginEstimate,
    SlickCharacterization,
    SlickDetection,
    VesselCandidate,
)
from backend.core.database import get_db
from backend.core.security import Role, create_access_token


class TestApiEndpoints(unittest.TestCase):
    """Integration test suite for all REST and WebSocket API endpoints."""

    def setUp(self) -> None:
        self.app = create_app()

        # Database session mock
        self.mock_db = MagicMock()
        self.app.dependency_overrides[get_db] = lambda: self.mock_db

        self.client = TestClient(self.app)

        # Pre-generated auth tokens
        self.investigator_token = create_access_token("inv_user", roles=[Role.INVESTIGATOR])
        self.analyst_token = create_access_token("ana_user", roles=[Role.ANALYST])
        self.legal_reviewer_token = create_access_token("leg_user", roles=[Role.LEGAL_REVIEWER])
        self.admin_token = create_access_token("adm_user", roles=[Role.ADMIN])

        self.case_uuid = uuid.uuid4()
        self.now_utc = datetime.now(UTC)

        # Synthetic Case Entity Mock Setup
        self.sample_case = Case(
            id=self.case_uuid,
            status=CaseStatus.READY,
            region=Polygon([(72.0, 18.8), (72.3, 18.8), (72.3, 19.1), (72.0, 19.1), (72.0, 18.8)]),
            source_scene_ref="S1A_IW_GRDH_1SDV_20260907_SAMPLE",
            created_by="investigator",
            created_at=self.now_utc,
        )

        self.sample_detection = SlickDetection(
            id=uuid.uuid4(),
            case_id=self.case_uuid,
            polygon=Polygon(
                [(72.14, 18.90), (72.16, 18.90), (72.16, 18.92), (72.14, 18.92), (72.14, 18.90)]
            ),
            centroid=Point(72.15, 18.91),
            area_m2=4_850_000.0,
            confidence=94.5,
            lookalike_risk=0.03,
            sensor="Sentinel-1A C-SAR IW",
            detection_time=self.now_utc,
            data_source=DataSource.SYNTHETIC,
            created_at=self.now_utc,
        )

        self.sample_characterization = SlickCharacterization(
            id=uuid.uuid4(),
            case_id=self.case_uuid,
            perimeter_m=12_400.0,
            principal_axis_deg=68.5,
            baoac_code=3,
            estimated_volume_m3=75.8,
            t_age_hours=4.2,
            age_confidence=88.0,
            created_at=self.now_utc,
        )

        self.sample_origin = OriginEstimate(
            id=uuid.uuid4(),
            case_id=self.case_uuid,
            centroid=Point(72.08, 18.84),
            covariance_matrix={"var_lat": 0.001, "var_lon": 0.001, "cov": 0.0},
            time_window_start=self.now_utc,
            time_window_end=self.now_utc,
            confidence_pct=91.5,
            region_area_km2=18.4,
            particle_trajectory_ref="sim_ref_001",
            created_at=self.now_utc,
        )

        self.sample_forecast = ForwardForecast(
            id=uuid.uuid4(),
            case_id=self.case_uuid,
            etb_hours=36.0,
            cvi_index=0.45,
            beached_volume_m3=12.5,
            shoreline_impact_polygon=None,
            created_at=self.now_utc,
        )

        self.sample_candidates = [
            VesselCandidate(
                id=uuid.uuid4(),
                case_id=self.case_uuid,
                mmsi=412345678,
                imo=9876543,
                name="PACIFIC TITAN",
                flag_state="Panama",
                vessel_type="Crude Oil Tanker",
                s_culprit=87.6,
                confidence=92.0,
                sub_scores={
                    "spatial": 91.0,
                    "temporal": 89.5,
                    "kinematic": 84.0,
                    "anomaly": 86.0,
                    "type": 88.0,
                },
                anomaly_flags=["speed_drop_dumping"],
                ais_coverage=AISCoverage.FULL,
                created_at=self.now_utc,
            ),
            VesselCandidate(
                id=uuid.uuid4(),
                case_id=self.case_uuid,
                mmsi=999000111,
                imo=None,
                name="UNFLAGGED CONTACT BRAVO",
                flag_state="Unknown",
                vessel_type="Bunkering Barge",
                s_culprit=54.2,
                confidence=72.0,
                sub_scores={
                    "spatial": 58.0,
                    "temporal": 54.0,
                    "kinematic": 49.0,
                    "anomaly": 60.0,
                    "type": 42.0,
                },
                anomaly_flags=["dark_transponder_gap"],
                ais_coverage=AISCoverage.DARK_GAP,
                created_at=self.now_utc,
            ),
        ]

        self.sample_alternatives = [
            AlternativeExplanation(
                id=uuid.uuid4(),
                case_id=self.case_uuid,
                hypothesis="natural_seep",
                score=12.5,
                confidence=95.0,
                evidence={"geological_basin": "Mumbai Offshore Basin", "distance_km": 48.2},
                created_at=self.now_utc,
            ),
            AlternativeExplanation(
                id=uuid.uuid4(),
                case_id=self.case_uuid,
                hypothesis="imaging_artifact",
                score=6.0,
                confidence=92.0,
                evidence={"spatial_anomaly": "High backscatter contrast"},
                created_at=self.now_utc,
            ),
        ]

        # Attach relationships to sample case
        self.sample_case.detections = [self.sample_detection]
        self.sample_case.characterizations = [self.sample_characterization]
        self.sample_case.origin_estimates = [self.sample_origin]
        self.sample_case.forward_forecasts = [self.sample_forecast]
        self.sample_case.vessel_candidates = self.sample_candidates
        self.sample_case.alternative_explanations = self.sample_alternatives
        self.sample_case.dossiers = []

    def tearDown(self) -> None:
        self.app.dependency_overrides.clear()

    # =========================================================================
    # 1. POST /cases & GET /cases
    # =========================================================================

    def test_post_case_creation(self) -> None:
        """Verify POST /cases creates a new case with status detecting."""
        headers = {"Authorization": f"Bearer {self.investigator_token}"}
        payload = {
            "region": {
                "type": "Polygon",
                "coordinates": [
                    [[72.0, 18.8], [72.3, 18.8], [72.3, 19.1], [72.0, 19.1], [72.0, 18.8]]
                ],
            },
            "source_scene_ref": "S1A_IW_GRDH_TEST",
            "created_by": "test_investigator",
        }

        # Configure mock_db
        def mock_refresh(case_obj: Case) -> None:
            case_obj.detections = []
            case_obj.characterizations = []
            case_obj.origin_estimates = []
            case_obj.forward_forecasts = []
            case_obj.vessel_candidates = []
            case_obj.alternative_explanations = []

        self.mock_db.refresh.side_effect = mock_refresh

        resp = self.client.post("/api/v1/cases", json=payload, headers=headers)
        self.assertEqual(resp.status_code, status.HTTP_201_CREATED)
        data = resp.json()

        self.assertEqual(data["status"], "detecting")
        self.assertEqual(data["source_scene_ref"], "S1A_IW_GRDH_TEST")
        self.assertTrue(self.mock_db.add.called)
        self.assertTrue(self.mock_db.commit.called)

    def test_get_cases_listing(self) -> None:
        """Verify GET /cases returns paginated list of cases."""
        headers = {"Authorization": f"Bearer {self.investigator_token}"}
        self.mock_db.query.return_value.order_by.return_value.offset.return_value.limit.return_value.all.return_value = [
            self.sample_case
        ]

        resp = self.client.get("/api/v1/cases", headers=headers)
        self.assertEqual(resp.status_code, status.HTTP_200_OK)
        data = resp.json()

        self.assertIsInstance(data, list)
        self.assertEqual(len(data), 1)
        self.assertEqual(data[0]["id"], str(self.case_uuid))
        self.assertEqual(data[0]["status"], "ready")

    # =========================================================================
    # 2. GET /cases/{id} Full Aggregate
    # =========================================================================

    def test_get_case_detail_success(self) -> None:
        """Verify GET /cases/{id} returns multi-tier aggregate with all children."""
        headers = {"Authorization": f"Bearer {self.investigator_token}"}
        self.mock_db.query.return_value.filter.return_value.first.return_value = self.sample_case

        resp = self.client.get(f"/api/v1/cases/{self.case_uuid}", headers=headers)
        self.assertEqual(resp.status_code, status.HTTP_200_OK)
        data = resp.json()

        self.assertEqual(data["id"], str(self.case_uuid))
        self.assertEqual(len(data["detections"]), 1)
        self.assertEqual(len(data["characterizations"]), 1)
        self.assertEqual(len(data["origin_estimates"]), 1)
        self.assertEqual(len(data["forward_forecasts"]), 1)
        self.assertEqual(len(data["vessel_candidates"]), 2)
        self.assertEqual(len(data["alternative_explanations"]), 2)

    def test_get_case_detail_not_found(self) -> None:
        """Verify GET /cases/{id} returns 404 RFC 7807 when case is absent."""
        headers = {"Authorization": f"Bearer {self.investigator_token}"}
        self.mock_db.query.return_value.filter.return_value.first.return_value = None

        unknown_uuid = uuid.uuid4()
        resp = self.client.get(f"/api/v1/cases/{unknown_uuid}", headers=headers)
        self.assertEqual(resp.status_code, status.HTTP_404_NOT_FOUND)
        self.assertIn("application/problem+json", resp.headers.get("content-type", ""))

    # =========================================================================
    # 3. GET /cases/{id}/vessels
    # =========================================================================

    def test_get_vessels_ranked(self) -> None:
        """Verify GET /cases/{id}/vessels returns ranked candidates with Rule 1 & 4 compliance."""
        headers = {"Authorization": f"Bearer {self.analyst_token}"}

        # Mock case check and candidate query
        self.mock_db.query.return_value.filter.return_value.first.return_value = self.sample_case
        self.mock_db.query.return_value.filter.return_value.order_by.return_value.all.return_value = self.sample_candidates

        resp = self.client.get(f"/api/v1/cases/{self.case_uuid}/vessels", headers=headers)
        self.assertEqual(resp.status_code, status.HTTP_200_OK)
        data = resp.json()

        self.assertEqual(len(data), 2)
        # Verify candidate #1
        self.assertEqual(data[0]["name"], "PACIFIC TITAN")
        self.assertEqual(data[0]["mmsi"], 412345678)
        self.assertGreater(data[0]["s_culprit"], data[1]["s_culprit"])
        self.assertIn("confidence", data[0])  # Rule 1

        # Verify dark ship contact is surfaced (Rule 4)
        self.assertEqual(data[1]["name"], "UNFLAGGED CONTACT BRAVO")
        self.assertEqual(data[1]["ais_coverage"], "dark_gap")

    # =========================================================================
    # 4. GET /cases/{id}/vessels/{mmsi}/explain
    # =========================================================================

    def test_explain_vessel(self) -> None:
        """Verify GET /cases/{id}/vessels/{mmsi}/explain returns WhyThisVesselPayload."""
        headers = {"Authorization": f"Bearer {self.legal_reviewer_token}"}

        # Setup mock db query responses for composer
        def mock_query(model: type) -> MagicMock:
            mock_q = MagicMock()
            if model == Case:
                mock_q.filter.return_value.first.return_value = self.sample_case
            elif model == VesselCandidate:
                mock_q.filter.return_value.first.return_value = self.sample_candidates[0]
                mock_q.filter.return_value.order_by.return_value.all.return_value = (
                    self.sample_candidates
                )
            elif model == OriginEstimate:
                mock_q.filter.return_value.first.return_value = self.sample_origin
            elif model == SlickCharacterization:
                mock_q.filter.return_value.first.return_value = self.sample_characterization
            elif model == SlickDetection:
                mock_q.filter.return_value.first.return_value = self.sample_detection
            else:
                mock_q.filter.return_value.first.return_value = None
                mock_q.filter.return_value.all.return_value = []
            return mock_q

        self.mock_db.query.side_effect = mock_query

        resp = self.client.get(
            f"/api/v1/cases/{self.case_uuid}/vessels/412345678/explain",
            headers=headers,
        )
        self.assertEqual(resp.status_code, status.HTTP_200_OK)
        data = resp.json()

        self.assertEqual(data["mmsi"], 412345678)
        self.assertEqual(data["vessel_name"], "PACIFIC TITAN")
        self.assertIn("spatial_breakdown", data)
        self.assertIn("temporal_breakdown", data)
        self.assertIn("radar_data", data)
        self.assertIn("bar_data", data)
        self.assertIn("evidence_checklist", data)
        self.assertIn("forensic_summary", data)

    # =========================================================================
    # 5. POST /cases/{id}/vessels/{mmsi}/counterfactual
    # =========================================================================

    def test_counterfactual_simulation(self) -> None:
        """Verify POST /cases/{id}/vessels/{mmsi}/counterfactual runs forward simulation."""
        headers = {"Authorization": f"Bearer {self.investigator_token}"}

        def mock_query(model: type) -> MagicMock:
            mock_q = MagicMock()
            if model == Case:
                mock_q.filter.return_value.first.return_value = self.sample_case
            elif model == VesselCandidate:
                mock_q.filter.return_value.first.return_value = self.sample_candidates[0]
                mock_q.filter.return_value.order_by.return_value.first.return_value = (
                    self.sample_candidates[0]
                )
            elif model == SlickDetection:
                mock_q.filter.return_value.first.return_value = self.sample_detection
                mock_q.filter.return_value.order_by.return_value.first.return_value = (
                    self.sample_detection
                )
            elif model == SlickCharacterization:
                mock_q.filter.return_value.first.return_value = self.sample_characterization
                mock_q.filter.return_value.order_by.return_value.first.return_value = (
                    self.sample_characterization
                )
            elif model == OriginEstimate:
                mock_q.filter.return_value.first.return_value = self.sample_origin
                mock_q.filter.return_value.order_by.return_value.first.return_value = (
                    self.sample_origin
                )
            else:
                mock_q.filter.return_value.first.return_value = None
                mock_q.filter.return_value.order_by.return_value.first.return_value = None
            return mock_q

        self.mock_db.query.side_effect = mock_query

        resp = self.client.post(
            f"/api/v1/cases/{self.case_uuid}/vessels/412345678/counterfactual",
            headers=headers,
        )
        self.assertEqual(resp.status_code, status.HTTP_200_OK)
        data = resp.json()

        self.assertEqual(data["case_id"], str(self.case_uuid))
        self.assertEqual(data["mmsi"], 412345678)
        self.assertIn("similarity_score", data)
        self.assertIn("iou_pct", data)
        self.assertIn("confidence_pct", data)

    # =========================================================================
    # 6. GET /cases/{id}/alternatives (Rule 5)
    # =========================================================================

    def test_get_alternatives(self) -> None:
        """Verify GET /cases/{id}/alternatives returns evaluated non-vessel hypotheses."""
        headers = {"Authorization": f"Bearer {self.analyst_token}"}

        def mock_query(model: type) -> MagicMock:
            mock_q = MagicMock()
            if model == Case:
                mock_q.filter.return_value.first.return_value = self.sample_case
            elif model == AlternativeExplanation:
                mock_q.filter.return_value.all.return_value = self.sample_alternatives
            return mock_q

        self.mock_db.query.side_effect = mock_query

        resp = self.client.get(f"/api/v1/cases/{self.case_uuid}/alternatives", headers=headers)
        self.assertEqual(resp.status_code, status.HTTP_200_OK)
        data = resp.json()

        self.assertIsInstance(data, list)
        self.assertEqual(len(data), 2)
        hypotheses = [h["hypothesis"] for h in data]
        self.assertIn("natural_seep", hypotheses)
        self.assertIn("imaging_artifact", hypotheses)

    # =========================================================================
    # 7. GET /cases/{id}/replay (Feature 4 / D4)
    # =========================================================================

    def test_get_replay_state(self) -> None:
        """Verify GET /cases/{id}/replay returns time-slice scrubber payload."""
        headers = {"Authorization": f"Bearer {self.analyst_token}"}
        self.mock_db.query.return_value.filter.return_value.first.return_value = self.sample_case

        resp = self.client.get(f"/api/v1/cases/{self.case_uuid}/replay", headers=headers)
        self.assertEqual(resp.status_code, status.HTTP_200_OK)
        data = resp.json()

        self.assertEqual(data["case_id"], str(self.case_uuid))
        self.assertIn("particles", data)
        self.assertIn("vessels", data)
        self.assertIn("time_progress_pct", data)
        self.assertIn("confidence_pct", data)

    # =========================================================================
    # 8. GET /cases/{id}/evidence-graph (Feature 11 / P5)
    # =========================================================================

    def test_get_evidence_graph(self) -> None:
        """Verify GET /cases/{id}/evidence-graph returns graph and timeline bundle."""
        headers = {"Authorization": f"Bearer {self.legal_reviewer_token}"}

        def mock_query(model: type) -> MagicMock:
            mock_q = MagicMock()
            if model == Case:
                mock_q.filter.return_value.first.return_value = self.sample_case
            elif model == SlickDetection:
                mock_q.filter.return_value.all.return_value = [self.sample_detection]
            elif model == SlickCharacterization:
                mock_q.filter.return_value.all.return_value = [self.sample_characterization]
            elif model == OriginEstimate:
                mock_q.filter.return_value.all.return_value = [self.sample_origin]
            elif model == VesselCandidate:
                mock_q.filter.return_value.all.return_value = self.sample_candidates
            elif model == AlternativeExplanation:
                mock_q.filter.return_value.all.return_value = self.sample_alternatives
            return mock_q

        self.mock_db.query.side_effect = mock_query

        resp = self.client.get(f"/api/v1/cases/{self.case_uuid}/evidence-graph", headers=headers)
        self.assertEqual(resp.status_code, status.HTTP_200_OK)
        data = resp.json()

        self.assertEqual(data["case_id"], str(self.case_uuid))
        self.assertIn("timeline", data)
        self.assertIn("graph", data)
        self.assertIn("nodes", data["graph"])
        self.assertIn("edges", data["graph"])

    # =========================================================================
    # 9. Legal Dossier Export & Download (POST / GET /cases/{id}/dossier)
    # =========================================================================

    def test_dossier_export_and_download(self) -> None:
        """Verify POST /cases/{id}/dossier generates dossier and GET /cases/{id}/dossier streams PDF."""
        headers = {"Authorization": f"Bearer {self.investigator_token}"}

        self.mock_db.query.return_value.filter.return_value.first.return_value = self.sample_case

        # POST /cases/{id}/dossier
        resp_post = self.client.post(f"/api/v1/cases/{self.case_uuid}/dossier", headers=headers)
        self.assertEqual(resp_post.status_code, status.HTTP_200_OK)
        data = resp_post.json()

        self.assertEqual(data["case_id"], str(self.case_uuid))
        self.assertEqual(len(data["sha256_hash"]), 64)
        self.assertTrue(data["verification_qr_b64"].startswith("data:image/png;base64,"))

        # Mock Dossier DB record for GET download
        mock_dossier = Dossier(
            id=uuid.uuid4(),
            case_id=self.case_uuid,
            pdf_ref="s3://aegis-storage/dossiers/test_dossier.pdf",
            sha256_hash=data["sha256_hash"],
            generated_by="investigator",
            generated_at=self.now_utc,
            model_versions={},
        )
        self.mock_db.query.return_value.filter.return_value.order_by.return_value.first.return_value = mock_dossier

        # GET /cases/{id}/dossier
        resp_get = self.client.get(f"/api/v1/cases/{self.case_uuid}/dossier", headers=headers)
        self.assertEqual(resp_get.status_code, status.HTTP_200_OK)
        self.assertEqual(resp_get.headers.get("content-type"), "application/pdf")
        self.assertTrue(resp_get.content.startswith(b"%PDF-"))

    # =========================================================================
    # 10. GET /ahp-config (Rule 7)
    # =========================================================================

    def test_ahp_config_api_and_root(self) -> None:
        """Constitutional Rule 7 ('Show your math'): GET /ahp-config returns matrix and CR < 0.10."""
        for path in ["/ahp-config", "/api/v1/ahp-config"]:
            resp = self.client.get(path)
            self.assertEqual(resp.status_code, status.HTTP_200_OK)
            data = resp.json()
            self.assertIn("pairwise_matrix", data)
            self.assertIn("weights", data)
            self.assertLess(data["consistency_ratio"], 0.10)

    # =========================================================================
    # 11. WebSocket /cases/{id}/status Live Progress Stream
    # =========================================================================

    def test_websocket_case_status_stream(self) -> None:
        """Verify WebSocket /cases/{id}/status connects and responds to ping."""
        ws_url = f"/api/v1/cases/{self.case_uuid}/status"

        with self.client.websocket_connect(ws_url) as ws:
            # Receive initial connection message
            init_msg = ws.receive_json()
            self.assertEqual(init_msg["case_id"], str(self.case_uuid))
            self.assertEqual(init_msg["status"], "connected")

            # Send ping
            ws.send_text("ping")
            pong_msg = ws.receive_json()
            self.assertEqual(pong_msg["type"], "pong")

            # Send query
            ws.send_text("query_status")
            status_msg = ws.receive_json()
            self.assertEqual(status_msg["status"], "ready")

    # =========================================================================
    # 12. RBAC Access Control Matrix Verification
    # =========================================================================

    def test_rbac_denials_on_restricted_endpoints(self) -> None:
        """Verify RBAC role checks deny unauthorized roles with 403."""
        # 1. Analyst cannot create case
        r1 = self.client.post(
            "/api/v1/cases",
            json={
                "region": {"type": "Polygon", "coordinates": [[[0, 0], [1, 0], [1, 1], [0, 0]]]},
            },
            headers={"Authorization": f"Bearer {self.legal_reviewer_token}"},
        )
        self.assertEqual(r1.status_code, status.HTTP_403_FORBIDDEN)

        # 2. Legal Reviewer cannot run counterfactual simulation
        r2 = self.client.post(
            f"/api/v1/cases/{self.case_uuid}/vessels/412345678/counterfactual",
            headers={"Authorization": f"Bearer {self.legal_reviewer_token}"},
        )
        self.assertEqual(r2.status_code, status.HTTP_403_FORBIDDEN)

        # 3. Analyst cannot generate dossier
        r3 = self.client.post(
            f"/api/v1/cases/{self.case_uuid}/dossier",
            headers={"Authorization": f"Bearer {self.analyst_token}"},
        )
        self.assertEqual(r3.status_code, status.HTTP_403_FORBIDDEN)

    # =========================================================================
    # 13. Rule 6 Terminology Compliance (Zero Banned Terms)
    # =========================================================================

    def test_rule_6_zero_banned_terms_across_all_responses(self) -> None:
        """Verify all endpoint responses contain strictly zero banned determination terms."""
        self.mock_db.query.return_value.filter.return_value.first.return_value = self.sample_case
        headers = {"Authorization": f"Bearer {self.investigator_token}"}

        endpoints = [
            f"/api/v1/cases/{self.case_uuid}",
            f"/api/v1/cases/{self.case_uuid}/vessels",
            f"/api/v1/cases/{self.case_uuid}/alternatives",
            f"/api/v1/cases/{self.case_uuid}/replay",
            "/ahp-config",
        ]

        for ep in endpoints:
            r = self.client.get(ep, headers=headers)
            violations = check_content(r.text, Path("api_response.json"))
            self.assertEqual(len(violations), 0, f"Found banned terms on {ep}: {violations}")


if __name__ == "__main__":
    unittest.main()
