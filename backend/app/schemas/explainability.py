"""AEGIS-Marine: Explainability, Timeline, and Graph Schemas."""

from __future__ import annotations

import uuid
from datetime import datetime
from typing import Any

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
    evidence: dict[str, Any] = Field(default_factory=dict)


class AlternativeExplanationCreate(AlternativeExplanationBase):
    """Payload to create alternative explanation."""

    case_id: uuid.UUID


class AlternativeExplanationResponse(AlternativeExplanationBase):
    """Response payload for alternative explanation."""

    id: uuid.UUID
    case_id: uuid.UUID
    created_at: datetime


class EvidenceTimelineItem(BaseSchema):
    """Rule 1: Chronological event reconstruction entry with paired confidence."""

    timestamp: datetime
    event_type: str = Field(
        ...,
        description=(
            "'satellite_pass' | 'release_window' | 'vessel_entry' | "
            "'anomaly_detected' | 'cpa_reached' | 'drift_progression' | 'slick_observed'"
        ),
    )
    title: str
    description: str
    evidence_ref: str | None = None
    confidence_pct: ConfidenceValue = Field(
        default=85.0, description="Rule 1: Paired confidence score in [0.0, 100.0]"
    )
    properties: dict[str, Any] = Field(default_factory=dict)


class EvidenceTimelinePayload(BaseSchema):
    """Chronological event reconstruction timeline payload."""

    case_id: uuid.UUID
    mmsi: int | None = Field(default=None, description="Candidate vessel MMSI filter, if any")
    events: list[EvidenceTimelineItem] = Field(default_factory=list)
    start_time: datetime | None = None
    end_time: datetime | None = None
    total_duration_hours: float = Field(default=0.0, ge=0.0)
    confidence_pct: ConfidenceValue = Field(
        default=85.0, description="Rule 1: Paired confidence score in [0.0, 100.0]"
    )


class GraphNode(BaseSchema):
    """Rule 1: Node in the interactive evidence graph."""

    id: str
    label: str
    node_type: str = Field(
        ...,
        description=(
            "'scene' | 'slick' | 'origin' | 'time_window' | 'ais_track' | "
            "'vessel' | 'anomaly' | 'alternative_hypothesis' | 'counterfactual'"
        ),
    )
    confidence_pct: ConfidenceValue = Field(
        default=85.0, description="Rule 1: Paired confidence score in [0.0, 100.0]"
    )
    properties: dict[str, Any] = Field(default_factory=dict)


class GraphEdge(BaseSchema):
    """Rule 1: Directed causal edge in the evidence graph."""

    source: str
    target: str
    relation: str = Field(
        ...,
        description=(
            "'OBSERVED' | 'DRIFTED_FROM' | 'ESTIMATED_WINDOW' | 'TRAVERSED' | "
            "'BROADCAST_BY' | 'CORRELATED_WITH' | 'EXHIBITED' | 'COINCIDED_WITH' | "
            "'EVALUATED_AGAINST' | 'SIMULATED_FORWARD' | 'CONGRUENT_WITH'"
        ),
    )
    confidence_pct: ConfidenceValue = Field(
        default=85.0, description="Rule 1: Paired confidence score in [0.0, 100.0]"
    )
    properties: dict[str, Any] = Field(default_factory=dict)


class EvidenceGraphPayload(BaseSchema):
    """Interactive node-edge evidence graph payload."""

    case_id: uuid.UUID
    mmsi: int | None = Field(default=None, description="Candidate vessel MMSI filter, if any")
    nodes: list[GraphNode] = Field(default_factory=list)
    edges: list[GraphEdge] = Field(default_factory=list)
    is_acyclic: bool = Field(default=True, description="Whether graph is a valid DAG")
    topological_order: list[str] = Field(default_factory=list)
    confidence_pct: ConfidenceValue = Field(
        default=85.0, description="Rule 1: Paired confidence score in [0.0, 100.0]"
    )
    metadata: dict[str, Any] = Field(default_factory=dict)


class EvidenceBundlePayload(BaseSchema):
    """Comprehensive forensic evidence package combining timeline and graph."""

    case_id: uuid.UUID
    mmsi: int | None = None
    timeline: EvidenceTimelinePayload
    graph: EvidenceGraphPayload
    confidence_pct: ConfidenceValue = Field(
        default=85.0, description="Rule 1: Paired confidence score in [0.0, 100.0]"
    )


