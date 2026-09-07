"""AEGIS-Marine: Shared Geospatial, Enums, and Common Types."""

from __future__ import annotations

import enum
from typing import Annotated, Any, List, Literal, Tuple
from pydantic import BaseModel, ConfigDict, Field


class CaseStatusEnum(str, enum.Enum):
    DETECTING = "detecting"
    CHARACTERIZING = "characterizing"
    HINDCASTING = "hindcasting"
    CORRELATING = "correlating"
    SCORING = "scoring"
    READY = "ready"
    FAILED = "failed"


class DataSourceEnum(str, enum.Enum):
    LIVE = "live"
    CACHED = "cached"
    SYNTHETIC = "synthetic"


class AISCoverageEnum(str, enum.Enum):
    FULL = "full"
    PARTIAL = "partial"
    DARK_GAP = "dark_gap"
    NON_AIS_UNKNOWN = "non_ais_unknown"


# Rule 1: Confidence value bounded between 0.0 and 100.0
ConfidenceValue = Annotated[
    float,
    Field(
        ge=0.0,
        le=100.0,
        description="Confidence percentage [0.0 - 100.0] associated with this estimate or score.",
    ),
]


class GeoJSONPoint(BaseModel):
    """GeoJSON Point geometry (EPSG:4326: [lon, lat])."""

    model_config = ConfigDict(frozen=True)

    type: Literal["Point"] = "Point"
    coordinates: Tuple[float, float] = Field(
        ...,
        description="Longitude and latitude coordinates [lon, lat]",
    )


class GeoJSONPolygon(BaseModel):
    """GeoJSON Polygon geometry (EPSG:4326)."""

    model_config = ConfigDict(frozen=True)

    type: Literal["Polygon"] = "Polygon"
    coordinates: List[List[Tuple[float, float]]] = Field(
        ...,
        description="Array of linear ring coordinate arrays [[ [lon, lat], ... ]]",
    )


class BaseSchema(BaseModel):
    """Base Pydantic configuration for all domain contracts."""

    model_config = ConfigDict(
        from_attributes=True,
        populate_by_name=True,
        use_enum_values=True,
    )
