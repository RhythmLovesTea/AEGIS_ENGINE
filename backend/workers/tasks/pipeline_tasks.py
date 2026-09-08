"""AEGIS-Marine: Scaffolding and Verification Tasks for Celery Pipeline."""

from __future__ import annotations

from typing import Any

from backend.core.celery_app import AegisTask, celery_app


@celery_app.task(bind=True, base=AegisTask, name="tier1.test_task")
def test_tier1_task(self: AegisTask, case_id: str) -> dict[str, Any]:
    """Test task demonstrating Tier 1 queue routing and progress reporting."""
    self.update_progress(
        case_id=case_id, stage="detecting", percent=10.0, message="Ingesting test SAR scene"
    )
    self.update_progress(
        case_id=case_id, stage="detecting", percent=50.0, message="Executing segmentation inference"
    )
    self.update_progress(
        case_id=case_id, stage="detecting", percent=100.0, message="Segmentation complete"
    )
    return {"status": "success", "case_id": case_id, "stage": "tier1_verified"}


@celery_app.task(bind=True, base=AegisTask, name="tier3.test_task")
def test_tier3_task(self: AegisTask, case_id: str) -> dict[str, Any]:
    """Test task demonstrating Tier 3 queue routing."""
    self.update_progress(
        case_id=case_id,
        stage="hindcasting",
        percent=25.0,
        message="Initializing OpenDrift particles",
    )
    self.update_progress(
        case_id=case_id,
        stage="hindcasting",
        percent=100.0,
        message="Hindcast origin cloud computed",
    )
    return {"status": "success", "case_id": case_id, "stage": "tier3_verified"}


@celery_app.task(bind=True, base=AegisTask, name="tier4.test_task")
def test_tier4_task(self: AegisTask, case_id: str) -> dict[str, Any]:
    """Test task demonstrating Tier 4 queue routing."""
    self.update_progress(
        case_id=case_id,
        stage="correlating",
        percent=50.0,
        message="Reconstructing AIS trajectories",
    )
    self.update_progress(
        case_id=case_id, stage="scoring", percent=100.0, message="Attribution scoring completed"
    )
    return {"status": "success", "case_id": case_id, "stage": "tier4_verified"}


@celery_app.task(
    bind=True,
    base=AegisTask,
    name="orchestration.run_what_if_scenario",
    autoretry_for=(Exception,),
    retry_kwargs={"max_retries": 2, "countdown": 3},
)
def run_what_if_scenario_task(
    self: AegisTask,
    case_id: str,
    request_params: dict[str, Any],
    user_id: str = "analyst",
) -> dict[str, Any]:
    """Asynchronous Celery task to execute a What-If scenario under overridden parameters.

    Re-runs Tier 3 (hindcast), Tier 4 (correlation & scoring), and Explainability
    while preserving Tier 1 segmentation outputs.
    """
    from backend.app.schemas.case import WhatIfRequest
    from backend.core.database import SessionLocal
    from backend.services.orchestration.what_if_service import get_what_if_service

    self.update_progress(
        case_id=case_id,
        stage="hindcasting",
        percent=20.0,
        message="Initializing What-If hydrodynamic simulation with overridden parameters",
    )

    req = WhatIfRequest.model_validate(request_params)
    service = get_what_if_service()

    with SessionLocal() as db:
        self.update_progress(
            case_id=case_id,
            stage="correlating",
            percent=60.0,
            message="Re-correlating AIS trajectories and computing AHP attribution scores",
        )
        res = service.run_scenario(
            case_id=case_id,
            request=req,
            db_session=db,
            user_id=user_id,
        )

    self.update_progress(
        case_id=case_id,
        stage="scoring",
        percent=100.0,
        message="What-If scenario simulation complete and cached",
    )

    return res.model_dump(mode="json")
