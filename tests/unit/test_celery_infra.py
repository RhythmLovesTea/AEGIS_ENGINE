"""Unit tests verifying TASK-007 Celery Task Queue Infrastructure."""

import unittest
from backend.core.celery_app import celery_app
from backend.workers.tasks.pipeline_tasks import (
    test_tier1_task,
    test_tier3_task,
    test_tier4_task,
)


class TestCeleryInfrastructure(unittest.TestCase):
    def setUp(self) -> None:
        # Enable in-memory task execution for tests without running external Redis
        self.orig_backend = celery_app.conf.result_backend
        celery_app.conf.result_backend = "cache+memory://"
        celery_app.conf.task_always_eager = True
        celery_app.conf.task_eager_propagates = True

    def tearDown(self) -> None:
        celery_app.conf.result_backend = self.orig_backend
        celery_app.conf.task_always_eager = False
        celery_app.conf.task_eager_propagates = False


    def test_celery_queues_configured(self) -> None:
        """Verify specialized tier queues and dead-letter queue are configured."""
        queue_names = {q.name for q in celery_app.conf.task_queues}
        expected = {
            "queue_default",
            "queue_tier1",
            "queue_tier2",
            "queue_tier3",
            "queue_tier4",
            "queue_dlq",
        }
        self.assertTrue(expected.issubset(queue_names), f"Missing queues: {expected - queue_names}")

    def test_celery_routes_configured(self) -> None:
        """Verify routing patterns for tier tasks."""
        routes = celery_app.conf.task_routes
        self.assertEqual(routes.get("tier1.*"), {"queue": "queue_tier1"})
        self.assertEqual(routes.get("tier2.*"), {"queue": "queue_tier2"})
        self.assertEqual(routes.get("tier3.*"), {"queue": "queue_tier3"})
        self.assertEqual(routes.get("tier4.*"), {"queue": "queue_tier4"})

    def test_tier1_task_execution_and_progress(self) -> None:
        """Verify execution of test Tier 1 task."""
        result = test_tier1_task.apply(args=["test-case-uuid-001"])
        self.assertTrue(result.successful())
        self.assertEqual(result.result["status"], "success")
        self.assertEqual(result.result["stage"], "tier1_verified")

    def test_tier3_task_execution(self) -> None:
        """Verify execution of test Tier 3 task."""
        result = test_tier3_task.apply(args=["test-case-uuid-003"])
        self.assertTrue(result.successful())
        self.assertEqual(result.result["stage"], "tier3_verified")

    def test_tier4_task_execution(self) -> None:
        """Verify execution of test Tier 4 task."""
        result = test_tier4_task.apply(args=["test-case-uuid-004"])
        self.assertTrue(result.successful())
        self.assertEqual(result.result["stage"], "tier4_verified")


if __name__ == "__main__":
    unittest.main()
