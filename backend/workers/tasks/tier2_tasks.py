"""AEGIS-Marine: Tier 2 Celery Characterization Pipeline Task.

Implements asynchronous, idempotent Tier 2 pipeline execution:
1. Retrieval of Tier 1 SlickDetection PostGIS geometries.
2. Geodesic morphometry: UTM projection, area, perimeter, circularity, PCA principal axis (theta_slick).
3. Bonn Agreement Oil Appearance Code (BAOAC 1-5) volumetric thickness profiling.
4. Physical inversion of Fay's mechanical spreading laws to estimate elapsed spill age (t_age).
5. Database persistence of SlickCharacterization entity (Rule 1 age confidence).
6. State transition: Case status advances to 'hindcasting'.
7. Real-time progress broadcasting over Redis Pub/Sub for WebSocket subscribers.
"""

from __future__ import annotations

import logging
import uuid
from typing import Any, Dict, Optional

from geoalchemy2.shape import to_shape
from sqlalchemy.orm import Session

from backend.app.models.entities import (
    Case,
    CaseStatus,
    SlickCharacterization,
    SlickDetection,
)
from backend.core.celery_app import AegisTask, celery_app
from backend.core.database import SessionLocal
from backend.services.tier2_morphometry.morphometry import analyze_slick_morphometry
from backend.services.tier2_morphometry.spreading_aging import estimate_spill_age
from backend.services.tier2_morphometry.thickness_profiler import profile_slick_thickness

logger = logging.getLogger("aegis.tier2_tasks")


@celery_app.task(
    bind=True,
    base=AegisTask,
    name="tier2.run_tier2_characterization",
    autoretry_for=(Exception,),
    retry_kwargs={"max_retries": 3, "countdown": 5},
    retry_backoff=True,
)
def run_tier2_characterization(
    self: AegisTask,
    case_id: str,
    db_session: Optional[Session] = None,
) -> Dict[str, Any]:
    """Execute Tier 2 morphometry, thickness profiling, and Fay spreading age inversion.

    Args:
        case_id: UUID string of the target investigation case.
        db_session: Optional injected SQLAlchemy session for testing.

    Returns:
        Dictionary summarizing extracted physical characteristics and state transition.
    """
    logger.info("Starting Tier 2 characterization task for case_id: %s", case_id)

    # 1. Initial Progress Broadcast
    self.update_progress(
        case_id=case_id,
        stage="characterizing",
        percent=10.0,
        message="Initializing Tier 2 characterization pipeline and resolving SlickDetection",
    )

    close_session_at_end = False
    if db_session is not None:
        db = db_session
    else:
        db = SessionLocal()
        close_session_at_end = True

    try:
        case_uuid = uuid.UUID(str(case_id))

        # 2. Fetch primary SlickDetection record for this case
        detection = (
            db.query(SlickDetection)
            .filter(SlickDetection.case_id == case_uuid)
            .order_by(SlickDetection.confidence.desc())
            .first()
        )

        if not detection:
            raise ValueError(
                f"No SlickDetection records found for case {case_id}. Tier 1 detection must precede Tier 2."
            )

        poly_wgs84 = to_shape(detection.polygon)

        # 3. Morphometry Analysis
        self.update_progress(
            case_id=case_id,
            stage="characterizing",
            percent=35.0,
            message="Computing metric UTM projection, spatial moments, PCA orientation, and skeleton",
        )

        morph_result = analyze_slick_morphometry(poly_wgs84)

        # 4. BAOAC Thickness Profiling & Volumetric Integration
        self.update_progress(
            case_id=case_id,
            stage="characterizing",
            percent=65.0,
            message="Classifying BAOAC appearance codes (1-5) and computing integrated volume",
        )

        # Infer damping ratio from detection confidence/risk or use nominal 9.0 dB
        damping_db = 9.0
        if hasattr(detection, "lookalike_risk") and detection.lookalike_risk <= 0.2:
            damping_db = 10.5

        thickness_profile = profile_slick_thickness(
            area_m2=morph_result.area_m2,
            damping_ratio_db=damping_db,
        )

        # 5. Fay Mechanical Spreading Age Inversion
        self.update_progress(
            case_id=case_id,
            stage="characterizing",
            percent=85.0,
            message="Inverting Fay mechanical spreading laws to estimate elapsed spill age",
        )

        age_result = estimate_spill_age(
            area_m2=morph_result.area_m2,
            estimated_volume_m3=thickness_profile.estimated_volume_m3,
        )

        # 6. Idempotent Persistence in PostgreSQL
        # Clear any prior characterizations for this case
        db.query(SlickCharacterization).filter(SlickCharacterization.case_id == case_uuid).delete()

        char_id = uuid.uuid4()
        characterization = SlickCharacterization(
            id=char_id,
            case_id=case_uuid,
            perimeter_m=morph_result.perimeter_m,
            principal_axis_deg=morph_result.principal_axis_deg,
            baoac_code=thickness_profile.dominant_baoac_code,
            estimated_volume_m3=thickness_profile.estimated_volume_m3,
            t_age_hours=age_result.t_age_hours,
            age_confidence=age_result.confidence,  # Rule 1 compliance
        )
        db.add(characterization)

        # 7. Advance Case Status to 'hindcasting'
        case_entity = db.query(Case).filter(Case.id == case_uuid).first()
        if case_entity:
            case_entity.status = CaseStatus.HINDCASTING
            db.add(case_entity)

        db.commit()

        # 8. Final Progress Broadcast
        self.update_progress(
            case_id=case_id,
            stage="hindcasting",
            percent=100.0,
            message=f"Tier 2 complete. Slick age estimated at {age_result.t_age_hours}h. Case transitioned to hindcasting.",
            extra={
                "characterization_id": str(char_id),
                "area_m2": morph_result.area_m2,
                "perimeter_m": morph_result.perimeter_m,
                "principal_axis_deg": morph_result.principal_axis_deg,
                "baoac_code": thickness_profile.dominant_baoac_code,
                "estimated_volume_m3": thickness_profile.estimated_volume_m3,
                "t_age_hours": age_result.t_age_hours,
                "age_confidence": age_result.confidence,
            },
        )

        return {
            "status": "success",
            "case_id": str(case_id),
            "stage": "hindcasting",
            "characterization_id": str(char_id),
            "area_m2": morph_result.area_m2,
            "perimeter_m": morph_result.perimeter_m,
            "principal_axis_deg": morph_result.principal_axis_deg,
            "baoac_code": thickness_profile.dominant_baoac_code,
            "estimated_volume_m3": thickness_profile.estimated_volume_m3,
            "t_age_hours": age_result.t_age_hours,
            "age_confidence": age_result.confidence,
        }

    except Exception as exc:
        db.rollback()
        logger.error("Error executing Tier 2 characterization task: %s", exc, exc_info=True)
        raise exc
    finally:
        if close_session_at_end:
            db.close()
