"""AEGIS-Marine: Tier 1 Detection Pydantic Schemas."""

from __future__ import annotations

import uuid
from datetime import datetime
from typing import Optional
from pydantic import Field

from backend.app.schemas.common import (
    BaseSchema,
    ConfidenceValue,
    DataSourceEnum,
    GeoJSONPoint,
    GeoJSONPolygon,
)


class SlickDetectionBase(BaseSchema):
    """Common fields for slick detection."""

    polygon: GeoJSONPolygon
    centroid: GeoJSONPoint
    area_m2: float = Field(..., gt=0.0, description="Estimated slick surface area in square meters")
    confidence: ConfidenceValue  # Rule 1: Mandatory confidence
    lookalike_risk: float = Field(
        default=0.0, ge=0.0, le=1.0, description="Risk probability that detection is a false lookalike"
    )
    sensor: str = Field(..., description="Sensor platform e.g., 'Sentinel-1 SAR IW'")
    detection_time: datetime = Field(..., description="Acquisition timestamp in UTC")
    data_source: DataSourceEnum = DataSourceEnum.SYNTHETIC


class SlickDetectionCreate(SlickDetectionBase):
    """Payload for creating a new detection."""

    case_id: uuid.UUID


class SlickDetectionResponse(SlickDetectionBase):
    """API and inter-service response for slick detection."""

    id: uuid.UUID
    case_id: uuid.UUID
    created_at: datetime
