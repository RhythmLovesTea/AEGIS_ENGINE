"""AEGIS-Marine: Audit Logging System Tests (TASK-038 & rules.md Section 5).

Validates:
- AuditLoggingMiddleware intercepting mutating HTTP requests (POST, PUT, DELETE, PATCH)
- SHA-256 cryptographic payload digest generation
- Extraction of authenticated user identity, client IP, action name, and target case ID
- Bypass of non-mutating HTTP requests (GET)
- Admin audit log query endpoint (GET /admin/audit-logs)
- RBAC permissions (strictly admin role allowed; all other roles denied with 403)
- Audit log filtering by case_id, user_id, and action
- Programmatic audit logging helper (record_audit_log)
- Constitutional Rule 6 zero banned determination terms
"""

from __future__ import annotations

import hashlib
import json
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
    AuditLog,
    Case,
    CaseStatus,
    DataSource,
    OriginEstimate,
    SlickCharacterization,
    SlickDetection,
    VesselCandidate,
)
from backend.core.audit import (
    clear_memory_audit_logs,
    get_memory_audit_logs,
    record_audit_log,
    resolve_action_name,
)
from backend.core.database import get_db
from backend.core.security import Role, create_access_token


class TestAuditLoggingSystem(unittest.TestCase):
    """Test suite covering the Audit Logging System and mutating request middleware."""

    def setUp(self) -> None:
        clear_memory_audit_logs()
        self.app = create_app()
        self.mock_db = MagicMock()
        self.app.dependency_overrides[get_db] = lambda: self.mock_db
        self.client = TestClient(self.app)

        # Auth tokens
        self.investigator_token = create_access_token("inv_user", roles=[Role.INVESTIGATOR])
        self.analyst_token = create_access_token("ana_user", roles=[Role.ANALYST])
        self.legal_reviewer_token = create_access_token("leg_user", roles=[Role.LEGAL_REVIEWER])
        self.admin_token = create_access_token("adm_user", roles=[Role.ADMIN])

        self.case_uuid = uuid.uuid4()
        self.now_utc = datetime.now(UTC)

        # Synthetic Case Entities
        self.sample_case = Case(
            id=self.case_uuid,
            status=CaseStatus.READY,
            region=Polygon([(72.0, 18.8), (72.3, 18.8), (72.3, 19.1), (72.0, 19.1), (72.0, 18.8)]),
            source_scene_ref="S1A_IW_GRDH_1SDV_20260907_AUDIT",
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
            covariance_matrix={"var_lat": 0.001, "var_lon": 0.001, "cov_lon_lat": 0.0},
            time_window_start=self.now_utc,
            time_window_end=self.now_utc,
            confidence_pct=91.5,
            region_area_km2=18.4,
            particle_trajectory_ref="baseline_traj_ref",
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
                s_culprit=88.5,
                confidence=92.0,
                sub_scores={
                    "spatial": 91.0,
                    "temporal": 89.5,
                    "kinematic": 84.0,
                    "anomaly": 86.0,
                    "type": 95.0,
                },
                anomaly_flags=["speed_drop_dumping"],
                ais_coverage=AISCoverage.FULL,
                created_at=self.now_utc,
            )
        ]

        self.sample_case.detections = [self.sample_detection]
        self.sample_case.characterizations = [self.sample_characterization]
        self.sample_case.origin_estimates = [self.sample_origin]
        self.sample_case.vessel_candidates = self.sample_candidates
        self.sample_case.alternative_explanations = []

        # Configure mock_db routing
        def mock_query_fn(entity):
            mock_q = MagicMock()
            if entity == Case:
                mock_q.filter.return_value.first.return_value = self.sample_case
            elif entity == SlickDetection:
                mock_q.filter.return_value.order_by.return_value.first.return_value = (
                    self.sample_detection
                )
            elif entity == SlickCharacterization:
                mock_q.filter.return_value.order_by.return_value.first.return_value = (
                    self.sample_characterization
                )
            elif entity == OriginEstimate:
                mock_q.filter.return_value.order_by.return_value.first.return_value = (
                    self.sample_origin
                )
            elif entity == VesselCandidate:
                mock_q.filter.return_value.order_by.return_value.all.return_value = (
                    self.sample_candidates
                )
            elif entity == AuditLog:
                # Return empty list from mock query so memory fallback handles query in tests
                mock_q.filter.return_value.count.return_value = 0
                mock_q.filter.return_value.order_by.return_value.offset.return_value.limit.return_value.all.return_value = []
                mock_q.count.return_value = 0
                mock_q.order_by.return_value.offset.return_value.limit.return_value.all.return_value = []
            return mock_q

        self.mock_db.query.side_effect = mock_query_fn

    def tearDown(self) -> None:
        self.app.dependency_overrides.clear()
        clear_memory_audit_logs()

    # =========================================================================
    # 1. Mutating HTTP Request Interception & Digest Verification
    # =========================================================================

    def test_audit_middleware_records_case_mutation(self) -> None:
        """Mutating request (POST /cases) creates an immutable audit entry with payload digest."""
        clear_memory_audit_logs()

        headers = {
            "Authorization": f"Bearer {self.investigator_token}",
            "X-Forwarded-For": "198.51.100.42",
        }
        payload = {
            "region": {
                "type": "Polygon",
                "coordinates": [
                    [[72.0, 18.8], [72.3, 18.8], [72.3, 19.1], [72.0, 19.1], [72.0, 18.8]]
                ],
            },
            "source_scene_ref": "S1A_IW_GRDH_AUDIT_TEST",
            "created_by": "inv_user",
        }
        body_bytes = json.dumps(payload, separators=(",", ":")).encode("utf-8")
        expected_sha256 = hashlib.sha256(body_bytes).hexdigest()

        def mock_refresh(c: Case) -> None:
            c.detections = []
            c.characterizations = []
            c.origin_estimates = []
            c.forward_forecasts = []
            c.vessel_candidates = []
            c.alternative_explanations = []

        self.mock_db.refresh.side_effect = mock_refresh

        headers["Content-Type"] = "application/json"
        resp = self.client.post("/api/v1/cases", content=body_bytes, headers=headers)
        self.assertEqual(resp.status_code, status.HTTP_201_CREATED)

        # Verify audit log in memory buffer
        logs = get_memory_audit_logs()
        self.assertTrue(len(logs) >= 1)

        create_log = next((log for log in logs if log.action == "case.create"), None)
        self.assertIsNotNone(create_log)
        self.assertEqual(create_log.user_id, "inv_user")
        self.assertEqual(create_log.details["client_ip"], "198.51.100.42")
        self.assertEqual(create_log.details["method"], "POST")
        self.assertEqual(create_log.details["status_code"], 201)
        self.assertEqual(create_log.details["payload_sha256"], expected_sha256)

        # Verify database persist attempt
        self.assertTrue(self.mock_db.add.called)

    def test_audit_middleware_records_what_if_override(self) -> None:
        """Mutating request (POST /cases/{id}/whatif) records case_id and what_if action."""
        clear_memory_audit_logs()

        headers = {
            "Authorization": f"Bearer {self.analyst_token}",
            "Content-Type": "application/json",
        }
        payload = {
            "scenario_name": "Audit Tracked Scenario",
            "t_age_override_hours": 8.0,
            "persist_scenario": False,
        }
        body_bytes = json.dumps(payload, separators=(",", ":")).encode("utf-8")
        expected_sha256 = hashlib.sha256(body_bytes).hexdigest()

        resp = self.client.post(
            f"/api/v1/cases/{self.case_uuid}/whatif",
            content=body_bytes,
            headers=headers,
        )
        self.assertEqual(resp.status_code, status.HTTP_200_OK)

        logs = get_memory_audit_logs()
        whatif_log = next((log for log in logs if log.action == "case.what_if_simulation"), None)
        self.assertIsNotNone(whatif_log)
        self.assertEqual(whatif_log.user_id, "ana_user")
        self.assertEqual(whatif_log.case_id, self.case_uuid)
        self.assertEqual(whatif_log.details["payload_sha256"], expected_sha256)

    def test_audit_middleware_records_dossier_export(self) -> None:
        """Mutating request (POST /cases/{id}/dossier) records dossier.generate action."""
        clear_memory_audit_logs()

        self.mock_db.query.return_value.filter.return_value.first.return_value = self.sample_case
        headers = {
            "Authorization": f"Bearer {self.legal_reviewer_token}",
            "Content-Type": "application/json",
        }
        payload = {
            "case_id": str(self.case_uuid),
            "generated_by": "legal_officer",
        }
        body_bytes = json.dumps(payload, separators=(",", ":")).encode("utf-8")
        expected_sha256 = hashlib.sha256(body_bytes).hexdigest()

        resp = self.client.post(
            f"/api/v1/cases/{self.case_uuid}/dossier",
            content=body_bytes,
            headers=headers,
        )
        self.assertEqual(resp.status_code, status.HTTP_200_OK)

        logs = get_memory_audit_logs()
        dossier_log = next((log for log in logs if log.action == "dossier.generate"), None)
        self.assertIsNotNone(dossier_log)
        self.assertEqual(dossier_log.user_id, "leg_user")
        self.assertEqual(dossier_log.case_id, self.case_uuid)
        self.assertEqual(dossier_log.details["payload_sha256"], expected_sha256)

    def test_audit_non_mutating_requests_bypassed(self) -> None:
        """Non-mutating HTTP requests (GET) bypass the mutation audit logger."""
        clear_memory_audit_logs()

        headers = {"Authorization": f"Bearer {self.investigator_token}"}
        resp = self.client.get(f"/api/v1/cases/{self.case_uuid}", headers=headers)
        self.assertEqual(resp.status_code, status.HTTP_200_OK)

        logs = get_memory_audit_logs()
        self.assertEqual(len(logs), 0)

    # =========================================================================
    # 2. Action Name Resolution Helper
    # =========================================================================

    def test_resolve_action_name(self) -> None:
        """Action name resolver correctly categorizes canonical endpoints."""
        self.assertEqual(resolve_action_name("POST", "/api/v1/cases"), "case.create")
        self.assertEqual(resolve_action_name("POST", "/cases"), "case.create")
        self.assertEqual(
            resolve_action_name("POST", f"/cases/{uuid.uuid4()}/whatif"), "case.what_if_simulation"
        )
        self.assertEqual(
            resolve_action_name("POST", f"/cases/{uuid.uuid4()}/dossier"), "dossier.generate"
        )
        self.assertEqual(resolve_action_name("POST", f"/cases/{uuid.uuid4()}/rerun"), "case.rerun")
        self.assertEqual(
            resolve_action_name("POST", f"/cases/{uuid.uuid4()}/vessels/123/counterfactual"),
            "vessel.counterfactual_simulation",
        )
        self.assertEqual(resolve_action_name("DELETE", f"/cases/{uuid.uuid4()}"), "case.delete")
        self.assertEqual(resolve_action_name("PUT", f"/cases/{uuid.uuid4()}"), "case.update")

    # =========================================================================
    # 3. Admin Audit Log API & RBAC Matrix
    # =========================================================================

    def test_admin_audit_logs_rbac_success(self) -> None:
        """Admin user successfully accesses GET /admin/audit-logs."""
        # Record a test audit log
        record_audit_log(
            db=self.mock_db,
            user_id="test_admin",
            action="admin.system_check",
            case_id=self.case_uuid,
            details={"check": "ok"},
        )

        headers = {"Authorization": f"Bearer {self.admin_token}"}
        resp = self.client.get("/admin/audit-logs", headers=headers)
        self.assertEqual(resp.status_code, status.HTTP_200_OK)

        data = resp.json()
        self.assertIn("items", data)
        self.assertIn("total", data)
        self.assertTrue(data["total"] >= 1)
        self.assertEqual(data["items"][0]["action"], "admin.system_check")

        # Also verify mounted at /api/v1/admin/audit-logs
        resp_v1 = self.client.get("/api/v1/admin/audit-logs", headers=headers)
        self.assertEqual(resp_v1.status_code, status.HTTP_200_OK)

    def test_admin_audit_logs_rbac_denied(self) -> None:
        """Non-admin roles (investigator, analyst, legal_reviewer) are rejected with 403 Forbidden."""
        for token in [self.investigator_token, self.analyst_token, self.legal_reviewer_token]:
            headers = {"Authorization": f"Bearer {token}"}
            resp = self.client.get("/admin/audit-logs", headers=headers)
            self.assertEqual(resp.status_code, status.HTTP_403_FORBIDDEN)

        # Unauthenticated -> 401
        unauth_resp = self.client.get("/admin/audit-logs")
        self.assertEqual(unauth_resp.status_code, status.HTTP_401_UNAUTHORIZED)

    def test_admin_audit_logs_filtering(self) -> None:
        """Admin audit logs endpoint supports filtering by case_id, user_id, and action."""
        clear_memory_audit_logs()
        case_a = uuid.uuid4()
        case_b = uuid.uuid4()

        record_audit_log(self.mock_db, "user_alpha", "case.create", case_a, {"tag": "1"})
        record_audit_log(self.mock_db, "user_beta", "case.what_if_simulation", case_b, {"tag": "2"})
        record_audit_log(self.mock_db, "user_alpha", "dossier.generate", case_a, {"tag": "3"})

        headers = {"Authorization": f"Bearer {self.admin_token}"}

        # Filter by case_id
        resp_case = self.client.get(f"/admin/audit-logs?case_id={case_a}", headers=headers)
        self.assertEqual(resp_case.status_code, status.HTTP_200_OK)
        items_case = resp_case.json()["items"]
        self.assertEqual(len(items_case), 2)
        for item in items_case:
            self.assertEqual(item["case_id"], str(case_a))

        # Filter by user_id
        resp_user = self.client.get("/admin/audit-logs?user_id=user_beta", headers=headers)
        self.assertEqual(resp_user.status_code, status.HTTP_200_OK)
        items_user = resp_user.json()["items"]
        self.assertEqual(len(items_user), 1)
        self.assertEqual(items_user[0]["user_id"], "user_beta")

        # Filter by action
        resp_action = self.client.get("/admin/audit-logs?action=dossier.generate", headers=headers)
        self.assertEqual(resp_action.status_code, status.HTTP_200_OK)
        items_action = resp_action.json()["items"]
        self.assertEqual(len(items_action), 1)
        self.assertEqual(items_action[0]["action"], "dossier.generate")

    # =========================================================================
    # 4. Constitutional Rule 6 Compliance
    # =========================================================================

    def test_constitutional_rules_compliance(self) -> None:
        """Enforces Rule 6: strictly zero occurrences of banned determination terms in audit output."""
        clear_memory_audit_logs()
        record_audit_log(
            self.mock_db,
            user_id="adm_auditor",
            action="case.audit_examination",
            case_id=self.case_uuid,
            details={"summary": "Routine evidence verification and cryptographic ledger check"},
        )

        headers = {"Authorization": f"Bearer {self.admin_token}"}
        resp = self.client.get("/admin/audit-logs", headers=headers)
        self.assertEqual(resp.status_code, status.HTTP_200_OK)

        json_text = resp.text
        violations = check_content(json_text, Path("admin_audit_logs_output.json"))
        self.assertEqual(
            violations, [], f"Rule 6 violations detected in audit payload: {violations}"
        )


if __name__ == "__main__":
    unittest.main()
