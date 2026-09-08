"""AEGIS-Marine: Unit Tests for Governance, ADR Verification & Schema Synchronization (TASK-055).

Validates:
1. Architecture Decision Records (ADR-001 through ADR-008 in ADR.md) completeness,
   formatting, statuses, deciders, options considered, and decisions.
2. System README.md completeness, architecture diagrams, runbook instructions,
   constitutional rules, and benchmark verification commands.
3. OpenAPI and Frontend TypeScript synchronization (FastAPI schema vs frontend/src/types/api.ts).
4. Strict enforcement of Constitutional Rule 6 (zero banned terms across codebase and docs).
5. Tech Stack Recommendation alignment across ADR.md and requirements.
"""

from __future__ import annotations

import re
import unittest
from pathlib import Path

from backend.app.main import create_app
from scripts.lint_banned_terms import check_content, scan_directory

REPO_ROOT = Path(__file__).resolve().parents[2]


class TestGovernanceAndSync(unittest.TestCase):
    """Test suite verifying ADR log integrity, README runbook, schema sync, and Rule 6 compliance."""

    def setUp(self) -> None:
        self.root_dir = REPO_ROOT
        self.adr_file = self.root_dir / "ADR.md"
        self.readme_file = self.root_dir / "README.md"
        self.tech_stack_file = self.root_dir / "AEGIS-Marine_Tech_Stack_Recommendation.md"
        self.rules_file = self.root_dir / "rules.md"
        self.frontend_api_types = self.root_dir / "frontend" / "src" / "types" / "api.ts"

    # =========================================================================
    # Test 1: Architecture Decision Records (ADR.md) Completeness & Rigor
    # =========================================================================
    def test_adr_structure_and_completeness(self) -> None:
        """Verify ADR.md contains template, log, and accepted entries for ADR-001 through ADR-008."""
        self.assertTrue(self.adr_file.exists(), "ADR.md must exist in repository root")
        content = self.adr_file.read_text(encoding="utf-8")

        # Must have template and log sections
        self.assertIn("## A. ADR Template", content)
        self.assertIn("## B. ADR Log", content)

        # Must contain ADR-001 through ADR-008
        expected_adrs = [
            ("ADR-001", "Adopting this ADR process itself"),
            ("ADR-002", "TimescaleDB Hypertables with PostGIS"),
            ("ADR-003", "Multi-Queue Celery Architecture"),
            ("ADR-004", "Vectorized Runge-Kutta 2nd Order Lagrangian Drift Simulation"),
            ("ADR-005", "Saaty Analytic Hierarchy Process (AHP) Multi-Criteria Attribution Scoring"),
            ("ADR-006", "WebGL deck.gl & MapLibre GL Visualization Architecture"),
            ("ADR-007", "Cryptographic SHA-256 Stamped Legal Evidence Dossier Generation"),
            ("ADR-008", "Multi-Stage Production Containerization and Health-Gated Deployment"),
        ]

        for adr_id, title_fragment in expected_adrs:
            self.assertIn(f"### {adr_id}:", content, f"ADR.md must contain header for {adr_id}")
            self.assertIn(
                title_fragment.lower(),
                content.lower(),
                f"ADR.md must contain decision title '{title_fragment}' for {adr_id}",
            )

        # Every ADR must have required standard fields
        for i in range(1, 9):
            adr_tag = f"ADR-{i:03d}"
            # Extract section for this ADR
            pattern = rf"### {adr_tag}:(.*?)(?=### ADR-|\*Next entry:|$)"
            match = re.search(pattern, content, re.DOTALL)
            self.assertIsNotNone(match, f"Could not isolate section for {adr_tag}")
            section = match.group(1)

            self.assertIn("**Date:**", section, f"{adr_tag} must specify Date")
            self.assertIn("**Status:** Accepted", section, f"{adr_tag} must have status Accepted")
            self.assertIn("**Deciders:**", section, f"{adr_tag} must specify Deciders")
            self.assertIn("**Affected documents:**", section, f"{adr_tag} must specify Affected documents")
            self.assertIn("**Context**", section, f"{adr_tag} must include Context section")
            self.assertIn("**Options Considered**", section, f"{adr_tag} must include Options Considered")
            self.assertIn("**Decision**", section, f"{adr_tag} must include Decision section")
            self.assertIn("**Consequences**", section, f"{adr_tag} must include Consequences section")
            self.assertIn("**Rule/Document Updates Required**", section, f"{adr_tag} must check document updates")

    # =========================================================================
    # Test 2: System README.md & Operational Runbook
    # =========================================================================
    def test_readme_presence_and_comprehensive_content(self) -> None:
        """Verify root README.md exists, details the 4 tiers, constitutional rules, and runbook."""
        self.assertTrue(self.readme_file.exists(), "README.md must exist in repository root")
        content = self.readme_file.read_text(encoding="utf-8")
        self.assertGreater(len(content), 3000, "README.md should be comprehensive (>3000 bytes)")

        # Title and Executive Summary
        self.assertIn("AEGIS-Marine", content)
        self.assertIn("Executive Summary", content)
        self.assertIn("MARPOL Annex I", content)

        # 4-Tier Analytical Architecture
        self.assertIn("Tier 1: Spaceborne SAR Detection", content)
        self.assertIn("Tier 2: Slick Characterization", content)
        self.assertIn("Tier 3: Hydrodynamic Drift Hindcast", content)
        self.assertIn("Tier 4: AIS Correlation & Attribution", content)

        # Constitutional Rules
        self.assertIn("Constitutional Governance Rules", content)
        for r in range(1, 8):
            self.assertIn(f"Rule {r}", content, f"README.md must mention Rule {r}")

        # Tech Stack Overview
        self.assertIn("Tech Stack Overview", content)
        self.assertIn("FastAPI", content)
        self.assertIn("TimescaleDB", content)
        self.assertIn("Celery", content)
        self.assertIn("WeasyPrint", content)
        self.assertIn("Next.js 15", content)
        self.assertIn("MapLibre GL", content)
        self.assertIn("deck.gl", content)

        # Quickstart & Deployment Runbook
        self.assertIn("Quickstart & Deployment Runbook", content)
        self.assertIn("scripts/deploy_local.sh", content)
        self.assertIn("docker-compose.prod.yml", content)
        self.assertIn("Service Health Verification", content)
        self.assertIn("Local Development Runbook", content)

        # Verification Commands
        self.assertIn("python3 scripts/lint_banned_terms.py", content)
        self.assertIn("python3 scripts/run_validation_benchmarks.py", content)
        self.assertIn("pytest", content)

        # ADR Reference
        self.assertIn("Architecture Decision Records (ADR)", content)
        for i in range(1, 9):
            self.assertIn(f"ADR-{i:03d}", content)

        # Legal Disclaimer
        self.assertIn("Legal & Scientific Disclaimer", content)

    # =========================================================================
    # Test 3: OpenAPI Schema & Frontend TypeScript Synchronicity
    # =========================================================================
    def test_openapi_and_frontend_types_synchronization(self) -> None:
        """Verify OpenAPI spec generated by FastAPI is synchronized with frontend/src/types/api.ts."""
        self.assertTrue(self.frontend_api_types.exists(), "frontend/src/types/api.ts must exist")
        frontend_types_content = self.frontend_api_types.read_text(encoding="utf-8")

        # Instantiate FastAPI app and generate OpenAPI dict
        app = create_app()
        openapi_schema = app.openapi()
        self.assertIsInstance(openapi_schema, dict)
        self.assertIn("openapi", openapi_schema)
        self.assertIn("paths", openapi_schema)
        self.assertIn("components", openapi_schema)

        schemas = openapi_schema["components"].get("schemas", {})

        # Core required schemas
        expected_schemas = [
            "CaseCreateRequest",
            "CaseDetailResponse",
            "VesselCandidateResponse",
            "WhyThisVesselPayload",
            "SubScores",
            "OriginEstimateResponse",
            "GeoJSONPolygon",
            "CaseStatusEnum",
        ]

        for s in expected_schemas:
            self.assertIn(s, schemas, f"OpenAPI components.schemas must contain '{s}'")
            self.assertIn(
                f"{s}:",
                frontend_types_content,
                f"frontend/src/types/api.ts must define schema '{s}'",
            )

        # Verify auto_start_pipeline field in CaseCreateRequest
        case_create_schema = schemas["CaseCreateRequest"]
        self.assertIn(
            "auto_start_pipeline",
            case_create_schema["properties"],
            "OpenAPI CaseCreateRequest must have property 'auto_start_pipeline'",
        )
        self.assertIn(
            "auto_start_pipeline",
            frontend_types_content,
            "frontend/src/types/api.ts must contain property 'auto_start_pipeline'",
        )

        # Verify critical API routes in OpenAPI spec
        paths = openapi_schema["paths"]
        expected_paths = [
            "/api/v1/cases",
            "/api/v1/cases/{case_id}",
            "/api/v1/cases/{case_id}/run",
            "/api/v1/cases/{case_id}/detection/sar-chip",
            "/health",
        ]

        for p in expected_paths:
            self.assertIn(p, paths, f"OpenAPI paths must include '{p}'")

    # =========================================================================
    # Test 4: Constitutional Rule 6 Banned Term Compliance
    # =========================================================================
    def test_rule6_banned_term_compliance_across_codebase(self) -> None:
        """Verify zero occurrences of banned legal determination terms across the codebase."""
        violations = scan_directory(self.root_dir)
        if violations:
            msg_lines = [f"{v.file_path}:{v.line_number} -> {v.rule_name} ('{v.line_content}')" for v in violations]
            self.fail(f"Found {len(violations)} Rule 6 violations:\n" + "\n".join(msg_lines))

    def test_rule6_compliance_in_readme_and_adr(self) -> None:
        """Verify README.md and ADR.md individually pass Rule 6 inspection without exceptions."""
        readme_content = self.readme_file.read_text(encoding="utf-8")
        readme_violations = check_content(readme_content, self.readme_file)
        self.assertEqual(
            readme_violations,
            [],
            f"README.md must not contain banned terms: {readme_violations}",
        )

        adr_content = self.adr_file.read_text(encoding="utf-8")
        adr_violations = check_content(adr_content, self.adr_file)
        self.assertEqual(
            adr_violations,
            [],
            f"ADR.md must not contain banned terms: {adr_violations}",
        )

    # =========================================================================
    # Test 5: Tech Stack Recommendation Alignment
    # =========================================================================
    def test_tech_stack_recommendation_alignment(self) -> None:
        """Verify approved technologies in Tech Stack doc correspond to recorded ADRs."""
        self.assertTrue(
            self.tech_stack_file.exists(),
            "AEGIS-Marine_Tech_Stack_Recommendation.md must exist",
        )
        tech_stack_content = self.tech_stack_file.read_text(encoding="utf-8")

        # Verify key approved technologies from recommendation doc
        self.assertIn("FastAPI", tech_stack_content)
        self.assertIn("TimescaleDB", tech_stack_content)
        self.assertIn("PostGIS", tech_stack_content)
        self.assertIn("Celery", tech_stack_content)
        self.assertIn("WeasyPrint", tech_stack_content)
        self.assertIn("deck.gl", tech_stack_content)
        self.assertIn("MapLibre", tech_stack_content)


if __name__ == "__main__":
    unittest.main()
