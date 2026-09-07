"""AEGIS-Marine: Shared Data Contracts & Pydantic Schemas."""

from backend.app.schemas.case import (
    CaseCreateRequest,
    CaseDetailResponse,
    WhatIfRequest,
)
from backend.app.schemas.characterization import (
    SlickCharacterizationBase,
    SlickCharacterizationCreate,
    SlickCharacterizationResponse,
)
from backend.app.schemas.common import (
    AISCoverageEnum,
    BaseSchema,
    CaseStatusEnum,
    ConfidenceValue,
    DataSourceEnum,
    GeoJSONPoint,
    GeoJSONPolygon,
)
from backend.app.schemas.detection import (
    SlickDetectionBase,
    SlickDetectionCreate,
    SlickDetectionResponse,
)
from backend.app.schemas.explainability import (
    AlternativeExplanationBase,
    AlternativeExplanationCreate,
    AlternativeExplanationResponse,
    EvidenceGraphPayload,
    EvidenceTimelineItem,
    GraphEdge,
    GraphNode,
    WhyThisVesselPayload,
)
from backend.app.schemas.hindcast import (
    ForwardForecastBase,
    ForwardForecastResponse,
    OriginEstimateBase,
    OriginEstimateCreate,
    OriginEstimateResponse,
    ParticleState,
)
from backend.app.schemas.vessel import (
    AHPConfigResponse,
    AISTrackPoint,
    SubScores,
    VesselCandidateBase,
    VesselCandidateCreate,
    VesselCandidateResponse,
)

__all__ = [
    "BaseSchema",
    "ConfidenceValue",
    "CaseStatusEnum",
    "DataSourceEnum",
    "AISCoverageEnum",
    "GeoJSONPoint",
    "GeoJSONPolygon",
    "SlickDetectionBase",
    "SlickDetectionCreate",
    "SlickDetectionResponse",
    "SlickCharacterizationBase",
    "SlickCharacterizationCreate",
    "SlickCharacterizationResponse",
    "OriginEstimateBase",
    "OriginEstimateCreate",
    "OriginEstimateResponse",
    "ForwardForecastBase",
    "ForwardForecastResponse",
    "ParticleState",
    "SubScores",
    "AISTrackPoint",
    "VesselCandidateBase",
    "VesselCandidateCreate",
    "VesselCandidateResponse",
    "AHPConfigResponse",
    "AlternativeExplanationBase",
    "AlternativeExplanationCreate",
    "AlternativeExplanationResponse",
    "EvidenceTimelineItem",
    "GraphNode",
    "GraphEdge",
    "EvidenceGraphPayload",
    "WhyThisVesselPayload",
    "CaseCreateRequest",
    "WhatIfRequest",
    "CaseDetailResponse",
]
