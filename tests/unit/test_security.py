"""AEGIS-Marine: Unit Tests for JWT Authentication, OIDC Claims & RBAC Security (TASK-035).

Tests conform to:
- Architecture Section 10 (Security & Access Control)
- RFC 7807 Problem Details specification
- Constitutional Rules 1, 6, and 7
"""

from __future__ import annotations

import unittest
from datetime import timedelta
from unittest.mock import MagicMock

from fastapi import status
from fastapi.testclient import TestClient
from scripts.lint_banned_terms import check_content

from backend.app.main import create_app
from backend.core.database import get_db
from backend.core.errors import AuthenticationError
from backend.core.security import (
    Role,
    create_access_token,
    decode_access_token,
    extract_roles_from_claims,
)


class TestSecurity(unittest.TestCase):
    """Test suite for JWT authentication, OIDC claims, and RBAC authorization."""

    def setUp(self) -> None:
        self.app = create_app()

        # Mock DB dependency for readiness check
        self.mock_db = MagicMock()
        self.app.dependency_overrides[get_db] = lambda: self.mock_db

        self.client = TestClient(self.app)

        # Helper tokens for the 4 core roles
        self.investigator_token = create_access_token(
            subject="user_investigator_1",
            roles=[Role.INVESTIGATOR],
            extra_claims={"email": "investigator@aegis.marine", "name": "Agent Smith"},
        )
        self.analyst_token = create_access_token(
            subject="user_analyst_1",
            roles=[Role.ANALYST],
            extra_claims={"email": "analyst@aegis.marine", "name": "Data Analyst"},
        )
        self.legal_reviewer_token = create_access_token(
            subject="user_legal_1",
            roles=[Role.LEGAL_REVIEWER],
            extra_claims={"email": "legal@aegis.marine", "name": "Legal Counsel"},
        )
        self.admin_token = create_access_token(
            subject="user_admin_1",
            roles=[Role.ADMIN],
            extra_claims={"email": "admin@aegis.marine", "name": "System Administrator"},
        )

    def tearDown(self) -> None:
        self.app.dependency_overrides.clear()

    # =========================================================================
    # 1. JWT Token Creation, Decoding & Validation
    # =========================================================================

    def test_token_creation_and_decoding(self) -> None:
        """Verify token generation produces valid signed JWT with correct claims."""
        token = create_access_token(
            subject="test_user_42",
            roles=[Role.INVESTIGATOR, Role.ANALYST],
            extra_claims={"email": "test@marine.gov"},
        )
        payload = decode_access_token(token)

        self.assertEqual(payload["sub"], "test_user_42")
        self.assertEqual(payload["roles"], ["investigator", "analyst"])
        self.assertEqual(payload["email"], "test@marine.gov")
        self.assertIn("exp", payload)
        self.assertIn("iat", payload)

    def test_expired_token_raises_authentication_error(self) -> None:
        """Verify expired tokens are rejected with 401 AuthenticationError."""
        expired_token = create_access_token(
            subject="test_expired",
            roles=[Role.INVESTIGATOR],
            expires_delta=timedelta(seconds=-10),  # expired in past
        )
        with self.assertRaises(AuthenticationError) as ctx:
            decode_access_token(expired_token)
        self.assertIn("expired", str(ctx.exception).lower())

    def test_tampered_token_signature_rejected(self) -> None:
        """Verify tokens with invalid signatures are rejected."""
        valid_token = create_access_token(subject="user_valid", roles=[Role.ANALYST])
        tampered_token = valid_token[:-5] + "XXXXX"

        with self.assertRaises(AuthenticationError) as ctx:
            decode_access_token(tampered_token)
        self.assertIn("invalid", str(ctx.exception).lower())

    def test_oidc_claims_extraction_keycloak_and_custom(self) -> None:
        """Verify role extraction handles Keycloak realm_access, resource_access, and custom claims."""
        # Keycloak realm_access format
        keycloak_payload = {
            "sub": "kc_user_1",
            "realm_access": {"roles": ["investigator", "offline_access", "uma_authorization"]},
        }
        roles = extract_roles_from_claims(keycloak_payload)
        self.assertIn("investigator", roles)

        # Keycloak resource_access format
        resource_payload = {
            "sub": "kc_user_2",
            "resource_access": {"aegis-marine-client": {"roles": ["legal_reviewer"]}},
        }
        roles_resource = extract_roles_from_claims(resource_payload)
        self.assertIn("legal_reviewer", roles_resource)

        # Custom namespaced format
        custom_payload = {
            "sub": "clerk_user_3",
            "https://aegis.marine/roles": ["admin"],
        }
        roles_custom = extract_roles_from_claims(custom_payload)
        self.assertIn("admin", roles_custom)

    # =========================================================================
    # 2. Current User Profile Endpoint (/api/v1/auth/me)
    # =========================================================================

    def test_auth_me_endpoint_success(self) -> None:
        """Verify /auth/me returns current user profile with resolved permissions."""
        headers = {"Authorization": f"Bearer {self.investigator_token}"}
        resp = self.client.get("/api/v1/auth/me", headers=headers)

        self.assertEqual(resp.status_code, status.HTTP_200_OK)
        data = resp.json()
        self.assertEqual(data["user_id"], "user_investigator_1")
        self.assertEqual(data["roles"], ["investigator"])
        self.assertIn("cases:create", data["permissions"])
        self.assertIn("dossier:export", data["permissions"])
        self.assertIn("replay:read", data["permissions"])

    def test_auth_me_unauthenticated_returns_401_rfc7807(self) -> None:
        """Verify unauthenticated requests return RFC 7807 problem details."""
        resp = self.client.get("/api/v1/auth/me")
        self.assertEqual(resp.status_code, status.HTTP_401_UNAUTHORIZED)
        self.assertIn("application/problem+json", resp.headers.get("content-type", ""))

        data = resp.json()
        self.assertEqual(data["status"], 401)
        self.assertEqual(data["title"], "Unauthorized")
        self.assertIn("urn:aegis:error:", data["type"])
        self.assertIn("Authentication credentials were not provided", data["detail"])

    # =========================================================================
    # 3. RBAC Matrix Verification (Architecture Section 10)
    # =========================================================================

    def test_case_create_rbac(self) -> None:
        """POST /api/v1/cases/test-create requires 'investigator' or 'admin'."""
        endpoint = "/api/v1/cases/test-create"

        # Investigator -> Allowed (201)
        r_inv = self.client.post(
            endpoint, headers={"Authorization": f"Bearer {self.investigator_token}"}
        )
        self.assertEqual(r_inv.status_code, status.HTTP_201_CREATED)

        # Admin -> Allowed (201)
        r_adm = self.client.post(endpoint, headers={"Authorization": f"Bearer {self.admin_token}"})
        self.assertEqual(r_adm.status_code, status.HTTP_201_CREATED)

        # Analyst -> Denied (403)
        r_ana = self.client.post(
            endpoint, headers={"Authorization": f"Bearer {self.analyst_token}"}
        )
        self.assertEqual(r_ana.status_code, status.HTTP_403_FORBIDDEN)
        self.assertIn("application/problem+json", r_ana.headers.get("content-type", ""))
        self.assertEqual(r_ana.json()["status"], 403)

        # Legal Reviewer -> Denied (403)
        r_leg = self.client.post(
            endpoint, headers={"Authorization": f"Bearer {self.legal_reviewer_token}"}
        )
        self.assertEqual(r_leg.status_code, status.HTTP_403_FORBIDDEN)

    def test_case_view_rbac(self) -> None:
        """GET /api/v1/cases/test-view allowed for all authenticated roles."""
        endpoint = "/api/v1/cases/test-view"

        for token in [
            self.investigator_token,
            self.analyst_token,
            self.legal_reviewer_token,
            self.admin_token,
        ]:
            r = self.client.get(endpoint, headers={"Authorization": f"Bearer {token}"})
            self.assertEqual(r.status_code, status.HTTP_200_OK)

        # Anonymous -> 401
        r_anon = self.client.get(endpoint)
        self.assertEqual(r_anon.status_code, status.HTTP_401_UNAUTHORIZED)

    def test_case_whatif_rbac(self) -> None:
        """POST /api/v1/cases/test-whatif requires 'investigator', 'analyst', or 'admin'."""
        endpoint = "/api/v1/cases/test-whatif"

        # Investigator -> Allowed
        r_inv = self.client.post(
            endpoint, headers={"Authorization": f"Bearer {self.investigator_token}"}
        )
        self.assertEqual(r_inv.status_code, status.HTTP_200_OK)

        # Analyst -> Allowed
        r_ana = self.client.post(
            endpoint, headers={"Authorization": f"Bearer {self.analyst_token}"}
        )
        self.assertEqual(r_ana.status_code, status.HTTP_200_OK)

        # Admin -> Allowed
        r_adm = self.client.post(endpoint, headers={"Authorization": f"Bearer {self.admin_token}"})
        self.assertEqual(r_adm.status_code, status.HTTP_200_OK)

        # Legal Reviewer -> Denied (403)
        r_leg = self.client.post(
            endpoint, headers={"Authorization": f"Bearer {self.legal_reviewer_token}"}
        )
        self.assertEqual(r_leg.status_code, status.HTTP_403_FORBIDDEN)

    def test_dossier_export_rbac(self) -> None:
        """POST /api/v1/dossiers/test-export requires 'investigator', 'legal_reviewer', or 'admin'."""
        endpoint = "/api/v1/dossiers/test-export"

        # Investigator -> Allowed
        r_inv = self.client.post(
            endpoint, headers={"Authorization": f"Bearer {self.investigator_token}"}
        )
        self.assertEqual(r_inv.status_code, status.HTTP_200_OK)

        # Legal Reviewer -> Allowed
        r_leg = self.client.post(
            endpoint, headers={"Authorization": f"Bearer {self.legal_reviewer_token}"}
        )
        self.assertEqual(r_leg.status_code, status.HTTP_200_OK)

        # Admin -> Allowed
        r_adm = self.client.post(endpoint, headers={"Authorization": f"Bearer {self.admin_token}"})
        self.assertEqual(r_adm.status_code, status.HTTP_200_OK)

        # Analyst -> Denied (403)
        r_ana = self.client.post(
            endpoint, headers={"Authorization": f"Bearer {self.analyst_token}"}
        )
        self.assertEqual(r_ana.status_code, status.HTTP_403_FORBIDDEN)

    def test_admin_only_audit_log_rbac(self) -> None:
        """GET /api/v1/admin/test-audit strictly restricted to 'admin'."""
        endpoint = "/api/v1/admin/test-audit"

        # Admin -> Allowed
        r_adm = self.client.get(endpoint, headers={"Authorization": f"Bearer {self.admin_token}"})
        self.assertEqual(r_adm.status_code, status.HTTP_200_OK)

        # Non-admins -> Denied (403)
        for token in [self.investigator_token, self.analyst_token, self.legal_reviewer_token]:
            r = self.client.get(endpoint, headers={"Authorization": f"Bearer {token}"})
            self.assertEqual(r.status_code, status.HTTP_403_FORBIDDEN)
            self.assertEqual(r.json()["status"], 403)

    # =========================================================================
    # 4. CORS Middleware Verification
    # =========================================================================

    def test_cors_preflight_headers(self) -> None:
        """Verify CORS middleware responds with correct headers for allowed origin."""
        headers = {
            "Origin": "http://localhost:3000",
            "Access-Control-Request-Method": "POST",
            "Access-Control-Request-Headers": "Authorization,Content-Type",
        }
        resp = self.client.options("/api/v1/cases/test-create", headers=headers)
        self.assertEqual(resp.status_code, status.HTTP_200_OK)
        self.assertEqual(resp.headers.get("access-control-allow-origin"), "http://localhost:3000")
        self.assertIn("POST", resp.headers.get("access-control-allow-methods", ""))

    # =========================================================================
    # 5. Operational Endpoints (/health, /ready, /ahp-config)
    # =========================================================================

    def test_liveness_health_check(self) -> None:
        """Verify /health returns 200 OK with system status."""
        resp = self.client.get("/health")
        self.assertEqual(resp.status_code, status.HTTP_200_OK)
        data = resp.json()
        self.assertEqual(data["status"], "healthy")
        self.assertEqual(data["service"], "aegis-marine-api")

    def test_readiness_check(self) -> None:
        """Verify /ready probe checks database health."""
        resp = self.client.get("/ready")
        self.assertEqual(resp.status_code, status.HTTP_200_OK)
        data = resp.json()
        self.assertEqual(data["status"], "ready")
        self.assertEqual(data["database"], "connected")

    def test_ahp_config_transparent_endpoint_rule_7(self) -> None:
        """Constitutional Rule 7 ('Show your math'): GET /ahp-config exposes matrix, weights, and CR < 0.10."""
        resp = self.client.get("/ahp-config")
        self.assertEqual(resp.status_code, status.HTTP_200_OK)
        data = resp.json()

        self.assertIn("pairwise_matrix", data)
        self.assertIn("weights", data)
        self.assertIn("consistency_ratio", data)
        self.assertLess(data["consistency_ratio"], 0.10)
        self.assertAlmostEqual(sum(data["weights"].values()), 1.0, places=4)

    # =========================================================================
    # 6. Constitutional Rule 6 Compliance (Zero Banned Terms)
    # =========================================================================

    def test_rule_6_zero_banned_terms_in_api_responses(self) -> None:
        """Verify that 401 and 403 error payloads contain strictly zero banned determination terms."""
        # Trigger 401
        r_401 = self.client.get("/api/v1/auth/me")
        violations_401 = check_content(r_401.text, MagicMock())
        self.assertEqual(len(violations_401), 0)

        # Trigger 403
        r_403 = self.client.post(
            "/api/v1/cases/test-create",
            headers={"Authorization": f"Bearer {self.analyst_token}"},
        )
        violations_403 = check_content(r_403.text, MagicMock())
        self.assertEqual(len(violations_403), 0)


if __name__ == "__main__":
    unittest.main()
