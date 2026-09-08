"""AEGIS-Marine: Pydantic Data Contracts for What-If Scenarios (Feature 3 / P3).

Conforms to:
- PRD Section 11 (Core Modules C1–C13) & Architecture Sections 7 & 8.
- Constitutional Rules 1, 4, 6, and 7.
"""

from __future__ import annotations

import uuid
from datetime import UTC, datetime
from typing import Any

from pydantic import Field

from backend.app.schemas.case import WhatIfRequest
from backend.app.schemas.common import BaseSchema, ConfidenceValue
from backend.app.schemas.explainability import AlternativeExplanationResponse
from backend.app.schemas.hindcast import OriginEstimateResponse
from backend.app.schemas.vessel import VesselCandidateResponse


class ScenarioParameterDelta(BaseSchema):
    """Detailed parameter divergence between baseline case and what-if scenario."""

    parameter: str = Field(
        ..., description="Parameter identifier (e.g. t_age_hours, wind_drift_factor)"
    )
    baseline_value: Any = Field(..., description="Baseline value from initial pipeline run")
    what_if_value: Any = Field(..., description="Overridden value applied in this scenario")
    unit: str = Field(default="", description="Engineering unit (e.g. hours, m/s, ratio)")
    delta: float | None = Field(
        default=None, description="Numeric difference (what_if - baseline) if applicable"
    )


class CandidateRankShift(BaseSchema):
    """Tracks position and score movements for a candidate vessel under what-if parameters."""

    mmsi: int = Field(..., description="Maritime Mobile Service Identity")
    vessel_name: str = Field(..., description="Vessel name")
    baseline_rank: int | None = Field(
        default=None, description="Candidate rank in baseline case (1-indexed)"
    )
    what_if_rank: int = Field(
        ..., description="Candidate rank in this what-if scenario (1-indexed)"
    )
    rank_delta: int = Field(
        default=0,
        description="Rank movement: positive = moved up in rank, negative = moved down, 0 = unchanged",
    )
    baseline_score: float | None = Field(
        default=None, description="Baseline S_culprit composite score [0-100]"
    )
    what_if_score: float = Field(
        ..., ge=0.0, le=100.0, description="What-if S_culprit composite score [0-100]"
    )
    score_delta: float = Field(
        default=0.0, description="Score change: what_if_score - baseline_score"
    )
    baseline_confidence: float | None = Field(
        default=None, description="Baseline attribution confidence score"
    )
    what_if_confidence: ConfidenceValue = Field(
        ..., description="Rule 1: Paired confidence score in [0.0, 100.0]"
    )
    ais_coverage: str = Field(
        default="full", description="Rule 4: AIS coverage flag ('full', 'partial', 'dark_gap')"
    )


class BaselineComparisonSummary(BaseSchema):
    """Quantitative forensic comparison between baseline investigation and what-if scenario."""

    origin_displacement_km: float = Field(
        ...,
        ge=0.0,
        description="Great-circle distance in kilometers between baseline origin centroid and scenario origin centroid",
    )
    release_time_shift_hours: float = Field(
        ...,
        description="Temporal difference in hours between scenario release time and baseline release time",
    )
    ellipse_area_ratio: float = Field(
        default=1.0,
        ge=0.0,
        description="Ratio of scenario 1-sigma uncertainty ellipse area to baseline 1-sigma area",
    )
    top_candidate_changed: bool = Field(
        default=False,
        description="Whether the highest-ranked suspect vessel changed under the what-if parameters",
    )
    rank_shifts: list[CandidateRankShift] = Field(
        default_factory=list,
        description="Detailed rank and score movement for each evaluated candidate vessel",
    )
    parameter_deltas: list[ScenarioParameterDelta] = Field(
        default_factory=list,
        description="Audit table of all parameters that diverged from the baseline case",
    )
    confidence_pct: ConfidenceValue = Field(
        default=85.0,
        description="Rule 1: Paired confidence assessment for the comparison analysis",
    )


class WhatIfScenarioResponse(BaseSchema):
    """Complete response payload for an executed What-If scenario."""

    scenario_id: uuid.UUID = Field(..., description="Unique scenario identifier")
    case_id: uuid.UUID = Field(..., description="Target parent case UUID")
    scenario_name: str = Field(..., description="Human-readable scenario label")
    created_at: datetime = Field(default_factory=lambda: datetime.now(UTC))
    created_by: str = Field(
        default="analyst", description="User identity that executed the scenario"
    )
    applied_parameters: WhatIfRequest = Field(
        ..., description="The parameter overrides applied in this scenario"
    )
    origin_estimate: OriginEstimateResponse = Field(
        ..., description="Re-computed Tier 3 origin estimate"
    )
    ranked_vessels: list[VesselCandidateResponse] = Field(
        default_factory=list,
        description="Re-computed and ranked Tier 4 candidate vessels with discrete sub-scores",
    )
    alternative_explanations: list[AlternativeExplanationResponse] = Field(
        default_factory=list,
        description="Re-evaluated alternative hypotheses under scenario origin and weights",
    )
    comparison: BaselineComparisonSummary = Field(
        ...,
        description="Forensic delta comparing scenario outcomes against baseline case",
    )


class WhatIfScenarioSummary(BaseSchema):
    """Lightweight scenario metadata for scenario list views."""

    scenario_id: uuid.UUID
    case_id: uuid.UUID
    scenario_name: str
    created_at: datetime
    created_by: str
    applied_parameters: WhatIfRequest
    top_candidate_name: str | None = None
    top_candidate_score: float | None = None
    origin_displacement_km: float = 0.0
    confidence_pct: ConfidenceValue = 85.0
