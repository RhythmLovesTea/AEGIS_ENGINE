"""AEGIS-Marine: Celery Worker Runner Script."""

from __future__ import annotations

import argparse
import sys
from backend.core.celery_app import celery_app


def start_worker(queue: str = "queue_default", concurrency: int = 2, log_level: str = "INFO") -> None:
    """Start Celery worker for the specified queue."""
    argv = [
        "worker",
        f"--queues={queue}",
        f"--concurrency={concurrency}",
        f"--loglevel={log_level}",
    ]
    celery_app.worker_main(argv)


def main() -> None:
    parser = argparse.ArgumentParser(description="AEGIS-Marine Celery Worker")
    parser.add_argument(
        "--queue",
        default="queue_default,queue_tier1,queue_tier2,queue_tier3,queue_tier4",
        help="Comma-separated list of queues to consume from",
    )
    parser.add_argument(
        "--concurrency",
        type=int,
        default=2,
        help="Number of concurrent worker processes",
    )
    parser.add_argument(
        "--loglevel",
        default="INFO",
        help="Logging level (DEBUG, INFO, WARNING, ERROR)",
    )
    args = parser.parse_args()
    start_worker(queue=args.queue, concurrency=args.concurrency, log_level=args.loglevel)


if __name__ == "__main__":
    main()
