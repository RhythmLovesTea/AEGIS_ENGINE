# AEGIS-Marine — System Architecture Document

**Companion to:** AEGIS-Marine PRD v2.0, AEGIS-Marine Tech Stack Recommendation
**Date:** September 3, 2026
**Status:** Draft for Build
**Sources synthesized:** PS 26143 layman problem explanation, Marine Oil Spill Novel Features catalog, and the corrected technical specification (SAR/EO physics, hydrodynamic hindcasting, AIS attribution scoring).

---

## 1. Purpose & Scope

This document describes the **technical architecture** of AEGIS-Marine: how the four analytical tiers (detection, characterization, hindcasting, AIS attribution) are decomposed into services, how data flows between them, how the explainability/forensic-replay features are implemented, and how the system is deployed.

It translates the PRD's functional requirements (FR-1 through FR-21) and feature catalog (Core/Differentiating/Premium) into concrete components, data contracts, and infrastructure, using the tech stack already selected (Next.js/MapLibre/deck.gl frontend, Python/FastAPI backend, PostgreSQL+PostGIS+TimescaleDB, Keycloak/Auth.js, Kubernetes).

---

## 2. Architectural Principles

These principles are carried directly from the PRD's guiding principles (Section 17) into concrete design constraints:

1. **Pipeline, not monolith.** Each of the four tiers is an independently deployable, independently scalable service with a well-defined input/output contract (GeoJSON in → GeoJSON out, etc.), because their compute profiles differ wildly (GPU-bound segmentation vs. CPU-bound particle simulation vs. I/O-bound AIS querying).
2. **Every output carries its uncertainty.** No service returns a bare point estimate — detection confidence, origin covariance, and attribution sub-scores are first-class fields in every data contract, not something computed only in the UI.
3. **Explainability is structural, not cosmetic.** The "Why this vessel?" breakdown (novel-features catalog, Feature 1) is not a UI trick applied after scoring — the scoring engine is required to persist its intermediate sub-scores and evidence pointers as part of its output schema, so the explanation is a direct read of stored data, never a reconstruction.
4. **Replayable by construction.** Because Investigation Replay (novel-features catalog, Feature 4) and the time-scrubber UI need to reconstruct "what did we know/compute at time T," every stage's intermediate state (particle positions per timestep, evolving scores) is persisted, not discarded after the final answer is produced.
5. **Degrade gracefully to synthetic/offline data.** Every external data dependency (live AIS feed, live CMEMS/ERA5 feed) has a fallback path to cached or synthetic data behind the same interface, so a missing upstream feed fails a single adapter, not the pipeline.
6. **Human-in-the-loop by default.** The system produces ranked, explained candidates and a case dossier for a human investigator to review — no component auto-escalates a finding to an external system without a human action.

---

## 3. High-Level Architecture

