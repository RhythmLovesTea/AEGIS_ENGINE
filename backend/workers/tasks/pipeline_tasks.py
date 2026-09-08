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


@celery_app.task(
    bind=True,
    base=AegisTask,
    name="explain.run_explainability",
    autoretry_for=(Exception,),
    retry_kwargs={"max_retries": 2, "countdown": 3},
)
def run_explainability_task(
    self: AegisTask,
    case_id: str,
    db_session: Any | None = None,
) -> dict[str, Any]:
    """Asynchronous Celery task to evaluate non-vessel alternative hypotheses (Rule 5)."""
    import uuid
    from backend.app.models.entities import Case, CaseStatus
    from backend.core.database import SessionLocal
    from backend.services.explainability.alternative_engine import AlternativeExplanationEngine

    self.update_progress(
        case_id=case_id,
        stage="explaining",
        percent=25.0,
        message="Evaluating non-vessel alternative hypotheses (seep, lookalike, dark vessel)",
    )

    close_session = False
    if db_session is not None:
        db = db_session
    else:
        db = SessionLocal()
        close_session = True

    try:
        engine = AlternativeExplanationEngine()
        persisted = engine.evaluate_and_persist_case(db=db, case_id=case_id)

        case_entity = db.query(Case).filter(Case.id == uuid.UUID(str(case_id))).first()
        if case_entity:
            case_entity.status = CaseStatus.SCORING
            db.add(case_entity)
            db.commit()

        self.update_progress(
            case_id=case_id,
            stage="explaining",
            percent=100.0,
            message="Alternative hypotheses evaluated and persisted",
            extra={"hypotheses_count": len(persisted)},
        )

        return {
            "status": "success",
            "case_id": str(case_id),
            "stage": "explaining",
            "hypotheses_count": len(persisted),
            "hypotheses": [h.hypothesis for h in persisted],
        }
    finally:
        if close_session:
            db.close()


@celery_app.task(
    bind=True,
    base=AegisTask,
    name="dossier.run_dossier_compilation",
    autoretry_for=(Exception,),
    retry_kwargs={"max_retries": 2, "countdown": 3},
)
def run_dossier_task(
    self: AegisTask,
    case_id: str,
    db_session: Any | None = None,
    generated_by: str = "AEGIS Automated Forensic Pipeline",
) -> dict[str, Any]:
    """Asynchronous Celery task to compile court-ready PDF legal dossier (FR-20, C13)."""
    import uuid
    from backend.app.models.entities import (
        AlternativeExplanation,
        Case,
        CaseStatus,
        OriginEstimate,
        SlickCharacterization,
        SlickDetection,
        VesselCandidate,
    )
    from backend.core.database import SessionLocal
    from backend.services.dossier.dossier_generator import DossierGenerator

    self.update_progress(
        case_id=case_id,
        stage="dossier",
        percent=30.0,
        message="Compiling official legal evidence dossier with SHA-256 seal",
    )

    close_session = False
    if db_session is not None:
        db = db_session
    else:
        db = SessionLocal()
        close_session = True

    try:
        case_uuid = uuid.UUID(str(case_id))
        case_entity = db.query(Case).filter(Case.id == case_uuid).first()
        if not case_entity:
            raise ValueError(f"Case {case_id} not found.")

        detection = (
            db.query(SlickDetection)
            .filter(SlickDetection.case_id == case_uuid)
            .order_by(SlickDetection.confidence.desc())
            .first()
        )
        characterization = (
            db.query(SlickCharacterization)
            .filter(SlickCharacterization.case_id == case_uuid)
            .order_by(SlickCharacterization.created_at.desc())
            .first()
        )
        origin = (
            db.query(OriginEstimate)
            .filter(OriginEstimate.case_id == case_uuid)
            .order_by(OriginEstimate.confidence_pct.desc())
            .first()
        )
        candidates = (
            db.query(VesselCandidate)
            .filter(VesselCandidate.case_id == case_uuid)
            .order_by(VesselCandidate.s_culprit.desc())
            .all()
        )
        alternatives = (
            db.query(AlternativeExplanation)
            .filter(AlternativeExplanation.case_id == case_uuid)
            .all()
        )

        generator = DossierGenerator()
        result = generator.generate_dossier(
            case_id=case_uuid,
            detection=detection,
            characterization=characterization,
            origin=origin,
            candidates=candidates,
            alternatives=alternatives,
            generated_by=generated_by,
            db_session=db,
        )

        case_entity.status = CaseStatus.READY
        db.add(case_entity)
        db.commit()

        self.update_progress(
            case_id=case_id,
            stage="completed",
            percent=100.0,
            message="Court-ready legal evidence dossier compiled and sealed",
            extra={"sha256": result.sha256_hash},
        )

        return {
            "status": "success",
            "case_id": str(case_id),
            "stage": "completed",
            "sha256_hash": result.sha256_hash,
            "pdf_ref": result.pdf_ref,
            "file_size_bytes": result.file_size_bytes,
        }
    finally:
        if close_session:
            db.close()


def build_full_pipeline_chain(case_id: str, scene_ref: str | None = None) -> Any:
    """Builds a Celery chain connecting all 6 pipeline stages from Tier 1 to Legal Dossier."""
    from celery import chain
    from backend.workers.tasks.tier1_tasks import run_tier1_segmentation
    from backend.workers.tasks.tier2_tasks import run_tier2_characterization
    from backend.workers.tasks.tier3_tasks import run_tier3_hindcast
    from backend.workers.tasks.tier4_tasks import run_tier4_correlation

    return chain(
        run_tier1_segmentation.si(case_id=case_id, scene_ref=scene_ref),
        run_tier2_characterization.si(case_id=case_id),
        run_tier3_hindcast.si(case_id=case_id),
        run_tier4_correlation.si(case_id=case_id),
        run_explainability_task.si(case_id=case_id),
        run_dossier_task.si(case_id=case_id),
    )


def run_full_pipeline_sync(
    case_id: str,
    scene_ref: str | None = None,
    wind_speed_mps: float = 6.5,
    ais_csv_path: Any = None,
    forcing_dataset: Any = None,
    db_session: Any | None = None,
) -> dict[str, Any]:
    """Synchronously executes the full end-to-end pipeline across all 6 stages.

    Ideal for integration and benchmark testing where deterministic sequential execution is required.
    """
    from backend.workers.tasks.tier1_tasks import run_tier1_segmentation
    from backend.workers.tasks.tier2_tasks import run_tier2_characterization
    from backend.workers.tasks.tier3_tasks import run_tier3_hindcast
    from backend.workers.tasks.tier4_tasks import run_tier4_correlation

    t1_res = run_tier1_segmentation(
        case_id=case_id,
        scene_ref=scene_ref,
        wind_speed_mps=wind_speed_mps,
        db_session=db_session,
    )
    t2_res = run_tier2_characterization(
        case_id=case_id,
        db_session=db_session,
    )
    t3_res = run_tier3_hindcast(
        case_id=case_id,
        forcing_dataset=forcing_dataset,
        db_session=db_session,
    )
    t4_res = run_tier4_correlation(
        case_id=case_id,
        ais_csv_path=ais_csv_path,
        db_session=db_session,
    )
    explain_res = run_explainability_task(
        case_id=case_id,
        db_session=db_session,
    )
    dossier_res = run_dossier_task(
        case_id=case_id,
        db_session=db_session,
    )

    return {
        "status": "success",
        "case_id": case_id,
        "tier1": t1_res,
        "tier2": t2_res,
        "tier3": t3_res,
        "tier4": t4_res,
        "explain": explain_res,
        "dossier": dossier_res,
    }
