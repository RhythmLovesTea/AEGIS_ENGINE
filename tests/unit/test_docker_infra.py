"""Unit tests verifying TASK-003 infrastructure files and configurations."""

import os
import unittest
from pathlib import Path


class TestDockerInfraConfiguration(unittest.TestCase):
    def setUp(self) -> None:
        self.root_dir = Path(__file__).resolve().parents[2]
        self.compose_file = self.root_dir / "docker" / "docker-compose.yml"
        self.env_example = self.root_dir / ".env.example"
        self.init_minio_script = self.root_dir / "scripts" / "init_minio.sh"

    def test_docker_compose_exists_and_has_required_services(self) -> None:
        """Verify docker-compose.yml contains db, redis, minio services."""
        self.assertTrue(self.compose_file.exists(), "docker-compose.yml must exist")
        content = self.compose_file.read_text(encoding="utf-8")

        self.assertIn("image: timescale/timescaledb-ha:pg16-latest", content)
        self.assertIn("image: redis:7-alpine", content)
        self.assertIn("image: minio/minio:latest", content)
        self.assertIn("image: minio/mc:latest", content)

        self.assertIn("pg_data:", content)
        self.assertIn("redis_data:", content)
        self.assertIn("minio_data:", content)
        self.assertIn("aegis-network:", content)

    def test_env_example_contains_all_required_keys(self) -> None:
        """Verify .env.example contains necessary database and storage credentials."""
        self.assertTrue(self.env_example.exists(), ".env.example must exist")
        content = self.env_example.read_text(encoding="utf-8")

        required_keys = [
            "POSTGRES_USER",
            "POSTGRES_PASSWORD",
            "POSTGRES_DB",
            "DATABASE_URL",
            "REDIS_URL",
            "MINIO_ROOT_USER",
            "MINIO_ROOT_PASSWORD",
            "MINIO_BUCKET",
            "SECRET_KEY",
        ]
        for key in required_keys:
            self.assertIn(f"{key}=", content, f"Missing required env key: {key}")

    def test_init_minio_script_is_executable(self) -> None:
        """Verify scripts/init_minio.sh is executable."""
        self.assertTrue(self.init_minio_script.exists(), "init_minio.sh must exist")
        self.assertTrue(
            os.access(self.init_minio_script, os.X_OK),
            "init_minio.sh must have executable permissions",
        )


if __name__ == "__main__":
    unittest.main()