```
                                   ┌─────────────────────────────┐
                                   │   Geospatial War Room (UI)   │
                                   │  Next.js + MapLibre + deck.gl│
                                   └───────────────┬──────────────┘
                                                    │ HTTPS / WebSocket
                                   ┌────────────────▼──────────────┐
                                   │        API Gateway / BFF        │
                                   │   FastAPI (case orchestration)  │
                                   └───┬─────────┬─────────┬────────┘
                    ┌──────────────────┘         │         └──────────────────┐
                    ▼                             ▼                            ▼
      ┌─────────────────────────┐   ┌─────────────────────────┐   ┌──────────────────────────┐
      │  TIER 1 SERVICE          │   │  TIER 2 SERVICE          │   │  TIER 3 SERVICE           │
      │  EO Ingestion &          │──▶│  Morphometry & Age       │──▶│  Hydrodynamic Hindcast /  │
      │  Segmentation            │   │  Inversion               │   │  Forecast (OpenDrift)     │
      │  (PyTorch/DeepLabv3+)    │   │                           │   │                           │
      └─────────────┬─────────────┘   └─────────────┬─────────────┘   └─────────────┬──────────────┘
                    │                                │                               │
                    │                                │                               ▼
                    │                                │                 ┌──────────────────────────┐
                    │                                │                 │  TIER 4 SERVICE           │
                    │                                └────────────────▶│  AIS Correlation &        │
                    │                                                  │  Attribution Scoring      │
                    │                                                  └─────────────┬──────────────┘
                    │                                                                │
                    │                                                                ▼
                    │                                                  ┌──────────────────────────┐
                    │                                                  │  EXPLAINABILITY &          │
                    │                                                  │  EVIDENCE SERVICE          │
                    │                                                  │  (Why-vessel, counterfactual,│
                    │                                                  │   alt-explanation engine)  │
                    │                                                  └─────────────┬──────────────┘
                    │                                                                │
                    ▼                                                                ▼
      ┌─────────────────────────────────────────────────────────────────────────────────────────┐
      │                              DOSSIER / REPORT GENERATION SERVICE                          │
      │                        (WeasyPrint/ReportLab — Case PDF, audit trail)                      │
      └─────────────────────────────────────────────────────────────────────────────────────────┘

      ┌─────────────────────────────── CROSS-CUTTING PLATFORM SERVICES ───────────────────────────┐
      │  Job Orchestration (Celery + Redis)  │  Auth (Keycloak/Auth.js, RBAC)  │  Observability     │
      │  Data Platform (PostgreSQL+PostGIS+TimescaleDB, S3/MinIO object storage)                    │
      │  External Data Adapters: Copernicus (Sentinel-1/-2), CMEMS, ERA5/GFS, MarineCadastre/AISHub,│
      │  Synthetic-Data Generator (fallback for imagery/AIS/met-ocean)                              │
      └─────────────────────────────────────────────────────────────────────────────────────────────┘
```

---

## 4. Component Architecture

### 4.1 Tier 1 Service — EO Ingestion & Segmentation

**Responsibility:** Turn a raw satellite scene into a candidate slick polygon with a confidence score, rejecting lookalikes.

| Sub-component | Function | Key Tech |
|---|---|---|
| Ingestion Adapter | Pulls Level-1 Sentinel-1 GRD (VV/VH) from Copernicus Open Access; falls back to a pre-cached tile set or synthetic scene generator if unavailable | Rasterio, GDAL |
| Preprocessing | Lee speckle filter (5×5 window), land masking, CRS reprojection (EPSG:4326 → local UTM) | GDAL, Rasterio |
| Segmentation Model Server | DeepLabv3+ (ResNet-50 encoder, ASPP dilation rates {1,6,12,18}), trained with compound loss (Focal + Dice + Boundary) | PyTorch, Segmentation Models PyTorch (SMP), served via TorchServe or a FastAPI model-serving wrapper |
| Lookalike Rejection Module | Computes Cloude-Pottier entropy (H) & mean alpha angle from polarimetric decomposition; pulls co-located ERA5 wind (reject < 3 m/s, evaluate 4–10 m/s band) | NumPy/SciPy, ERA5 adapter |
| EO Cross-Validation Module | When co-located Sentinel-2/Landsat imagery exists: computes SFOI, NDOI indices and red-edge (705 nm) biogenic discrimination | Rasterio, NumPy |
| Output Writer | Persists slick polygon (PostGIS geometry), centroid, area, confidence, and rejection-check results | PostGIS |

**Output contract (`SlickDetection`):** GeoJSON polygon + `{confidence, detection_time, sensor, wind_speed_ms, entropy_H, mean_alpha_deg, lookalike_risk, sfoi, ndoi}`.

### 4.2 Tier 2 Service — Morphometry, Thickness & Age Inversion

**Responsibility:** Characterize the detected slick and estimate elapsed time since release (`t_age`), which bounds the Tier 3 hindcast window.

| Sub-component | Function |
|---|---|
| Morphometry Engine | Spatial central moments → area (`A_s`), perimeter, principal dispersion axis (`θ_slick`) |
| Thickness Classifier | BAOAC code (1–5) classification + polarimetric dielectric thickness inversion where feasible |
| Fay Age-Inversion Engine | Inverts Fay's mechanical spreading law against `A_s` to compute `t_age`; applies confidence decay for `t_age > 72h` (evaporation/emulsification degrade reliability) |

**Output contract (`SlickCharacterization`):** `{area_m2, perimeter_m, principal_axis_deg, baoac_code, estimated_volume_m3, t_age_hours, age_confidence}`.

