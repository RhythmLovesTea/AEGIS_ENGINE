"""AEGIS-Marine: Tier 1 Celery Segmentation Pipeline Task.

Implements asynchronous, idempotent Tier 1 pipeline execution:
1. Ingestion of spaceborne SAR/EO scenes (via CopernicusAdapter / local GeoTIFF).
2. DeepLabv3+ sliding window inference and polarimetric lookalike rejection.
3. Database persistence of SlickDetection entities with PostGIS geometries.
4. State transition: Case status advances to 'characterizing'.
5. Real-time progress broadcasting over Redis Pub/Sub for WebSocket subscribers.
"""

from __future__ import annotations

import logging
import os
import uuid
from datetime import datetime, timezone
from pathlib import Path
from typing import Any, Dict, List, Optional, Union

import shapely.geometry
from geoalchemy2.shape import from_shape
from sqlalchemy.orm import Session

from backend.app.models.entities import Case, CaseStatus, DataSource, SlickDetection
from backend.core.celery_app import AegisTask, celery_app
from backend.core.database import SessionLocal
from backend.services.tier1_segmentation.inference import (
    create_mock_test_tile,
    run_inference_on_geotiff,
)

logger = logging.getLogger("aegis.tier1_tasks")


@celery_app.task(
    bind=True,
    base=AegisTask,
    name="tier1.run_tier1_segmentation",
    autoretry_for=(Exception,),
    retry_kwargs={"max_retries": 3, "countdown": 5},
    retry_backoff=True,
)
def run_tier1_segmentation(
    self: AegisTask,
    case_id: str,
    scene_ref: Optional[str] = None,
    wind_speed_mps: float = 6.5,
    db_session: Optional[Session] = None,
) -> Dict[str, Any]:
    """Execute Tier 1 SAR segmentation and lookalike rejection pipeline.

    Args:
        case_id: UUID of the investigation case.
        scene_ref: Filepath, Copernicus product identifier, or None (defaults to benchmark fixture).
        wind_speed_mps: Environmental wind speed (m/s) for lookalike physics filters.
        db_session: Optional injected SQLAlchemy session for testing.

    Returns:
        Dictionary summarizing detected candidate slick polygons and transition state.
    """
    logger.info("Starting Tier 1 segmentation task for case_id: %s (scene: %s)", case_id, scene_ref)

    # 1. Initial Progress Broadcast
    self.update_progress(
        case_id=case_id,
        stage="detecting",
        percent=10.0,
        message="Initializing Tier 1 segmentation pipeline and resolving scene",
    )

    # 2. Scene Ingestion & File Resolution
    tif_path: Optional[Path] = None
    if scene_ref and Path(scene_ref).exists():
        tif_path = Path(scene_ref)
    elif scene_ref and Path("data/sar") / scene_ref:
        candidate = Path("data/sar") / scene_ref
        if candidate.exists():
            tif_path = candidate

    if tif_path is None:
        # Default to standard benchmark sample or generate mock tile
        sample_s1 = Path("data/sar/sample_s1_iw_grd.tif")
        if sample_s1.exists():
            tif_path = sample_s1
        else:
            default_tile = Path("data/sar/test_tile_fixture.tif")
            create_mock_test_tile(default_tile)
            tif_path = default_tile

    self.update_progress(
        case_id=case_id,
        stage="detecting",
        percent=30.0,
        message=f"Ingested SAR scene {tif_path.name}, running sliding-window DeepLabv3+ inference",
    )

    # 3. Execute Sliding-Window Inference & Physics Diagnostics
    geojson_result = run_inference_on_geotiff(
        tif_path=tif_path,
        wind_speed_mps=wind_speed_mps,
    )
    features: List[Dict[str, Any]] = geojson_result.get("features", [])

    self.update_progress(
        case_id=case_id,
        stage="detecting",
        percent=75.0,
        message=f"Extracted {len(features)} candidate polygon(s) with physics diagnostics",
        extra={"features_count": len(features)},
    )

    # 4. Database Persistence (PostGIS & Relational State)
    close_session_at_end = False
    if db_session is not None:
        db = db_session
    else:
        db = SessionLocal()
        close_session_at_end = True

    persisted_detection_ids: List[str] = []
    primary_confidence: float = 0.0

    try:
        case_uuid = uuid.UUID(str(case_id))

        # Idempotency check: remove prior detections for this case to avoid duplicates
        db.query(SlickDetection).filter(SlickDetection.case_id == case_uuid).delete()

        # Persist extracted detections
        for feat in features:
            props = feat.get("properties", {})
            geom = feat.get("geometry", {})

            poly_shape = shapely.geometry.shape(geom)
            if not poly_shape.is_valid:
                poly_shape = poly_shape.buffer(0)
            centroid_shape = poly_shape.centroid

            conf = float(props.get("confidence", 0.0))
            if conf > primary_confidence:
                primary_confidence = conf

            data_source = (
                DataSource.SYNTHETIC
                if "synthetic" in str(tif_path).lower() or "test" in str(tif_path).lower()
                else DataSource.LIVE
            )

            det_id = uuid.uuid4()
            detection = SlickDetection(
                id=det_id,
                case_id=case_uuid,
                polygon=from_shape(poly_shape, srid=4326),
                centroid=from_shape(centroid_shape, srid=4326),
                area_m2=float(props.get("area_m2", 0.0)),
                confidence=conf,  # Rule 1 compliance
                lookalike_risk=float(props.get("lookalike_risk", 0.0)),
                sensor="Sentinel-1 SAR IW",
                detection_time=datetime.now(timezone.utc),
                data_source=data_source,
            )
            db.add(detection)
            db.flush()
            persisted_detection_ids.append(str(det_id))

        # 5. Transition Case Status to 'characterizing'
        case_entity = db.query(Case).filter(Case.id == case_uuid).first()
        if case_entity:
            case_entity.status = CaseStatus.CHARACTERIZING
            db.add(case_entity)

        db.commit()

        # 6. Final Progress Broadcast
        self.update_progress(
            case_id=case_id,
            stage="characterizing",
            percent=100.0,
            message="Tier 1 segmentation complete. Case transitioned to characterizing.",
            extra={
                "persisted_detections": len(persisted_detection_ids),
                "primary_confidence": primary_confidence,
            },
        )

        return {
            "status": "success",
            "case_id": str(case_id),
            "stage": "characterizing",
            "scene_ref": str(tif_path),
            "detections_count": len(persisted_detection_ids),
            "detection_ids": persisted_detection_ids,
            "primary_confidence": primary_confidence,
        }

    except Exception as exc:
        db.rollback()
        logger.error("Error executing Tier 1 segmentation task: %s", exc, exc_info=True)
        raise exc
    finally:
        if close_session_at_end:
            db.close()