class SpatialBreakdown(BaseSchema):
    """Forensic breakdown of spatial proximity to estimated spill origin."""

    sub_score: float = Field(
        ..., ge=0.0, le=100.0, description="Spatial proximity sub-score [0 - 100]"
    )
    mahalanobis_distance: float = Field(
        ..., ge=0.0, description="Mahalanobis distance D_M from origin centroid"
    )
    physical_distance_km: float = Field(
        ..., ge=0.0, description="Great-circle physical distance in km"
    )
    sigma_band: str = Field(..., description="'1sigma' | '2sigma' | '3sigma' | 'outside_3sigma'")
    inside_1sigma: bool = Field(
        ..., description="Whether CPA falls within 1-sigma uncertainty ellipse (D_M <= 1.0)"
    )
    inside_2sigma: bool = Field(
        ..., description="Whether CPA falls within 2-sigma uncertainty ellipse (D_M <= 2.0)"
    )
    inside_3sigma: bool = Field(
        ..., description="Whether CPA falls within 3-sigma uncertainty ellipse (D_M <= 3.0)"
    )
    cpa_coordinates: tuple[float, float] | None = Field(
        default=None, description="Coordinates (lon, lat) at CPA"
    )
    origin_centroid: tuple[float, float] | None = Field(
        default=None, description="Coordinates (lon, lat) of origin centroid"
    )
    rationale: str = Field(..., description="Objective forensic spatial rationale")


class TemporalBreakdown(BaseSchema):
    """Forensic breakdown of temporal coincidence with estimated release window."""

    sub_score: float = Field(
        ..., ge=0.0, le=100.0, description="Temporal coincidence sub-score [0 - 100]"
    )
    delta_minutes: float = Field(
        ..., ge=0.0, description="Time delta |t_CPA - t_release| in minutes"
    )
    delta_hours: float = Field(..., ge=0.0, description="Time delta |t_CPA - t_release| in hours")
    decay_factor: float = Field(
        ..., ge=0.0, le=1.0, description="Temporal exponential decay factor exp(-dt / tau)"
    )
    tau_hours: float = Field(default=1.5, description="Time constant tau in hours")
    t_cpa: datetime | None = Field(default=None, description="Timestamp of vessel closest approach")
    t_release: datetime | None = Field(
        default=None, description="Estimated spill release timestamp"
    )
    rationale: str = Field(..., description="Objective forensic temporal rationale")


class KinematicBreakdown(BaseSchema):
    """Forensic breakdown of vessel kinematics and slick alignment."""

    sub_score: float = Field(
        ..., ge=0.0, le=100.0, description="Kinematic alignment sub-score [0 - 100]"
    )
    vessel_cog_deg: float | None = Field(
        default=None, description="Vessel Course Over Ground in degrees at CPA"
    )
    slick_orientation_deg: float | None = Field(
        default=None, description="Observed slick principal axis orientation in degrees"
    )
    heading_difference_deg: float = Field(
        ..., ge=0.0, le=180.0, description="Angular difference |vessel_heading - slick_axis|"
    )
    vessel_speed_kts: float | None = Field(
        default=None, description="Vessel speed over ground in knots at CPA"
    )
    speed_modulation_factor: float = Field(
        ..., ge=0.0, le=1.0, description="Speed wake modulation factor f(v)"
    )
    rationale: str = Field(..., description="Objective forensic kinematic rationale")


class AnomalyBreakdown(BaseSchema):
    """Forensic breakdown of behavioral anomalies and transponder gaps."""

    sub_score: float = Field(
        ..., ge=0.0, le=100.0, description="Behavioral anomaly sub-score [0 - 100]"
    )
    anomaly_flags: list[str] = Field(
        default_factory=list, description="List of detected anomaly flag identifiers"
    )
    speed_anomaly_score: float = Field(
        ..., ge=0.0, le=1.0, description="Speed loitering / dumping score A_speed"
    )
    course_anomaly_score: float = Field(
        ..., ge=0.0, le=1.0, description="Course alteration score A_course"
    )
    dark_gap_score: float = Field(..., ge=0.0, le=1.0, description="Transponder gap score A_dark")
    speed_loitering_detected: bool = Field(
        default=False, description="True if vessel slowed into dumping window [4, 8] kts"
    )
    speed_at_cpa_kts: float | None = Field(default=None, description="Speed at CPA in knots")
    dark_gap_detected: bool = Field(
        default=False, description="True if transponder silence > 30 min was detected"
    )
    dark_gap_intervals: list[dict[str, Any]] = Field(
        default_factory=list, description="Transponder gap intervals with duration and coordinates"
    )
    rationale: str = Field(..., description="Objective forensic anomaly rationale")