### 4.3 Tier 3 Service — Hydrodynamic Hindcast & Forecast Engine

**Responsibility:** Run backward Lagrangian simulation to estimate the spill's origin region and time window; optionally run a forward forecast for shoreline-impact planning.

| Sub-component | Function |
|---|---|
| Met-Ocean Adapter | Fetches CMEMS GLO12 surface currents and ERA5/GFS 10 m winds for the region/time window; falls back to cached NetCDF subsets or a synthetic current/wind field generator |
| Backward Hindcast Runner (Sub-Module 3A) | OpenDrift/OpenOil: seeds ≥10,000 particles across the slick polygon, runs backward advection (Δt = −15 min) over `[t_obs − t_age, t_obs]`, incorporating current, wind-drift (`c_w` 2.5–3.5%), Stokes drift, and Coriolis rotation |
| Origin Density Estimator | 2D Gaussian KDE over the particle ensemble at each candidate release time → origin centroid `μ_p`, covariance `Σ_p` |
| Forward Forecast Runner (Sub-Module 3B) | +72h forward simulation with Mackay evaporative-loss and emulsification weathering; flags particles within 50 m of coast as stranded; computes Estimated Time of Beaching (ETB), Coastal Vulnerability Index (CVI), beached volume |
| Particle State Store | Persists per-timestep particle positions (for replay) rather than only the final KDE result |

**Output contract (`OriginEstimate`):** `{origin_centroid: [lat,lon], covariance_matrix, time_window: [t_start, t_end], confidence_pct, region_area_km2, particle_trajectory_ref}` and, optionally, `ForwardForecast: {etb, cvi, beached_volume_m3, shoreline_impact_polygon}`.

### 4.4 Tier 4 Service — AIS Correlation & Attribution Scoring Engine

**Responsibility:** Reconstruct vessel traffic around the estimated origin/time window, detect behavioral anomalies, and compute the ranked, weighted Culprit Score.

| Sub-component | Function |
|---|---|
| AIS Query Adapter | Pulls historical AIS (MarineCadastre/AISHub) within `μ_p ± 3Σ_p` spatially and `t_obs ± t_age` temporally; falls back to the synthetic-AIS generator when live coverage is insufficient |
| Trajectory Reconstructor | Cubic-spline interpolation of discrete AIS position reports (Types 1–3) into continuous per-vessel tracks |
| Anomaly Detector | Flags speed drops into the 4–8 kt band, abnormal course turns, and AIS transponder gaps (`A_dark`, "dark ship" behavior) |
| Non-AIS Vessel Flagger (Premium, P4) | Supplementary SAR ship-wake / optical vessel detection to surface non-cooperative targets as "unknown" rather than silently dropping them |
| Scoring Engine | Computes five sub-scores per candidate vessel and combines them via AHP-derived weights `w = [0.30, 0.25, 0.15, 0.20, 0.10]` into `S_culprit ∈ [0,100]`:<br>• `S_spatial` — Mahalanobis distance to `μ_p`<br>• `S_temporal` — exponential decay (`τ = 1.5h`) from closest AIS timestamp to estimated release time<br>• `S_kinematic` — heading alignment with `θ_slick`, modulated by speed<br>• `S_anomaly` — bounded combination of speed/course/dark-gap indicators<br>• `S_type` — categorical vessel-type prior (Tanker 1.00, Cargo 0.75, Offshore 0.50, Fishing 0.30, Pleasure 0.05) |
| AHP Weight Manager | Stores the pairwise comparison matrix and consistency ratio (`CR = 0.0094 < 0.10`); exposes both for transparency (D6) and supports "what-if" reweighting (P3) |

**Output contract (`VesselCandidate`):** `{mmsi, imo, name, flag_state, vessel_type, s_culprit, sub_scores: {spatial, temporal, kinematic, anomaly, type}, evidence_refs: [...], anomaly_flags: [...], ais_coverage: "full"|"partial"|"dark_gap"|"non_ais_unknown"}`.

### 4.5 Explainability & Evidence Service

This service implements the differentiator features from the novel-features catalog directly as backend capabilities, not UI-only logic — consistent with Architectural Principle 3.

