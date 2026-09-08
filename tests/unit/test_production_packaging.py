"""AEGIS-Marine: Unit Tests for Production Packaging & Deployment Infrastructure (TASK-054).

Validates:
1. Multi-stage Dockerfile.backend (Python 3.12, GDAL/GEOS, non-root user, healthcheck).
2. Multi-stage Dockerfile.frontend (Next.js 15 standalone, non-root user, healthcheck).
3. Multi-stage Dockerfile.worker (Celery task worker, queue bindings, healthcheck).
4. docker-compose.prod.yml (syntax, services, healthchecks, dependencies, resource limits, volumes).
5. scripts/deploy_local.sh (executable permissions, bash syntax, dry-run, help flag).
6. Constitutional Rule 6 terminology compliance across all packaging artifacts.
"""

from __future__ import annotations

import os
import subprocess
import unittest
from pathlib import Path

import yaml
from scripts.lint_banned_terms import check_content

REPO_ROOT = Path(__file__).resolve().parents[2]


class TestProductionPackaging(unittest.TestCase):
    """Test suite verifying production Dockerfiles, Compose environment, and deploy scripts."""

    def setUp(self) -> None:
        self.root_dir = REPO_ROOT
        self.docker_dir = self.root_dir / "docker"
        self.backend_dockerfile = self.docker_dir / "Dockerfile.backend"
        self.frontend_dockerfile = self.docker_dir / "Dockerfile.frontend"
        self.worker_dockerfile = self.docker_dir / "Dockerfile.worker"
        self.compose_prod = self.root_dir / "docker-compose.prod.yml"
        self.deploy_script = self.root_dir / "scripts" / "deploy_local.sh"
        self.frontend_health_route = self.root_dir / "frontend" / "src" / "app" / "api" / "health" / "route.ts"
        self.requirements_txt = self.root_dir / "requirements.txt"

    # =========================================================================
    # Test 1: Backend Dockerfile
    # =========================================================================
    def test_backend_dockerfile_structure_and_security(self) -> None:
        """Verify Dockerfile.backend is multi-stage, uses Python 3.12, GDAL/GEOS, and non-root user."""
        self.assertTrue(self.backend_dockerfile.exists(), "Dockerfile.backend must exist")
        content = self.backend_dockerfile.read_text(encoding="utf-8")

        # Multi-stage check
        self.assertIn("FROM python:3.12-slim-bookworm AS builder", content)
        self.assertIn("FROM python:3.12-slim-bookworm AS runtime", content)

        # Geospatial C/C++ libraries
        self.assertIn("libgdal-dev", content)
        self.assertIn("libgeos-dev", content)
        self.assertIn("libproj-dev", content)
        self.assertIn("libgdal32", content)

        # WeasyPrint / Cairo libraries
        self.assertIn("libcairo2", content)
        self.assertIn("libpango-1.0-0", content)

        # Security: Non-root user
        self.assertIn("useradd -u 1000 -g aegis", content)
        self.assertIn("USER aegis", content)

        # Port & Healthcheck
        self.assertIn("EXPOSE 8000", content)
        self.assertIn("HEALTHCHECK", content)
        self.assertIn("http://localhost:8000/health", content)

        # Entrypoint
        self.assertIn("uvicorn", content)
        self.assertIn("backend.app.main:app", content)

    # =========================================================================
    # Test 2: Frontend Dockerfile
    # =========================================================================
    def test_frontend_dockerfile_standalone_packaging(self) -> None:
        """Verify Dockerfile.frontend leverages Next.js standalone build and non-root user."""
        self.assertTrue(self.frontend_dockerfile.exists(), "Dockerfile.frontend must exist")
        content = self.frontend_dockerfile.read_text(encoding="utf-8")

        # Multi-stage check
        self.assertIn("FROM node:20-alpine AS deps", content)
        self.assertIn("FROM node:20-alpine AS builder", content)
        self.assertIn("FROM node:20-alpine AS runner", content)

        # Standalone build output copying
        self.assertIn(".next/standalone", content)
        self.assertIn(".next/static", content)

        # Security: Non-root user
        self.assertIn("addgroup --system --gid 1001 nodejs", content)
        self.assertIn("adduser --system --uid 1001 nextjs", content)
        self.assertIn("USER nextjs", content)

        # Port & Healthcheck
        self.assertIn("EXPOSE 3000", content)
        self.assertIn("HEALTHCHECK", content)
        self.assertIn("http://localhost:3000/api/health", content)
        self.assertIn('CMD ["node", "server.js"]', content)

    # =========================================================================
    # Test 3: Celery Worker Dockerfile
    # =========================================================================
    def test_worker_dockerfile_task_routing(self) -> None:
        """Verify Dockerfile.worker configures Celery task queues and monitoring healthcheck."""
        self.assertTrue(self.worker_dockerfile.exists(), "Dockerfile.worker must exist")
        content = self.worker_dockerfile.read_text(encoding="utf-8")

        # Base and dependencies
        self.assertIn("FROM python:3.12-slim-bookworm AS builder", content)
        self.assertIn("FROM python:3.12-slim-bookworm AS runtime", content)
        self.assertIn("USER aegis", content)

        # Queue routing
        self.assertIn("queue_tier1", content)
        self.assertIn("queue_tier2", content)
        self.assertIn("queue_tier3", content)
        self.assertIn("queue_tier4", content)
        self.assertIn("queue_default", content)

        # Healthcheck via inspect ping
        self.assertIn("HEALTHCHECK", content)
        self.assertIn("inspect ping", content)

    # =========================================================================
    # Test 4: Production Docker Compose Specification
    # =========================================================================
    def test_docker_compose_prod_schema_and_resources(self) -> None:
        """Verify docker-compose.prod.yml contains all required services, healthchecks, and resource limits."""
        self.assertTrue(self.compose_prod.exists(), "docker-compose.prod.yml must exist")
        content = self.compose_prod.read_text(encoding="utf-8")
        parsed = yaml.safe_load(content)

        self.assertIn("services", parsed)
        services = parsed["services"]

        # Expected production service set
        expected_services = ["db", "redis", "minio", "minio-init", "api", "worker", "frontend"]
        for svc in expected_services:
            self.assertIn(svc, services, f"Missing service '{svc}' in docker-compose.prod.yml")

        # Healthchecks on long-running services
        for svc in ["db", "redis", "minio", "api", "worker", "frontend"]:
            self.assertIn("healthcheck", services[svc], f"Service '{svc}' must define a healthcheck")
            self.assertIn("test", services[svc]["healthcheck"])

        # Health-gated dependencies
        self.assertIn("depends_on", services["api"])
        self.assertEqual(services["api"]["depends_on"]["db"]["condition"], "service_healthy")
        self.assertEqual(services["api"]["depends_on"]["redis"]["condition"], "service_healthy")
        self.assertEqual(services["api"]["depends_on"]["minio"]["condition"], "service_healthy")

        self.assertIn("depends_on", services["worker"])
        self.assertEqual(services["worker"]["depends_on"]["db"]["condition"], "service_healthy")
        self.assertEqual(services["worker"]["depends_on"]["api"]["condition"], "service_healthy")

        self.assertIn("depends_on", services["frontend"])
        self.assertEqual(services["frontend"]["depends_on"]["api"]["condition"], "service_healthy")

        # Resource limits
        for svc in ["db", "redis", "minio", "api", "worker", "frontend"]:
            self.assertIn("deploy", services[svc], f"Service '{svc}' should define deploy configuration")
            self.assertIn("resources", services[svc]["deploy"])
            self.assertIn("limits", services[svc]["deploy"]["resources"])
            self.assertIn("cpus", services[svc]["deploy"]["resources"]["limits"])
            self.assertIn("memory", services[svc]["deploy"]["resources"]["limits"])

        # Restart policies
        for svc in ["db", "redis", "minio", "api", "worker", "frontend"]:
            self.assertEqual(services[svc].get("restart"), "always")

        # Networks and Volumes
        self.assertIn("networks", parsed)
        self.assertIn("aegis-prod-network", parsed["networks"])

        self.assertIn("volumes", parsed)
        for vol in ["pg_prod_data", "redis_prod_data", "minio_prod_data", "dossier_prod_data"]:
            self.assertIn(vol, parsed["volumes"])

    # =========================================================================
    # Test 5: Deployment Automation Script
    # =========================================================================
    def test_deploy_script_permissions_and_dry_run(self) -> None:
        """Verify scripts/deploy_local.sh has executable permissions, valid syntax, and passes dry-run."""
        self.assertTrue(self.deploy_script.exists(), "deploy_local.sh must exist")
        self.assertTrue(
            os.access(self.deploy_script, os.X_OK),
            "deploy_local.sh must be marked executable",
        )

        # 1. Check bash syntax via bash -n
        res_syntax = subprocess.run(
            ["bash", "-n", str(self.deploy_script)],
            capture_output=True,
            text=True,
        )
        self.assertEqual(
            res_syntax.returncode,
            0,
            f"deploy_local.sh syntax error: {res_syntax.stderr}",
        )

        # 2. Test --help flag
        res_help = subprocess.run(
            ["bash", str(self.deploy_script), "--help"],
            capture_output=True,
            text=True,
        )
        self.assertEqual(res_help.returncode, 0)
        self.assertIn("Usage:", res_help.stdout)
        self.assertIn("--dry-run", res_help.stdout)

        # 3. Test --dry-run execution
        res_dry = subprocess.run(
            ["bash", str(self.deploy_script), "--dry-run"],
            capture_output=True,
            text=True,
        )
        self.assertEqual(res_dry.returncode, 0)
        self.assertIn("DRY-RUN validation mode", res_dry.stdout)
        self.assertIn("[PASS]", res_dry.stdout)

    # =========================================================================
    # Test 6: Frontend Health Route
    # =========================================================================
    def test_frontend_health_route_exists(self) -> None:
        """Verify frontend /api/health route handler exists and exports GET."""
        self.assertTrue(self.frontend_health_route.exists(), "frontend /api/health route must exist")
        content = self.frontend_health_route.read_text(encoding="utf-8")
        self.assertIn("export async function GET", content)
        self.assertIn("healthy", content)

    # =========================================================================
    # Test 7: Rule 6 Banned Determination Terms Compliance
    # =========================================================================
    def test_rule6_compliance_in_packaging_artifacts(self) -> None:
        """Verify Dockerfiles, compose file, and deploy script contain zero Rule 6 banned terms."""
        files_to_audit = [
            self.backend_dockerfile,
            self.frontend_dockerfile,
            self.worker_dockerfile,
            self.compose_prod,
            self.deploy_script,
            self.requirements_txt,
        ]

        for file_path in files_to_audit:
            content = file_path.read_text(encoding="utf-8")
            violations = check_content(content, file_path)
            self.assertEqual(
                len(violations),
                0,
                f"Rule 6 banned term violations detected in {file_path.name}: {[v.rule_name for v in violations]}",
            )


if __name__ == "__main__":
    unittest.main()
