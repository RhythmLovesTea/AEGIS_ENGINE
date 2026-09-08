/**
 * AEGIS-Marine: Consolidated API Contract & Domain Types (TASK-040)
 * Re-exports auto-generated OpenAPI contracts and provides ergonomic domain aliases.
 */

import type { components, operations, paths } from "./api";

export type { components, operations, paths };

// Convenience namespace for raw OpenAPI schemas
export type Schemas = components["schemas"];

// -----------------------------------------------------------------------------
// Core Case Domain Models
// -----------------------------------------------------------------------------
export type CaseDetail = Schemas["CaseDetailResponse"];
export type CaseCreateRequest = Schemas["CaseCreateRequest"];
export type CaseUpdateRequest = Partial<CaseCreateRequest>;
export type CaseStatus = Schemas["CaseStatusEnum"];

export interface CaseStatusResponse {
  case_id: string;
  status: CaseStatus | string;
  progress_pct: number;
  stage?: string;
  message?: string;
  timestamp: string;
}

export type SlickDetection = Schemas["SlickDetectionResponse"];
export type SlickCharacterization = Schemas["SlickCharacterizationResponse"];
export type OriginEstimate = Schemas["OriginEstimateResponse"];
export type ForwardForecast = Schemas["ForwardForecastResponse"];
export type VesselCandidate = Schemas["VesselCandidateResponse"];
export type SubScores = Schemas["SubScores"];
export type AISCoverage = Schemas["AISCoverageEnum"];
export type AlternativeExplanation = Schemas["AlternativeExplanationResponse"];

export interface NaturalSeepEvidence {
  nearest_seep_id?: string;
  nearest_seep_name?: string;
  basin?: string;
  distance_km?: number;
  bearing_deg?: number;
  water_depth_m?: number;
  seep_type?: string;
  activity_status?: string;
  target_coordinates?: [number, number];
  rationale?: string;
}

export interface ImagingArtifactEvidence {
  lookalike_risk?: number;
  incidence_angle_deg?: number;
  wind_speed_ms?: number;
  sensor?: string;
  angle_factor?: number;
  wind_factor?: number;
  rationale?: string;
}

export interface NonAISVesselEvidence {
  candidate_count?: number;
  dark_gap_count?: number;
  unidentified_radar_contacts?: number;
  regional_ais_coverage?: string;
  rationale?: string;
}

// -----------------------------------------------------------------------------
// Evidence, Graph & Explainability Models (D1, FR-21)
// -----------------------------------------------------------------------------
export type WhyThisVessel = Schemas["WhyThisVesselPayload"];
export type WhyThisVesselPayload = Schemas["WhyThisVesselPayload"];
export type SpatialBreakdown = Schemas["SpatialBreakdown"];
export type TemporalBreakdown = Schemas["TemporalBreakdown"];
export type KinematicBreakdown = Schemas["KinematicBreakdown"];
export type AnomalyBreakdown = Schemas["AnomalyBreakdown"];
export type TypeBreakdown = Schemas["TypeBreakdown"];
export type BarChartItem = Schemas["BarChartItem"];
export type EvidenceChecklistItem = Schemas["EvidenceChecklistItem"];

export interface RadarChartDataPoint {
  axis: string;
  key: string;
  value: number;
  weight: number;
  weighted_score: number;
  fleet_benchmark: number;
}

export type Counterfactual = Schemas["CounterfactualResult"];
export type CounterfactualResult = Schemas["CounterfactualResult"];
export type EvidenceGraph = Schemas["EvidenceGraphPayload"];
export type EvidenceGraphPayload = Schemas["EvidenceGraphPayload"];
export type GraphNode = Schemas["GraphNode"];
export type GraphEdge = Schemas["GraphEdge"];
export type EvidenceBundlePayload = Schemas["EvidenceBundlePayload"];
export type EvidenceBundle = Schemas["EvidenceBundlePayload"];
export type EvidenceTimelinePayload = Schemas["EvidenceTimelinePayload"];
export type EvidenceTimelineItem = Schemas["EvidenceTimelineItem"];
export type ReplayState = Schemas["ReplayStatePayload"];
export type ReplayStatePayload = Schemas["ReplayStatePayload"];
export type VesselReplayState = Schemas["VesselReplayState"];
export type ParticleEnsembleState = Schemas["ParticleEnsembleState"];

// -----------------------------------------------------------------------------
// "What-If" Simulation & Parameter Overrides (FR-19, TASK-037)
// -----------------------------------------------------------------------------
export type WhatIfRequest = Schemas["WhatIfRequest"];
export type WhatIfScenarioResponse = Schemas["WhatIfScenarioResponse"];
export type WhatIfScenarioSummary = Schemas["WhatIfScenarioSummary"];
export type ScenarioParameterDelta = Schemas["ScenarioParameterDelta"];
export type CandidateRankShift = Schemas["CandidateRankShift"];
export type BaselineComparisonSummary = Schemas["BaselineComparisonSummary"];

// -----------------------------------------------------------------------------
// Legal Dossier & Chain of Custody (FR-20, C13)
// -----------------------------------------------------------------------------
export type DossierResult = Schemas["DossierResult"];
export type DossierGenerateRequest = Schemas["DossierGenerateRequest"];

// -----------------------------------------------------------------------------
// Multi-Criteria AHP Weight Configuration (FR-12, Rule 7)
// -----------------------------------------------------------------------------
export type AHPConfigResponse = Schemas["AHPConfigResponse"];
export interface AHPWeightUpdatePayload {
  weights: Record<string, number>;
  reason?: string;
}

// -----------------------------------------------------------------------------
// Audit Logging System (Section 5, TASK-038)
// -----------------------------------------------------------------------------
export type AuditLog = Schemas["AuditLogResponse"];
export type AuditLogListResponse = Schemas["AuditLogListResponse"];

// -----------------------------------------------------------------------------
// Identity, User Profile & RBAC (Architecture 10)
// -----------------------------------------------------------------------------
export interface TokenResponse {
  access_token: string;
  token_type?: string;
  expires_in?: number;
  refresh_token?: string;
}

export interface UserProfileResponse {
  user_id: string;
  email: string;
  name: string;
  roles: string[];
  permissions: string[];
}

export type Role = "investigator" | "analyst" | "legal_reviewer" | "admin";

// -----------------------------------------------------------------------------
// Real-time WebSocket Protocol Types (/cases/{id}/status)
// -----------------------------------------------------------------------------
export interface CaseStatusMessage {
  case_id: string;
  status: string;
  progress_pct: number;
  stage?: string;
  message?: string;
  timestamp: string;
  error?: string;
}

export interface WebSocketHeartbeat {
  type: "pong";
  timestamp: string;
}

export type ConnectionState =
  | "idle"
  | "connecting"
  | "connected"
  | "reconnecting"
  | "disconnected"
  | "error";
