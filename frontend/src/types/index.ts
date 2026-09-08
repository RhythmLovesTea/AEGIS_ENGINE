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
export type AlternativeExplanation = Schemas["AlternativeExplanationResponse"];

// -----------------------------------------------------------------------------
// Evidence, Graph & Explainability Models (D1, FR-21)
// -----------------------------------------------------------------------------
export type WhyThisVessel = Schemas["WhyThisVesselPayload"];
export type Counterfactual = Schemas["CounterfactualResult"];
export type EvidenceGraph = Schemas["EvidenceGraphPayload"];
export type EvidenceTimeline = Schemas["EvidenceTimelinePayload"];
export type ReplayState = Schemas["ReplayStatePayload"];

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