| Sub-component | Maps to Feature | Function |
|---|---|---|
| Why-This-Vessel Composer | Feature 1 | Reads the persisted sub-scores + evidence refs for a `VesselCandidate` and assembles the structured explanation payload consumed by the UI panel |
| Counterfactual Simulator | Feature 2 (D2) | For a candidate vessel, re-runs a *forward* OpenDrift simulation seeded at the vessel's actual track/time, and computes a shape/position similarity score against the observed slick |
| Alternative Explanation Engine | Feature 7 (P2) | Scores non-vessel hypotheses (natural seep, imaging artifact, unlisted/non-AIS vessel) alongside the ranked vessel list, using the Tier 1 lookalike-risk score and Tier 4 AIS-coverage gaps as inputs |
| Evidence Timeline Builder | Feature 8 | Assembles a chronological event reconstruction (vessel enters region → anomaly detected → estimated release → detection → slick reaches observed position) from the persisted Tier 3/4 timestamps |
| Evidence Graph Builder | Feature 11 (P5) | Constructs the node/edge graph (observation → slick → origin → time window → AIS records → candidate vessels) for the interactive graph UI |
| Replay State Server | Feature 4 (D4) | Serves per-timestep particle positions, vessel positions, and evolving `S_culprit` values to the frontend time-scrubber |

### 4.6 Case Orchestration Service (API Gateway / BFF)

Coordinates a case run across the four tiers and the explainability service; owns the case state machine and exposes the primary REST/WebSocket API to the frontend.

- Triggers each tier as an async Celery task, passing the previous tier's output as input.
- Tracks case status (`detecting → characterizing → hindcasting → correlating → scoring → ready`) and pushes progress over WebSocket for the UI's staged-reveal experience (supports Investigation Replay's "reveal" pacing).
- Exposes the "what-if" parameter-override endpoint (P3): re-invokes Tier 3/4 with adjusted `t_age` window, origin radius, or search window, without re-running Tier 1 segmentation.
- Enforces RBAC at the endpoint level (see Section 10).

### 4.7 Dossier / Report Generation Service

- Assembles the final case report: detection metadata, slick characterization, origin estimate with confidence, ranked suspect list with sub-scores, alternative explanations considered, and the required responsible-use disclaimer language (FR-20).
- Renders to PDF via WeasyPrint/ReportLab; embeds SAR imagery thumbnails, drift skill-score summaries, and vessel kinematic logs.
- Writes the generated PDF to object storage and records an immutable audit entry (case ID, generating user, model/weight versions used) for later review.

### 4.8 Geospatial War Room (Frontend)

- **Map layers:** raw SAR backscatter, segmented slick polygon, ocean current streamlines, AIS tracks, origin probability heatmap (D3) — independently toggleable, rendered via MapLibre GL base map + deck.gl overlay layers (`ScatterplotLayer`/`TripsLayer` for particles and vessel tracks).
- **Time-scrubber:** drives the Replay State Server (4.5) to animate reverse particle convergence and forward vessel motion, updating `S_culprit` rankings live as the scrubber moves.
- **Suspect ranking panel:** ranked `VesselCandidate` cards; clicking a card opens the Why-This-Vessel panel (D1) and, where available, the counterfactual similarity result (D2).
- **What-if controls (P3):** sliders/inputs for `t_age` window, origin radius, search window; changes call the Case Orchestration Service's override endpoint and re-render on response.
- **Evidence graph view (P5):** interactive node-graph component consuming the Evidence Graph Builder output.
- **Dossier export button:** triggers the Dossier Service and surfaces a download link once ready.

### 4.9 Auth & Identity

- Auth.js in the Next.js layer, backed by an OIDC provider (Clerk/Auth0 for early build phases, Keycloak for the operational deployment — see Tech Stack doc Section 3).
- Roles: `investigator`, `analyst`, `legal_reviewer`, `admin` — each maps to a distinct permission set enforced at the Case Orchestration Service's API layer (see Section 10).

### 4.10 Data Platform

| Store | Purpose |
|---|---|
| PostgreSQL + PostGIS | Case metadata, slick polygons, origin geometries, vessel candidate records, AHP weight configs — anything relational/spatial |
| TimescaleDB (extension on the same Postgres) | Raw AIS position time series per MMSI, particle-trajectory time series (for replay) |
| S3-compatible object storage (AWS S3 / MinIO) | Raw SAR/EO tiles, CMEMS/ERA5 NetCDF files, generated PDF dossiers, model checkpoints |
| Redis | Celery broker, job-status cache, hot AHP-weight cache |

