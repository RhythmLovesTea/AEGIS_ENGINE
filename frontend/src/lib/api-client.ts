/**
 * AEGIS-Marine: Typed REST API Client (TASK-040)
 * Uses native fetch with automatic JWT Bearer token injection, RFC 7807 problem details parsing,
 * and end-to-end type safety derived from generated OpenAPI contracts.
 */

import type {
  AHPConfigResponse,
  AHPWeightUpdatePayload,
  AuditLogListResponse,
  CaseCreateRequest,
  CaseDetail,
  CaseStatusResponse,
  CaseUpdateRequest,
  DossierGenerateRequest,
  DossierResult,
  TokenResponse,
  UserProfileResponse,
  WhatIfRequest,
  WhatIfScenarioResponse,
  WhatIfScenarioSummary,
  ReplayStatePayload,
} from "@/types";

export class ApiClientError extends Error {
  public readonly status: number;
  public readonly code?: string;
  public readonly details?: unknown;

  constructor(
    message: string,
    status: number,
    code?: string,
    details?: unknown
  ) {
    super(message);
    this.name = "ApiClientError";
    this.status = status;
    this.code = code;
    this.details = details;
  }
}

export interface RequestOptions extends RequestInit {
  params?: Record<string, string | number | boolean | undefined | null>;
  skipAuth?: boolean;
}

export class ApiClient {
  private baseUrl: string;
  private token: string | null = null;

  constructor(baseUrl?: string) {
    this.baseUrl =
      baseUrl ||
      (typeof process !== "undefined" && process.env.NEXT_PUBLIC_API_URL
        ? process.env.NEXT_PUBLIC_API_URL.replace(/\/$/, "")
        : "http://localhost:8000/api/v1");

    if (typeof window !== "undefined") {
      this.token = window.localStorage.getItem("aegis_access_token");
    }
  }

  public setToken(token: string | null): void {
    this.token = token;
    if (typeof window !== "undefined") {
      if (token) {
        window.localStorage.setItem("aegis_access_token", token);
      } else {
        window.localStorage.removeItem("aegis_access_token");
      }
    }
  }

  public getToken(): string | null {
    return this.token;
  }

  public clearToken(): void {
    this.setToken(null);
  }

  private buildUrl(
    endpoint: string,
    params?: Record<string, string | number | boolean | undefined | null>
  ): string {
    const cleanEndpoint = endpoint.startsWith("/") ? endpoint : `/${endpoint}`;
    const url = new URL(`${this.baseUrl}${cleanEndpoint}`);

    if (params) {
      Object.entries(params).forEach(([key, value]) => {
        if (value !== undefined && value !== null) {
          url.searchParams.append(key, String(value));
        }
      });
    }

    return url.toString();
  }

  public async request<T>(
    endpoint: string,
    options: RequestOptions = {}
  ): Promise<T> {
    const { params, skipAuth, headers = {}, ...customConfig } = options;
    const url = this.buildUrl(endpoint, params);

    const requestHeaders: Record<string, string> = {
      Accept: "application/json",
      ...((headers as Record<string, string>) || {}),
    };

    if (!(customConfig.body instanceof FormData) && !requestHeaders["Content-Type"]) {
      requestHeaders["Content-Type"] = "application/json";
    }

    if (!skipAuth && this.token) {
      requestHeaders["Authorization"] = `Bearer ${this.token}`;
    }

    const response = await fetch(url, {
      ...customConfig,
      headers: requestHeaders,
    });

    if (!response.ok) {
      let errorMessage = `HTTP Error ${response.status}: ${response.statusText}`;
      let errorCode: string | undefined;
      let errorDetails: unknown;

      try {
        const errorJson = await response.json();
        // Parse RFC 7807 Problem Details or FastAPI error response
        if (typeof errorJson === "object" && errorJson !== null) {
          errorMessage =
            errorJson.detail ||
            errorJson.title ||
            errorJson.message ||
            errorMessage;
          errorCode = errorJson.code || errorJson.error_code;
          errorDetails = errorJson.invalid_params || errorJson;
        }
      } catch {
        // Response was not JSON, fallback to statusText
      }

      throw new ApiClientError(errorMessage, response.status, errorCode, errorDetails);
    }

    // Return empty object for 204 No Content
    if (response.status === 204) {
      return {} as T;
    }

    return (await response.json()) as T;
  }

  // ---------------------------------------------------------------------------
  // Case Endpoints (Architecture 10 & PRD FR-17)
  // ---------------------------------------------------------------------------

  public async listCases(params?: {
    status?: string;
    limit?: number;
    offset?: number;
  }): Promise<CaseDetail[]> {
    return this.request<CaseDetail[]>("/cases", { method: "GET", params });
  }

  public async getCase(caseId: string): Promise<CaseDetail> {
    return this.request<CaseDetail>(`/cases/${caseId}`, { method: "GET" });
  }

  public async createCase(payload: CaseCreateRequest): Promise<CaseDetail> {
    return this.request<CaseDetail>("/cases", {
      method: "POST",
      body: JSON.stringify(payload),
    });
  }

