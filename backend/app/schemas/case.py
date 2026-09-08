"""AEGIS-Marine: Case Orchestration & What-If Schemas."""

from __future__ import annotations

import uuid
from datetime import datetime
from typing import Dict, List, Optional
from pydantic import Field

from backend.app.schemas.characterization import SlickCharacterizationResponse
from backend.app.schemas.common import (
    BaseSchema,
    CaseStatusEnum,
    GeoJSONPolygon,
)
from backend.app.schemas.detection import SlickDetectionResponse
from backend.app.schemas.explainability import AlternativeExplanationResponse
from backend.app.schemas.hindcast import (
    ForwardForecastResponse,
    OriginEstimateResponse,
)
from backend.app.schemas.vessel import VesselCandidateResponse


class CaseCreateRequest(BaseSchema):
    """Payload to trigger a new oil spill investigation."""

    region: GeoJSONPolygon
    source_scene_ref: Optional[str] = Field(
        default=None,
        description="Copernicus CDSE product reference or local file path",
    )
    created_by: str = Field(default="investigator", description="Investigator username/ID")


class WhatIfRequest(BaseSchema):
    """What-If scenario parameter override payload (Feature 3 / P3)."""

    scenario_name: Optional[str] = Field(
        default=None,
        description="Optional human-readable label for this what-if scenario run",
    )
    t_age_override_hours: Optional[float] = Field(
        default=None,
        ge=0.0,
        description="Manual override for slick elapsed spreading age",
    )
    wind_drift_factor: Optional[float] = Field(
        default=None,
        ge=0.01,
        le=0.06,
        description="Override wind-drift factor c_w (nominal 0.030)",
    )
    horizontal_diffusivity: Optional[float] = Field(
        default=None,
        ge=0.0,
        le=50.0,
        description="Override horizontal eddy diffusivity Kh in m^2/s (nominal 2.0)",
    )
    origin_search_sigma: Optional[float] = Field(
        default=None,
        ge=1.0,
        le=5.0,
        description="Spatial origin search buffer in standard deviations (e.g. 2.0 or 3.0)",
    )
    custom_ahp_weights: Optional[Dict[str, float]] = Field(
        default=None,
        description="Custom AHP weights for {spatial, temporal, kinematic, anomaly, type}",
    )
    persist_scenario: bool = Field(
        default=True,
        description="Whether to cache this scenario under child scenario keys",
    )


class CaseDetailResponse(BaseSchema):
    """Root aggregate response for complete case status and tier outputs."""

    id: uuid.UUID
    status: CaseStatusEnum
    region: GeoJSONPolygon
    source_scene_ref: Optional[str] = None
    created_by: str
    created_at: datetime

    detections: List[SlickDetectionResponse] = Field(default_factory=list)
    characterizations: List[SlickCharacterizationResponse] = Field(default_factory=list)
    origin_estimates: List[OriginEstimateResponse] = Field(default_factory=list)
    forward_forecasts: List[ForwardForecastResponse] = Field(default_factory=list)
    vessel_candidates: List[VesselCandidateResponse] = Field(default_factory=list)
    alternative_explanations: List[AlternativeExplanationResponse] = Field(default_factory=list)