---

## 5. End-to-End Data Flow (Case Lifecycle)

```
1. Case Created
   Operator selects/uploads a Sentinel-1 scene (or a live-monitoring trigger fires)
                    │
2. Tier 1 — Segmentation
   Preprocess → DeepLabv3+ inference → lookalike rejection → (optional EO cross-check)
                    │  → SlickDetection persisted
3. Tier 2 — Characterization & Aging
   Morphometry → BAOAC thickness → Fay age inversion
                    │  → SlickCharacterization persisted (t_age computed)
4. Tier 3 — Hindcasting
   Fetch CMEMS/ERA5 for [t_obs - t_age, t_obs] → seed 10,000 particles →
   backward advection → Gaussian KDE → origin centroid + covariance
                    │  → OriginEstimate persisted (+ optional +72h forward forecast)
5. Tier 4 — AIS Correlation & Scoring
   Query AIS within μ_p ± 3Σ_p, t_obs ± t_age → spline interpolation →
   anomaly detection → AHP-weighted S_culprit per vessel
                    │  → Ranked VesselCandidate list persisted
6. Explainability & Evidence
   Why-This-Vessel composition, counterfactual simulation (top-N vessels),
   alternative-explanation scoring, evidence timeline/graph assembly
                    │
7. Case Ready
   UI displays ranked, explained suspects; operator can replay, run what-if
   scenarios, inspect evidence graph, and adjust assumptions
                    │
8. Dossier Export (on demand)
   Dossier Service assembles PDF → stored in object storage → audit entry recorded
```

Each numbered stage after Case Creation runs as an async Celery task chain; the orchestration service persists intermediate outputs so a failure or a "what-if" re-run at stage 4/5 does not require re-running stages 1–3.

---

## 6. Core Data Model (Entity Overview)

| Entity | Key Fields | Notes |
|---|---|---|
| `Case` | id, status, created_by, created_at, region, source_scene_ref | Root aggregate for an investigation |
| `SlickDetection` | case_id, polygon (PostGIS geometry), centroid, area_m2, confidence, lookalike_risk, sensor, detection_time | Tier 1 output |
| `SlickCharacterization` | case_id, perimeter_m, principal_axis_deg, baoac_code, t_age_hours, age_confidence | Tier 2 output |
| `OriginEstimate` | case_id, centroid, covariance_matrix, time_window, confidence_pct, particle_trajectory_ref | Tier 3 output; `particle_trajectory_ref` points to TimescaleDB series for replay |
| `ForwardForecast` | case_id, etb, cvi, beached_volume_m3, shoreline_impact_polygon | Optional Tier 3B output |
| `VesselCandidate` | case_id, mmsi, imo, name, flag_state, vessel_type, s_culprit, sub_scores (jsonb), anomaly_flags (jsonb), ais_coverage | Tier 4 output, one row per ranked vessel |
| `AlternativeExplanation` | case_id, hypothesis ("natural_seep"/"imaging_artifact"/"non_ais_vessel"), score, evidence | Explainability service output |
| `AISTrack` (Timescale hypertable) | mmsi, timestamp, lat, lon, sog, cog | Raw/interpolated AIS series feeding Tier 4 |
| `AHPConfig` | version, pairwise_matrix (jsonb), weights, consistency_ratio | Versioned scoring configuration (supports D6 transparency + P3 what-if) |
| `Dossier` | case_id, pdf_ref (object storage key), generated_by, generated_at, model_versions (jsonb) | Audit-linked export record |

---

## 7. API Surface (Representative Endpoints)

All endpoints are served behind the Case Orchestration Service (FastAPI), which internally dispatches to the tier services.