  public async updateCase(
    caseId: string,
    payload: CaseUpdateRequest
  ): Promise<CaseDetail> {
    return this.request<CaseDetail>(`/cases/${caseId}`, {
      method: "PUT",
      body: JSON.stringify(payload),
    });
  }

  public async deleteCase(caseId: string): Promise<void> {
    await this.request<void>(`/cases/${caseId}`, { method: "DELETE" });
  }

  public async triggerAnalysis(caseId: string): Promise<{ task_id: string; status: string }> {
    return this.request<{ task_id: string; status: string }>(`/cases/${caseId}/analyze`, {
      method: "POST",
    });
  }

  public async getCaseStatus(caseId: string): Promise<CaseStatusResponse> {
    return this.request<CaseStatusResponse>(`/cases/${caseId}/status`, {
      method: "GET",
    });
  }

  // ---------------------------------------------------------------------------
  // Investigation Replay & Time-Slice State (Feature 4 / D4, TASK-043)
  // ---------------------------------------------------------------------------

  public async getReplayState(
    caseId: string,
    timestamp?: string
  ): Promise<ReplayStatePayload> {
    return this.request<ReplayStatePayload>(`/cases/${caseId}/replay`, {
      method: "GET",
      params: timestamp ? { t: timestamp } : undefined,
    });
  }

  public getSarChipUrl(caseId: string): string {
    return this.buildUrl(`/cases/${caseId}/detection/sar-chip`);
  }

  // ---------------------------------------------------------------------------
  // "What-If" Scenario Simulation Endpoints (TASK-037, FR-19)
  // ---------------------------------------------------------------------------

  public async simulateWhatIf(
    caseId: string,
    payload: WhatIfRequest
  ): Promise<WhatIfScenarioResponse> {
    return this.request<WhatIfScenarioResponse>(`/cases/${caseId}/whatif`, {
      method: "POST",
      body: JSON.stringify(payload),
    });
  }

  public async listScenarios(caseId: string): Promise<WhatIfScenarioSummary[]> {
    return this.request<WhatIfScenarioSummary[]>(`/cases/${caseId}/scenarios`, {
      method: "GET",
    });
  }

  public async getScenario(
    caseId: string,
    scenarioId: string
  ): Promise<WhatIfScenarioResponse> {
    return this.request<WhatIfScenarioResponse>(
      `/cases/${caseId}/scenarios/${scenarioId}`,
      { method: "GET" }
    );
  }

  // ---------------------------------------------------------------------------
  // Legal Evidence Dossier Endpoints (FR-20, C13)
  // ---------------------------------------------------------------------------

  public async generateDossier(
    caseId: string,
    payload?: DossierGenerateRequest
  ): Promise<DossierResult> {
    return this.request<DossierResult>(`/cases/${caseId}/dossier`, {
      method: "POST",
      body: payload ? JSON.stringify(payload) : undefined,
    });
  }

  public async getDossier(caseId: string): Promise<DossierResult> {
    return this.request<DossierResult>(`/cases/${caseId}/dossier`, {
      method: "GET",
    });
  }

  public getDossierDownloadUrl(caseId: string): string {
    return this.buildUrl(`/cases/${caseId}/dossier`);
  }

  // ---------------------------------------------------------------------------
  // Multi-Criteria AHP Weight Management Endpoints (FR-12)
  // ---------------------------------------------------------------------------

  public async getAhpWeights(): Promise<AHPConfigResponse> {
    return this.request<AHPConfigResponse>("/ahp/weights", { method: "GET" });
  }

  public async updateAhpWeights(
    payload: AHPWeightUpdatePayload
  ): Promise<AHPConfigResponse> {
    return this.request<AHPConfigResponse>("/ahp/weights", {
      method: "PUT",
      body: JSON.stringify(payload),
    });
  }

  // ---------------------------------------------------------------------------
  // Security Audit Logging Endpoints (Section 5, TASK-038)
  // ---------------------------------------------------------------------------

  public async getAdminAuditLogs(params?: {
    case_id?: string;
    user_id?: string;
    action?: string;
    limit?: number;
    offset?: number;
  }): Promise<AuditLogListResponse> {
    return this.request<AuditLogListResponse>("/admin/audit-logs", {
      method: "GET",
      params,
    });
  }

  // ---------------------------------------------------------------------------
  // Authentication & Identity Endpoints
  // ---------------------------------------------------------------------------

  public async login(formData: FormData | URLSearchParams): Promise<TokenResponse> {
    const response = await this.request<TokenResponse>("/auth/token", {
      method: "POST",
      body: formData,
      skipAuth: true,
    });
    if (response.access_token) {
      this.setToken(response.access_token);
    }
    return response;
  }

  public async refresh(refreshToken: string): Promise<TokenResponse> {
    const response = await this.request<TokenResponse>("/auth/refresh", {
      method: "POST",
      body: JSON.stringify({ refresh_token: refreshToken }),
      skipAuth: true,
    });
    if (response.access_token) {
      this.setToken(response.access_token);
    }
    return response;
  }

  public async getCurrentUser(): Promise<UserProfileResponse> {
    return this.request<UserProfileResponse>("/auth/me", { method: "GET" });
  }

  public logout(): void {
    this.clearToken();
  }
}

// Global singleton instance for convenient frontend consumption
export const apiClient = new ApiClient();
