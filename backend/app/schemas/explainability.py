"""AEGIS-Marine: Explainability, Timeline, and Graph Schemas."""

from __future__ import annotations

import uuid
from datetime import datetime
from typing import Any, Dict, List, Optional
from pydantic import Field

from backend.app.schemas.common import BaseSchema, ConfidenceValue
from backend.app.schemas.vessel import SubScores


class AlternativeExplanationBase(BaseSchema):
    """Rule 5: Non-vessel alternative hypothesis."""

    hypothesis: str = Field(
        ...,
        description="'natural_seep' | 'imaging_artifact' | 'non_ais_vessel'",
    )
    score: float = Field(..., ge=0.0, le=100.0, description="Hypothesis plausibility score")
    confidence: ConfidenceValue  # Rule 1: Mandatory confidence
    evidence: Dict[str, Any] = Field(default_factory=dict)


class AlternativeExplanationCreate(AlternativeExplanationBase):
    """Payload to create alternative explanation."""

    case_id: uuid.UUID


class AlternativeExplanationResponse(AlternativeExplanationBase):
    """Response payload for alternative explanation."""

    id: uuid.UUID
    case_id: uuid.UUID
    created_at: datetime


class EvidenceTimelineItem(BaseSchema):
    """Chronological event reconstruction entry."""

    timestamp: datetime
    event_type: str = Field(
        ...,
        description="'satellite_pass' | 'spill_origin' | 'vessel_entry' | 'anomaly_detected' | 'cpa_reached'",
    )
    title: str
    description: str
    evidence_ref: Optional[str] = None


class GraphNode(BaseSchema):
    """Node in the evidence graph."""

    id: str
    label: str
    node_type: str = Field(
        ...,
        description="'scene' | 'slick' | 'origin' | 'ais_track' | 'vessel' | 'seep' | 'anomaly'",
    )
    properties: Dict[str, Any] = Field(default_factory=dict)


class GraphEdge(BaseSchema):
    """Directed edge in the evidence graph."""

    source: str
    target: str
    relation: str = Field(
        ...,
        description="'DETECTED' | 'DRIFTED_FROM' | 'TRAVERSED' | 'FLAGGED_BY' | 'EXPLAINS'",
    )
    properties: Dict[str, Any] = Field(default_factory=dict)


class EvidenceGraphPayload(BaseSchema):
    """Evidence graph response for interactive visualization."""

    nodes: List[GraphNode]
    edges: List[GraphEdge]


class WhyThisVesselPayload(BaseSchema):
    """Structured forensic rationale payload for suspect candidate (Feature 1)."""

    mmsi: int
    vessel_name: str
    s_culprit: float
    confidence: ConfidenceValue
    sub_scores: SubScores
    radar_data: List[Dict[str, Any]] = Field(
        ..., description="Polar coordinates for AHP 5-axis radar chart"
    )
    forensic_summary: str = Field(
        ..., description="Objective forensic rationale (strictly zero Rule 6 banned terms)"
    )
    counterfactual_similarity_pct: Optional[float] = None
