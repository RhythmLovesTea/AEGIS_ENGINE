"""AEGIS-Marine: Tier 3 Celery Hydrodynamic Hindcast & Forecast Pipeline Task.

Implements asynchronous, idempotent Tier 3 pipeline execution:
1. Retrieval of Tier 1 SlickDetection and Tier 2 SlickCharacterization entities.
2. Ingestion or fallback generation of met-ocean environmental forcing (surface currents & winds).
3. Backward Lagrangian particle hindcasting (Sub-Module 3A, N >= 10,000, dt = -15 min).
4. Probabilistic 2D Gaussian Kernel Density Estimation (KDE) origin localization (centroid, covariance, ellipses).
5. Forward +72h trajectory forecasting with Mackay weathering and coastal beaching detection (Sub-Module 3B).
6. Bulk insertion of Lagrangian particle trajectory snapshots into TimescaleDB hypertable for UI replay.
7. PostgreSQL persistence of OriginEstimate and ForwardForecast records.
8. State transition: Case status advances to 'correlating'.
9. Real-time progress broadcasting over Redis Pub/Sub for WebSocket subscribers.

Adheres to:
- PRD Section 10 & Architecture Section 4.3 & Section 6.
- Rule 1: Mandatory confidence scores in [0.0, 100.0].
- Rule 4: Data source identification ('live' | 'cached' | 'synthetic').
- Rule 6: Zero occurrences of banned terms.
"""

from __future__ import annotations

import logging
import uuid
from datetime import UTC, timedelta
from typing import Any

import xarray as xr
from geoalchemy2.shape import from_shape, to_shape
from shapely.geometry import Point, shape
from sqlalchemy.orm import Session

from backend.app.models.entities import (
    Case,
    CaseStatus,
    ForwardForecast,
    OriginEstimate,
    ParticleTrajectory,
    SlickCharacterization,
    SlickDetection,
)
from backend.core.celery_app import AegisTask, celery_app
from backend.core.database import SessionLocal
from backend.services.data_adapters.metocean_adapter import (
    MetoceanAdapter,
    MetoceanQuery,
)
from backend.services.tier3_hindcast.forecast_runner import (
    ForecastConfig,
    ForwardForecastResult,
    ForwardForecastRunner,
)
from backend.services.tier3_hindcast.hindcast_runner import (
    HindcastConfig,
    HindcastResult,
    LagrangianHindcastRunner,
)
from backend.services.tier3_hindcast.origin_estimator import (
    OriginDensityEstimator,
    OriginEstimateResult,
)

logger = logging.getLogger("aegis.tier3_tasks")


