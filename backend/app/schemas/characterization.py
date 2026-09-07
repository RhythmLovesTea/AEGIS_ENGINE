"""AEGIS-Marine: Tier 2 Morphometry & Spreading Aging Schemas."""

from __future__ import annotations

import uuid
from datetime import datetime
from pydantic import Field

from backend.app.schemas.common import BaseSchema, ConfidenceValue


class SlickCharacterizationBase(BaseSchema):
    """Tier 2 characterization properties."""

    perimeter_m: float = Field(..., gt=0.0, description="Measured perimeter in meters")
    principal_axis_deg: float = Field(
        ..., ge=0.0, lt=360.0, description="Principal orientation axis [0.0 - 360.0) degrees"
    )
    baoac_code: int = Field(
        ..., ge=1, le=5, description="Bonn Agreement Oil Appearance Code (1=Sheen to 5=Continuous)"
    )
    estimated_volume_m3: float = Field(
        ..., ge=0.0, description="Estimated total slick volume in cubic meters"
    )
    t_age_hours: float = Field(
        ..., ge=0.0, description="Fay spreading model mechanical inverted age in hours"
    )
    age_confidence: ConfidenceValue  # Rule 1: Mandatory paired age confidence


class SlickCharacterizationCreate(SlickCharacterizationBase):
    """Payload to create characterization."""

    case_id: uuid.UUID


class SlickCharacterizationResponse(SlickCharacterizationBase):
    """Response payload for slick characterization."""

    id: uuid.UUID
    case_id: uuid.UUID
    created_at: datetime
