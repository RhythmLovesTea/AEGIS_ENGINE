"""AEGIS-Marine: Tier 4 AIS Correlation & Attribution Schemas."""

from __future__ import annotations

import uuid
from datetime import datetime
from typing import Any, Dict, List, Optional
from pydantic import Field, field_validator

from backend.app.schemas.common import (
    AISCoverageEnum,
    BaseSchema,
    ConfidenceValue,
    DataSourceEnum,
    GeoJSONPoint,
)


class SubScores(BaseSchema):
    """Rule 2: Persisted 5-component AHP sub-scores [0.0 - 100.0]."""

    spatial: float = Field(..., ge=0.0, le=100.0, description="Spatial Mahalanobis proximity score")
    temporal: float = Field(..., ge=0.0, le=100.0, description="Temporal coincidence decay score")
    kinematic: float = Field(..., ge=0.0, le=100.0, description="Heading alignment & speed modulation")
    anomaly: float = Field(..., ge=0.0, le=100.0, description="Loitering, speed drop, or dark gap score")
    type: float = Field(..., ge=0.0, le=100.0, description="Vessel type risk prior score")


class AISTrackPoint(BaseSchema):
    """Discrete AIS kinematic position report."""

    mmsi: int
    timestamp: datetime
    point: GeoJSONPoint
    sog: Optional[float] = Field(default=None, description="Speed over ground in knots")
    cog: Optional[float] = Field(default=None, description="Course over ground in degrees")
    heading: Optional[float] = Field(default=None, description="True heading in degrees")
    nav_status: Optional[int] = Field(default=None, description="Navigational status code")
    data_source: DataSourceEnum = DataSourceEnum.SYNTHETIC


class VesselCandidateBase(BaseSchema):
    """Ranked candidate vessel entity."""

    mmsi: int
    imo: Optional[int] = None
    name: str
    flag_state: Optional[str] = None
    vessel_type: str
    s_culprit: float = Field(
        ..., ge=0.0, le=100.0, description="Composite AHP-weighted culprit attribution score"
    )
    confidence: ConfidenceValue  # Rule 1: Mandatory confidence

    # Rule 2: Sub-scores must be persisted, never calculated client-side
    sub_scores: SubScores

    anomaly_flags: List[str] = Field(
        default_factory=list,
        description="Flags e.g., ['speed_drop_dumping', 'dark_transponder_gap']",
    )

    # Rule 4: Transponder gap and non-AIS flags
    ais_coverage: AISCoverageEnum = AISCoverageEnum.FULL


class VesselCandidateCreate(VesselCandidateBase):
    """Payload to create candidate vessel record."""

    case_id: uuid.UUID


class VesselCandidateResponse(VesselCandidateBase):
    """API response for a ranked suspect vessel candidate."""

    id: uuid.UUID
    case_id: uuid.UUID
    created_at: datetime


class AHPConfigResponse(BaseSchema):
    """Rule 7: Transparent AHP pairwise matrix, weights, and consistency ratio."""

    version: str
    pairwise_matrix: List[List[float]] = Field(
        ..., description="5x5 AHP Pairwise comparison matrix"
    )
    weights: Dict[str, float] = Field(
        ..., description="Normalized weight vector summing to 1.0"
    )
    consistency_ratio: float = Field(
        ..., lt=0.10, description="Must satisfy Saaty consistency test CR < 0.10"
    )
    created_at: datetime