@celery_app.task(
    bind=True,
    base=AegisTask,
    name="tier3.run_tier3_hindcast",
    autoretry_for=(Exception,),
    retry_kwargs={"max_retries": 3, "countdown": 5},
    retry_backoff=True,
)
def run_tier3_hindcast(
    self: AegisTask,
    case_id: str,
    db_session: Session | None = None,
    forcing_dataset: xr.Dataset | None = None,
    coastline_polygon: Any | None = None,
    n_hindcast_particles: int | None = None,
    n_forecast_particles: int | None = None,
    include_forecast: bool = True,
) -> dict[str, Any]:
    """Execute Tier 3 backward Lagrangian hindcast, origin estimation, and forward forecast.

    Args:
        case_id: UUID string of the target investigation case.
        db_session: Optional injected SQLAlchemy session for testing.
        forcing_dataset: Optional pre-loaded or mock met-ocean xarray Dataset.
        coastline_polygon: Optional GSHHG coastline polygon for beaching detection.
        n_hindcast_particles: Optional particle count override for backward hindcast.
        n_forecast_particles: Optional particle count override for forward forecast.
        include_forecast: Whether to execute forward trajectory and weathering forecast (default True).

    Returns:
        Dictionary summarizing origin estimate, forward forecast, and state transition.
    """
    logger.info("Starting Tier 3 hydrodynamic simulation task for case_id: %s", case_id)

    # 1. Initial Progress Broadcast
    self.update_progress(
        case_id=case_id,
        stage="hindcasting",
        percent=5.0,
        message="Initializing Tier 3 hydrodynamic simulation and retrieving case entities",
    )

    close_session_at_end = False
    if db_session is not None:
        db = db_session
    else:
        db = SessionLocal()
        close_session_at_end = True

    try:
        case_uuid = uuid.UUID(str(case_id))

        # 2. Retrieve primary SlickDetection and SlickCharacterization records
        detection = (
            db.query(SlickDetection)
            .filter(SlickDetection.case_id == case_uuid)
            .order_by(SlickDetection.confidence.desc())
            .first()
        )
        if not detection:
            raise ValueError(
                f"No SlickDetection records found for case {case_id}. Tier 1 detection must precede Tier 3."
            )

        characterization = (
            db.query(SlickCharacterization)
            .filter(SlickCharacterization.case_id == case_uuid)
            .order_by(SlickCharacterization.created_at.desc())
            .first()
        )
        if not characterization:
            raise ValueError(
                f"No SlickCharacterization records found for case {case_id}. Tier 2 characterization must precede Tier 3."
            )

        poly_wgs84 = to_shape(detection.polygon)
        t_obs = detection.detection_time
        if t_obs.tzinfo is None:
            t_obs = t_obs.replace(tzinfo=UTC)

        t_age_hours = max(0.5, float(characterization.t_age_hours))
        initial_volume_m3 = max(1.0, float(characterization.estimated_volume_m3))

        # 3. Met-Ocean Environmental Forcing Ingestion
        self.update_progress(
            case_id=case_id,
            stage="hindcasting",
            percent=20.0,
            message="Acquiring met-ocean environmental forcing field (surface currents & winds)",
        )

        if forcing_dataset is not None:
            forcing_ds = forcing_dataset
        else:
            min_lon, min_lat, max_lon, max_lat = poly_wgs84.bounds
            # Expand bounding box by 1.2 degrees to accommodate particle drift trajectories
            query_bbox = (
                min_lon - 1.2,
                min_lat - 1.2,
                max_lon + 1.2,
                max_lat + 1.2,
            )
            time_start = t_obs - timedelta(hours=t_age_hours + 8.0)
            time_end = t_obs + timedelta(hours=76.0 if include_forecast else 4.0)

            adapter = MetoceanAdapter()
            query = MetoceanQuery(
                bbox=query_bbox,
                time_start=time_start,
                time_end=time_end,
            )
            forcing_ds = adapter.fetch_forcing_field(query)

        # 4. Backward Lagrangian Hindcasting (Sub-Module 3A)
        p_count_hindcast = n_hindcast_particles if n_hindcast_particles is not None else 10000
        self.update_progress(
            case_id=case_id,
            stage="hindcasting",
            percent=40.0,
            message=f"Executing backward Lagrangian advection (N={p_count_hindcast}, dt=-15min)",
        )

        hindcast_cfg = HindcastConfig(
            n_particles=p_count_hindcast,
            time_step_minutes=-15.0,
        )
        hindcast_runner = LagrangianHindcastRunner(config=hindcast_cfg)
        hindcast_result: HindcastResult = hindcast_runner.run_hindcast(
            slick_polygon=poly_wgs84,
            t_obs=t_obs,
            t_age_hours=t_age_hours,
            forcing_ds=forcing_ds,
            case_id=case_id,
        )

        # 5. Probabilistic 2D Gaussian Kernel Density Origin Estimation
        self.update_progress(
            case_id=case_id,
            stage="hindcasting",
            percent=60.0,
            message="Computing 2D Gaussian KDE origin mode, covariance matrix, and confidence ellipses",
        )

        origin_estimator = OriginDensityEstimator()
        origin_result: OriginEstimateResult = origin_estimator.estimate_origin(
            hindcast_result=hindcast_result,
            case_id=case_id,
        )

        # 6. Forward Trajectory Forecasting & Mackay Weathering (Sub-Module 3B)
        forecast_result: ForwardForecastResult | None = None
        if include_forecast:
            p_count_forecast = n_forecast_particles if n_forecast_particles is not None else 5000
            self.update_progress(
                case_id=case_id,
                stage="hindcasting",
                percent=75.0,
                message=f"Executing forward +72h forecast with Mackay weathering (N={p_count_forecast})",
            )

            forecast_cfg = ForecastConfig(
                n_particles=p_count_forecast,
                forecast_hours=72.0,
                time_step_minutes=15.0,
                initial_volume_m3=initial_volume_m3,
            )
            forecast_runner = ForwardForecastRunner(config=forecast_cfg)
            forecast_result = forecast_runner.run_forecast(
                slick_polygon=poly_wgs84,
                t_obs=t_obs,
                forcing_ds=forcing_ds,
                coastline_polygon=coastline_polygon,
                initial_volume_m3=initial_volume_m3,
                case_id=case_id,
            )

        # 7. Bulk Persist Particle Trajectory Snapshots into TimescaleDB Hypertable
        self.update_progress(
            case_id=case_id,
            stage="hindcasting",
            percent=85.0,
            message="Persisting particle trajectory time-series snapshots into TimescaleDB hypertable",
        )

        # Idempotent cleanup of prior particle trajectories for this case
        db.query(ParticleTrajectory).filter(ParticleTrajectory.case_id == case_uuid).delete()

        trajectory_records: list[ParticleTrajectory] = []

        # Ingest backward hindcast trajectory snapshots
        for snapshot in hindcast_result.snapshots:
            snap_time = snapshot.timestamp
            if snap_time.tzinfo is None:
                snap_time = snap_time.replace(tzinfo=UTC)

            for p_idx, coord in enumerate(snapshot.subsample_coords):
                lon, lat = coord[0], coord[1]
                pt_point = from_shape(Point(lon, lat), srid=4326)
                trajectory_records.append(
                    ParticleTrajectory(
                        case_id=case_uuid,
                        particle_id=p_idx,
                        timestamp=snap_time,
                        point=pt_point,
                        depth_m=0.0,
                        mass_fraction=1.0,
                        status="active",
                    )
                )

        # Ingest forward forecast trajectory snapshots if available
        if forecast_result is not None:
            for snapshot in forecast_result.snapshots:
                snap_time = snapshot.timestamp
                if snap_time.tzinfo is None:
                    snap_time = snap_time.replace(tzinfo=UTC)

                remaining_mass = max(0.0, min(1.0, 1.0 - snapshot.weathering.evaporated_fraction))

                for p_idx, coord in enumerate(snapshot.subsample_coords):
                    lon, lat = coord[0], coord[1]
                    p_status = "beached" if p_idx < snapshot.n_beached else "active"
                    pt_point = from_shape(Point(lon, lat), srid=4326)
                    trajectory_records.append(
                        ParticleTrajectory(
                            case_id=case_uuid,
                            particle_id=10000 + p_idx,  # Distinct ID space for forward particles
                            timestamp=snap_time,
                            point=pt_point,
                            depth_m=0.0,
                            mass_fraction=round(remaining_mass, 4),
                            status=p_status,
                        )
                    )

        if trajectory_records:
            db.add_all(trajectory_records)

        # 8. Persist OriginEstimate and ForwardForecast in PostgreSQL
        self.update_progress(
            case_id=case_id,
            stage="hindcasting",
            percent=95.0,
            message="Persisting OriginEstimate and ForwardForecast entities in PostgreSQL",
        )

        # Idempotent cleanup of prior estimates and forecasts
        db.query(OriginEstimate).filter(OriginEstimate.case_id == case_uuid).delete()
        db.query(ForwardForecast).filter(ForwardForecast.case_id == case_uuid).delete()

        # OriginEstimate persistence
        origin_point = from_shape(
            Point(origin_result.centroid[0], origin_result.centroid[1]), srid=4326
        )
        origin_id = uuid.uuid4()
        origin_entity = OriginEstimate(
            id=origin_id,
            case_id=case_uuid,
            centroid=origin_point,
            covariance_matrix=origin_result.covariance_matrix,
            time_window_start=origin_result.time_window_start,
            time_window_end=origin_result.time_window_end,
            confidence_pct=origin_result.confidence_pct,  # Rule 1 compliance
            region_area_km2=origin_result.region_area_km2,
            particle_trajectory_ref=f"particle_trajectories:{case_uuid}",
        )
        db.add(origin_entity)

        # ForwardForecast persistence (if computed)
        forecast_id: uuid.UUID | None = None
        if forecast_result is not None:
            impact_poly_geom = None
            if forecast_result.shoreline_impact_polygon is not None:
                impact_shape = shape(forecast_result.shoreline_impact_polygon)
                impact_poly_geom = from_shape(impact_shape, srid=4326)

            forecast_id = uuid.uuid4()
            forecast_entity = ForwardForecast(
                id=forecast_id,
                case_id=case_uuid,
                etb_hours=forecast_result.etb_hours,
                cvi_index=forecast_result.cvi_index,
                beached_volume_m3=forecast_result.beached_volume_m3,
                shoreline_impact_polygon=impact_poly_geom,
            )
            db.add(forecast_entity)

        # 9. Advance Case State to 'correlating'
        case_entity = db.query(Case).filter(Case.id == case_uuid).first()
        if case_entity:
            case_entity.status = CaseStatus.CORRELATING
            db.add(case_entity)

        db.commit()

        # 10. Final Progress Broadcast
        summary_payload = {
            "origin_estimate_id": str(origin_id),
            "origin_centroid": list(origin_result.centroid),
            "region_area_km2": origin_result.region_area_km2,
            "confidence_pct": origin_result.confidence_pct,
            "forecast_id": str(forecast_id) if forecast_id else None,
            "etb_hours": forecast_result.etb_hours if forecast_result else None,
            "cvi_index": forecast_result.cvi_index if forecast_result else None,
            "beached_volume_m3": forecast_result.beached_volume_m3 if forecast_result else None,
            "trajectories_persisted": len(trajectory_records),
        }

        self.update_progress(
            case_id=case_id,
            stage="correlating",
            percent=100.0,
            message="Tier 3 simulation complete. Origin localized and trajectories saved. Case transitioned to correlating.",
            extra=summary_payload,
        )

        return {
            "status": "success",
            "case_id": str(case_id),
            "stage": "correlating",
            **summary_payload,
        }

    except Exception as exc:
        db.rollback()
        logger.error("Error executing Tier 3 hindcast task: %s", exc, exc_info=True)
        raise exc
    finally:
        if close_session_at_end:
            db.close()