| Method & Path | Purpose | Auth Role(s) |
|---|---|---|
| `POST /cases` | Create a new case from a scene reference or upload | investigator, analyst |
| `GET /cases/{id}` | Fetch case status and all tier outputs | investigator, analyst, legal_reviewer |
| `POST /cases/{id}/segment` | (Internal/async trigger) Run Tier 1 | system |
| `POST /cases/{id}/hindcast` | (Internal/async trigger) Run Tier 3 | system |
| `POST /cases/{id}/correlate` | (Internal/async trigger) Run Tier 4 | system |
| `GET /cases/{id}/vessels` | Ranked `VesselCandidate` list | investigator, analyst, legal_reviewer |
| `GET /cases/{id}/vessels/{mmsi}/explain` | Why-This-Vessel breakdown | investigator, analyst, legal_reviewer |
| `POST /cases/{id}/vessels/{mmsi}/counterfactual` | Run counterfactual simulation for one candidate | investigator, analyst |
| `GET /cases/{id}/alternatives` | Alternative-explanation scores | investigator, analyst, legal_reviewer |
| `GET /cases/{id}/replay?t=...` | Particle/vessel state at time `t` (drives the scrubber) | investigator, analyst |
| `POST /cases/{id}/whatif` | Re-run Tier 3/4 with overridden parameters | investigator, analyst |
| `GET /cases/{id}/evidence-graph` | Evidence graph nodes/edges | investigator, analyst, legal_reviewer |
| `POST /cases/{id}/dossier` | Generate and store the PDF dossier | investigator, legal_reviewer |
| `GET /cases/{id}/dossier` | Download the generated dossier | investigator, legal_reviewer |
| `GET /ahp-config` | Current AHP weights + consistency ratio | any authenticated role |
| `WS /cases/{id}/status` | Live case-progress stream | investigator, analyst |

---

## 8. Job Orchestration & Async Processing

- **Celery + Redis** executes the tier pipeline as a task chain: `segment → characterize → hindcast → correlate → explain`, with each task's output written to Postgres/object storage before the next task is dispatched.
- Tasks are idempotent and re-runnable from any stage — this is what makes the "what-if" feature (P3) cheap: overriding a Tier 3 parameter only re-queues `hindcast → correlate → explain`, not the full chain.
- Long-running tasks (segmentation inference, 10,000-particle hindcast) report progress increments so the orchestration service can push meaningful WebSocket updates rather than a binary "done/not done" status.
- A dead-letter queue captures failed tasks (e.g., a met-ocean data fetch timeout) and triggers the synthetic/cached-data fallback adapter automatically, logging the degradation for audit purposes.

---

## 9. Deployment Architecture

Consistent with the Tech Stack Recommendation (Section 5) and PRD roadmap (Section 16):

```
Phase 0–4 (Build & Integration): Docker Compose
┌─────────────────────────────────────────────────────────┐
│ next-js-frontend │ fastapi-gateway │ celery-worker(s)      │
│ postgres+postgis+timescale │ redis │ minio (object storage)│
└─────────────────────────────────────────────────────────┘

Phase 5–7 (Hardening → Operational): Kubernetes
┌───────────────────────────────────────────────────────────────────┐
│ Namespace: aegis-marine                                             │
│  ┌───────────────┐ ┌───────────────┐ ┌────────────────────────┐   │
│  │ Deployment:     │ │ Deployment:    │ │ Deployment/Job:         │   │
│  │ frontend (Next) │ │ api-gateway    │ │ tier1-segmentation      │   │
│  │                 │ │ (FastAPI)      │ │ (GPU node pool)         │   │
│  └───────────────┘ └───────────────┘ └────────────────────────┘   │
│  ┌────────────────────────┐ ┌────────────────────────┐             │
│  │ Deployment/Job:          │ │ Deployment:              │             │
│  │ tier3-hindcast           │ │ tier4-ais-correlation    │             │
│  │ (CPU node pool, bursty)  │ │                          │             │
│  └────────────────────────┘ └────────────────────────┘             │
│  ┌────────────────────────┐ ┌────────────────────────┐             │
│  │ StatefulSet:             │ │ Deployment:              │             │
│  │ postgres+postgis+        │ │ redis (Celery broker)    │             │
│  │ timescaledb               │ │                          │             │
│  └────────────────────────┘ └────────────────────────┘             │
│  External/Managed: S3-compatible object storage, Keycloak            │
└───────────────────────────────────────────────────────────────────┘
```

