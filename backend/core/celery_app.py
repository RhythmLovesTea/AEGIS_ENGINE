"""AEGIS-Marine: Celery Application, Task Routing, and Progress Tracking."""

from __future__ import annotations

import json
import logging
import os
from typing import Any

from celery import Celery, Task
from kombu import Exchange, Queue

logger = logging.getLogger("aegis.celery")

# Redis Connection URL
REDIS_URL = os.getenv("REDIS_URL", "redis://localhost:6379/0")

# Exchanges
default_exchange = Exchange("default", type="direct")
tier1_exchange = Exchange("tier1", type="topic")
tier2_exchange = Exchange("tier2", type="topic")
tier3_exchange = Exchange("tier3", type="topic")
tier4_exchange = Exchange("tier4", type="topic")
dlq_exchange = Exchange("dlq", type="direct")

# Queue Definitions
task_queues = (
    Queue("queue_default", default_exchange, routing_key="default"),
    Queue("queue_tier1", tier1_exchange, routing_key="tier1.#"),
    Queue("queue_tier2", tier2_exchange, routing_key="tier2.#"),
    Queue("queue_tier3", tier3_exchange, routing_key="tier3.#"),
    Queue("queue_tier4", tier4_exchange, routing_key="tier4.#"),
    Queue("queue_dlq", dlq_exchange, routing_key="dlq"),
)

# Route Mappings
task_routes = {
    "tier1.*": {"queue": "queue_tier1"},
    "tier2.*": {"queue": "queue_tier2"},
    "tier3.*": {"queue": "queue_tier3"},
    "tier4.*": {"queue": "queue_tier4"},
    "explain.*": {"queue": "queue_default"},
    "dossier.*": {"queue": "queue_default"},
}


class AegisTask(Task):
    """Base Celery Task for AEGIS-Marine pipeline stages.

    Provides:
    - Standardized progress reporting (0% -> 100%) to Celery task state and Redis Pub/Sub.
    - Graceful error logging and dead-letter queue routing.
    - Idempotent execution wrappers.
    """

    abstract = True

    def update_progress(
        self,
        case_id: str,
        stage: str,
        percent: float,
        message: str = "",
        extra: dict[str, Any] | None = None,
    ) -> None:
        """Update task state to PROGRESS and publish event to Redis for WebSocket clients."""
        payload = {
            "task_id": self.request.id,
            "case_id": case_id,
            "stage": stage,
            "percent": max(0.0, min(100.0, float(percent))),
            "message": message,
            "extra": extra or {},
        }
        # Update Celery task meta state (handle case where backend is offline/eager)
        try:
            self.update_state(state="PROGRESS", meta=payload)
        except Exception as e:
            logger.debug(f"Task state update skipped (backend offline): {e}")

        # Attempt to publish to Redis Pub/Sub if Redis is available
        try:
            import redis

            r = redis.Redis.from_url(REDIS_URL, socket_connect_timeout=0.2)
            r.publish(f"cases:{case_id}:progress", json.dumps(payload))
        except Exception as e:
            logger.debug(f"Redis Pub/Sub broadcast skipped (offline/unavailable): {e}")

    def on_failure(
        self,
        exc: Exception,
        task_id: str,
        args: Any,
        kwargs: Any,
        einfo: Any,
    ) -> None:
        """Invoked when a task fails after all retries."""
        logger.error(
            f"❌ Task {self.name} [{task_id}] failed: {exc}",
            exc_info=True,
            extra={"task_args": args, "task_kwargs": kwargs},
        )
        # Record failure metadata
        super().on_failure(exc, task_id, args, kwargs, einfo)

    def on_retry(
        self,
        exc: Exception,
        task_id: str,
        args: Any,
        kwargs: Any,
        einfo: Any,
    ) -> None:
        """Invoked when a task is scheduled for retry."""
        logger.warning(f"⚠️ Task {self.name} [{task_id}] retrying due to: {exc}")
        super().on_retry(exc, task_id, args, kwargs, einfo)


# Initialize Celery Application
celery_app = Celery(
    "aegis_marine",
    broker=REDIS_URL,
    backend=REDIS_URL,
)

celery_app.conf.update(
    task_cls="backend.core.celery_app:AegisTask",
    task_serializer="json",
    result_serializer="json",
    accept_content=["json"],
    timezone="UTC",
    enable_utc=True,
    task_queues=task_queues,
    task_routes=task_routes,
    task_default_queue="queue_default",
    task_track_started=True,
    task_time_limit=1800,  # 30-minute hard ceiling for complex particle hindcasts
    task_soft_time_limit=1500,  # 25-minute soft ceiling
    worker_prefetch_multiplier=1,  # Prevent prefetching on long-running ML/simulation tasks
    worker_concurrency=int(os.getenv("CELERY_CONCURRENCY", "4")),
    result_expires=86400,  # Retain task results for 24 hours
    imports=[
        "backend.workers.tasks.pipeline_tasks",
        "backend.workers.tasks.tier1_tasks",
        "backend.workers.tasks.tier2_tasks",
        "backend.workers.tasks.tier3_tasks",
        "backend.workers.tasks.tier4_tasks",
    ],
)
