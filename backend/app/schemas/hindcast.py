"""AEGIS-Marine: Tier 3 Hydrodynamic Hindcast & Forecast Schemas."""

from __future__ import annotations

import uuid
from datetime import datetime
from typing import Any, Dict, Optional
from pydantic import Field

from backend.app.schemas.common import (
    BaseSchema,
    ConfidenceValue,
    GeoJSONPoint,
    GeoJSONPolygon,
)


class ParticleState(BaseSchema):
    """Lagrangian advection particle state at a discrete timestep."""

    particle_id: int
    timestamp: datetime
    point: GeoJSONPoint
    depth_m: float = 0.0
    mass_fraction: float = Field(default=1.0, ge=0.0, le=1.0)
    status: str = Field(default="active", description="'active' | 'beached' | 'evaporated'")


class OriginEstimateBase(BaseSchema):
    """Probabilistic origin density estimate."""

    centroid: GeoJSONPoint
    covariance_matrix: Dict[str, Any] = Field(
        ..., description="2x2 spatial covariance matrix [[var_lat, cov], [cov, var_lon]]"
    )
    time_window_start: datetime
    time_window_end: datetime
    confidence_pct: ConfidenceValue  # Rule 1: Mandatory origin confidence
    region_area_km2: float = Field(..., gt=0.0, description="3-sigma uncertainty contour area")
    particle_trajectory_ref: Optional[str] = None


class OriginEstimateCreate(OriginEstimateBase):
    """Payload to create origin estimate."""

    case_id: uuid.UUID


class OriginEstimateResponse(OriginEstimateBase):
    """Response payload for origin estimate."""

    id: uuid.UUID
    case_id: uuid.UUID
    created_at: datetime


class ForwardForecastBase(BaseSchema):
    """Forward trajectory weathering and shoreline impact forecast."""

    etb_hours: Optional[float] = Field(
        default=None, description="Estimated Time of Beaching (ETB) in hours"
    )
    cvi_index: Optional[float] = Field(
        default=None, ge=0.0, le=1.0, description="Coastal Vulnerability Index"
    )
    beached_volume_m3: Optional[float] = Field(
        default=None, ge=0.0, description="Estimated beached hydrocarbon volume"
    )
    shoreline_impact_polygon: Optional[GeoJSONPolygon] = None


class ForwardForecastResponse(ForwardForecastBase):
    """Response payload for forward forecast."""

    id: uuid.UUID
    case_id: uuid.UUID
    created_at: datetime