- **GPU node pool** isolates Tier 1 (segmentation) so it can autoscale independently and use GPU-backed nodes without forcing the rest of the platform onto GPU hardware.
- **CPU node pool** for Tier 3 (particle simulation) is provisioned for burst capacity — hindcast jobs are triggered per-incident, not continuously running.
- **StatefulSet** for the database tier ensures persistent volume claims survive pod rescheduling.
- Ingress/Gateway layer terminates TLS and routes `/api/*` to the FastAPI gateway and everything else to the Next.js frontend.

---

## 10. Security & Access Control Architecture

| Concern | Design |
|---|---|
| Authentication | OIDC via Keycloak (production) / Clerk-Auth0 (early build), integrated through Auth.js in the frontend and JWT validation in FastAPI |
| Authorization (RBAC) | Roles: `investigator` (full case workflow), `analyst` (read + what-if, no dossier export), `legal_reviewer` (read + dossier export, no case creation), `admin` (AHP config, user management) |
| Data classification | Raw AIS/vessel-identity data and generated dossiers are treated as sensitive; access logged per FR/NFR auditability requirement |
| Network segmentation | Tier 1/3 compute services (GPU/CPU pools) are not directly internet-exposed; only the API gateway is reachable externally |
| Audit trail | Every case-state transition, dossier generation, and what-if override is written to an append-only audit log with user identity and timestamp |
| Secrets management | Kubernetes Secrets (or a managed secrets store) for DB credentials, object-storage keys, and identity-provider client secrets — never embedded in service images |

---

## 11. Observability & Auditability

- **Structured logging** across all services (JSON logs) correlated by `case_id` and `trace_id`, so a single case's journey through all four tiers can be reconstructed from logs alone.
- **Metrics** (Prometheus-compatible): per-tier task duration (validating the ~4.5-minute end-to-end latency budget), queue depth, model-inference latency, particle-simulation wall-clock time.
- **Model/weight versioning:** every `SlickDetection`, `OriginEstimate`, and `VesselCandidate` record stores the model/AHP-config version used to produce it, so historical cases remain reproducible even after the segmentation model or AHP weights are updated.
- **Case audit log:** immutable record of who created a case, who ran a what-if override, who exported a dossier — directly supporting the PRD's "Auditability" NFR and the legal-review use case.

---

## 12. Resilience & Fallback Strategy

| Dependency | Failure Mode | Fallback |
|---|---|---|
| Copernicus Sentinel-1/-2 feed | Unavailable / rate-limited | Pre-cached tile set or synthetic-scene generator behind the same Ingestion Adapter interface |
| CMEMS / ERA5 met-ocean feed | Unavailable / stale for region | Cached NetCDF subsets or a synthetic current/wind field generator |
| MarineCadastre / AISHub AIS feed | Sparse coverage for region/time | Synthetic-AIS generator producing schema-identical records |
| Segmentation model | Low-confidence or ambiguous result | Result is still returned with an explicit low-confidence flag and routed to the Alternative Explanation Engine rather than silently discarded |
| Vessel has no AIS | Non-cooperative / non-equipped vessel | Flagged as "unknown" via SAR ship-wake/optical detection (P4), included in the dossier rather than omitted |

This mirrors the PRD's Risk table (Section 15) and ensures the system remains demonstrable and testable end-to-end even when one or more live data sources are degraded — a requirement now doubly important since the system is being built for sustained real-world operation, not a single scripted run.

---

## 13. Traceability: Architecture Components → PRD Requirements

| Architecture Component | PRD Requirement(s) Satisfied |
|---|---|
| Tier 1 Service | FR-1, FR-2, FR-3, FR-4, C1, C2, C3 |
| Tier 2 Service | FR-5, FR-6, FR-7, C4, C5, C6 |
| Tier 3 Service | FR-8, FR-9, FR-10, C7, C8, D5 |
| Tier 4 Service | FR-11, FR-12, FR-13, FR-14, FR-19, C9, C10, C11, P4 |
| Explainability & Evidence Service | FR-15, FR-16, D1, D2, D6, P2, P5 |
| Case Orchestration Service | FR-17, P3 |
| Dossier Service | FR-18, FR-20, C13 |
| Data Platform + Auth | NFR (Auditability, Data Resilience), FR-21 |

---

*End of Document*
