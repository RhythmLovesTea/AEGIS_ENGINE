"""AEGIS-Marine: Scaffolding and Verification Tasks for Celery Pipeline."""

from __future__ import annotations

import time
from typing import Any, Dict
from backend.core.celery_app import AegisTask, celery_app


@celery_app.task(bind=True, base=AegisTask, name="tier1.test_task")
def test_tier1_task(self: AegisTask, case_id: str) -> Dict[str, Any]:
    """Test task demonstrating Tier 1 queue routing and progress reporting."""
    self.update_progress(case_id=case_id, stage="detecting", percent=10.0, message="Ingesting test SAR scene")
    self.update_progress(case_id=case_id, stage="detecting", percent=50.0, message="Executing segmentation inference")
    self.update_progress(case_id=case_id, stage="detecting", percent=100.0, message="Segmentation complete")
    return {"status": "success", "case_id": case_id, "stage": "tier1_verified"}


@celery_app.task(bind=True, base=AegisTask, name="tier3.test_task")
def test_tier3_task(self: AegisTask, case_id: str) -> Dict[str, Any]:
    """Test task demonstrating Tier 3 queue routing."""
    self.update_progress(case_id=case_id, stage="hindcasting", percent=25.0, message="Initializing OpenDrift particles")
    self.update_progress(case_id=case_id, stage="hindcasting", percent=100.0, message="Hindcast origin cloud computed")
    return {"status": "success", "case_id": case_id, "stage": "tier3_verified"}


@celery_app.task(bind=True, base=AegisTask, name="tier4.test_task")
def test_tier4_task(self: AegisTask, case_id: str) -> Dict[str, Any]:
    """Test task demonstrating Tier 4 queue routing."""
    self.update_progress(case_id=case_id, stage="correlating", percent=50.0, message="Reconstructing AIS trajectories")
    self.update_progress(case_id=case_id, stage="scoring", percent=100.0, message="Attribution scoring completed")
    return {"status": "success", "case_id": case_id, "stage": "tier4_verified"}