class TypeBreakdown(BaseSchema):
    """Forensic breakdown of vessel category prior risk and registry status."""

    sub_score: float = Field(
        ..., ge=0.0, le=100.0, description="Vessel type risk prior sub-score [0 - 100]"
    )
    vessel_type: str = Field(..., description="Vessel type string category")
    prior_risk_score: float = Field(
        ..., ge=0.0, le=100.0, description="Prior discharge risk score based on IMO typology"
    )
    imo: int | None = Field(default=None, description="IMO registry number if registered")
    flag_state: str | None = Field(default=None, description="Vessel flag state registry")
    registry_reference: str = Field(
        ..., description="Official registry reference or contact classification"
    )
    rationale: str = Field(..., description="Objective forensic vessel type rationale")


class RadarChartDataPoint(BaseSchema):
    """Polar coordinate entry for frontend 5-axis AHP radar chart."""

    axis: str = Field(..., description="Axis label e.g., 'Spatial Proximity'")
    key: str = Field(..., description="Sub-score identifier e.g., 'spatial'")
    value: float = Field(..., ge=0.0, le=100.0, description="Candidate vessel score [0 - 100]")
    weight: float = Field(..., ge=0.0, le=1.0, description="AHP canonical weight")
    weighted_score: float = Field(..., ge=0.0, le=100.0, description="Value * Weight contribution")
    fleet_benchmark: float = Field(
        default=20.0, ge=0.0, le=100.0, description="Regional baseline / innocent vessel comparison"
    )


class BarChartItem(BaseSchema):
    """Weighted contribution bar chart item."""

    category: str = Field(..., description="Criteria category name")
    key: str = Field(..., description="Criteria key e.g., 'spatial'")
    raw_score: float = Field(
        ..., ge=0.0, le=100.0, description="Unweighted raw sub-score [0 - 100]"
    )
    weight: float = Field(..., ge=0.0, le=1.0, description="AHP weight factor")
    weighted_contribution: float = Field(
        ..., ge=0.0, le=100.0, description="Contribution to S_culprit"
    )
    max_contribution: float = Field(
        ..., ge=0.0, le=100.0, description="Maximum possible contribution (weight * 100)"
    )


class EvidenceChecklistItem(BaseSchema):
    """Structured checklist item for forensic evidence verification."""

    check: str = Field(..., description="Check item title e.g., 'Spatial Ellipse Containment'")
    status: str = Field(..., description="'positive_indicator' | 'neutral' | 'unlikely'")
    finding: str = Field(..., description="Factual description of finding")
    confidence_pct: ConfidenceValue  # Rule 1: Paired confidence


class WhyThisVesselPayload(BaseSchema):
    """Structured forensic rationale payload for suspect candidate (Feature 1)."""

    mmsi: int
    vessel_name: str
    s_culprit: float
    confidence: ConfidenceValue
    sub_scores: SubScores
    radar_data: list[dict[str, Any]] = Field(
        ..., description="Polar coordinates for AHP 5-axis radar chart"
    )
    forensic_summary: str = Field(
        ..., description="Objective forensic rationale (strictly zero Rule 6 banned terms)"
    )
    counterfactual_similarity_pct: float | None = None

    # Enhanced breakdown fields (Feature 1 / Architecture 4.5)
    rank: int | None = None
    imo: int | None = None
    vessel_type: str | None = None
    flag_state: str | None = None
    ais_coverage: str | None = None
    spatial_breakdown: SpatialBreakdown | None = None
    temporal_breakdown: TemporalBreakdown | None = None
    kinematic_breakdown: KinematicBreakdown | None = None
    anomaly_breakdown: AnomalyBreakdown | None = None
    type_breakdown: TypeBreakdown | None = None
    bar_data: list[BarChartItem] = Field(default_factory=list)
    evidence_checklist: list[EvidenceChecklistItem] = Field(default_factory=list)
    evidence_refs: list[str] = Field(default_factory=list)


class CounterfactualResult(BaseSchema):
    """Counterfactual forward Lagrangian simulation result (Feature 2 / D2)."""

    case_id: uuid.UUID
    mmsi: int
    vessel_name: str
    iou_pct: float = Field(
        ..., ge=0.0, le=100.0, description="Intersection-over-Union similarity percentage [0 - 100]"
    )
    similarity_score: float = Field(
        ..., ge=0.0, le=100.0, description="Composite geometric similarity score [0 - 100]"
    )
    hausdorff_distance_m: float = Field(
        ..., ge=0.0, description="Maximum Hausdorff boundary discrepancy in meters"
    )
    centroid_distance_m: float = Field(
        ...,
        ge=0.0,
        description="Distance between simulated cloud centroid and observed slick centroid",
    )
    t_release: datetime = Field(..., description="Release timestamp at seed position")
    t_obs: datetime = Field(..., description="Observation timestamp of satellite pass")
    duration_hours: float = Field(..., ge=0.0, description="Simulation drift duration in hours")
    seed_position: tuple[float, float] = Field(
        ..., description="Seed coordinates (lon, lat) at vessel position at t_release"
    )
    simulated_centroid: tuple[float, float] = Field(
        ..., description="Centroid (lon, lat) of simulated particle cloud at t_obs"
    )
    observed_centroid: tuple[float, float] = Field(
        ..., description="Centroid (lon, lat) of observed slick polygon at t_obs"
    )
    simulated_polygon_geojson: dict[str, Any] = Field(
        ..., description="GeoJSON polygon geometry of simulated cloud at t_obs"
    )
    snapshots: list[dict[str, Any]] = Field(
        default_factory=list,
        description="Subsampled particle trajectory snapshots along simulation",
    )
    confidence_pct: ConfidenceValue  # Rule 1: Paired confidence
    rationale: str = Field(
        ...,
        description="Objective forensic counterfactual rationale (strictly zero Rule 6 banned terms)",
    )


class ParticleReplayPoint(BaseSchema):
    """Lagrangian advection particle at a requested replay timestamp."""

    particle_id: int
    lon: float
    lat: float
    depth_m: float = 0.0
    status: str = Field(default="active", description="'active' | 'beached' | 'evaporated'")


class ParticleEnsembleState(BaseSchema):
    """Ensemble summary and coordinates for deck.gl map rendering."""

    timestamp: datetime
    mean_lon: float
    mean_lat: float
    n_particles: int
    subsample_coords: list[list[float]] = Field(
        default_factory=list,
        description="Subsampled [lon, lat] coordinates for high-performance cartography",
    )
    dispersion_radius_m: float = Field(
        default=0.0,
        ge=0.0,
        description="Estimated standard deviation particle dispersion radius in meters",
    )


class VesselReplayState(BaseSchema):
    """Rule 1: Vessel position, kinematics, and dynamic attribution at replay timestamp."""

    mmsi: int
    name: str
    vessel_type: str
    flag_state: str | None = None
    lon: float
    lat: float
    sog_kts: float = Field(..., ge=0.0, description="Interpolated speed over ground in knots")
    cog_deg: float = Field(
        ..., ge=0.0, le=360.0, description="Interpolated course over ground in degrees"
    )
    distance_to_cloud_m: float = Field(
        ..., ge=0.0, description="Euclidean distance to particle ensemble center"
    )
    current_s_culprit: float = Field(
        ..., ge=0.0, le=100.0, description="Dynamic attribution score at time t"
    )
    rank: int = Field(..., ge=1, description="Live ranking among candidates at time t")
    confidence_pct: ConfidenceValue  # Rule 1: Paired confidence
    in_surveillance_zone: bool = True


class ReplayStatePayload(BaseSchema):
    """Investigation Replay state at a discrete or interpolated timestamp (Feature 4 / D4)."""

    case_id: uuid.UUID
    timestamp: datetime = Field(..., description="Query timestamp t in UTC")
    particles: ParticleEnsembleState
    vessels: list[VesselReplayState] = Field(default_factory=list)
    observed_slick_centroid: tuple[float, float] | None = None
    estimated_origin_centroid: tuple[float, float] | None = None
    time_progress_pct: float = Field(
        default=0.0,
        ge=0.0,
        le=100.0,
        description="Normalized timeline progress percentage [0 - 100]",
    )
    confidence_pct: ConfidenceValue  # Rule 1: Paired confidence
    metadata: dict[str, Any] = Field(default_factory=dict)
