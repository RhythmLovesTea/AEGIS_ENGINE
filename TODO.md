# AEGIS-Marine: Master Project TODO & Execution Roadmap

This document serves as the master, strictly sequential, atomic task backlog for building **AEGIS-Marine** (Automated Spaceborne Oil Spill Detection, Hydrodynamic Hindcasting & AIS Vessel Attribution Platform).

### Sequencing & Atomicity Principles
1. **Strict Linearity:** Every task $N$ depends exclusively on tasks $1 \dots N-1$. No overlapping or circular dependencies.
2. **Atomic Units:** Each task is an indivisible unit of engineering work with concrete input requirements, deliverables, and objective verification criteria.
3. **Source-of-Truth Alignment:** Governed by `rules.md` (Constitutional Rules), `AEGIS-Marine_PRD.md` (Functional Requirements FR-01 to FR-20, NFRs), `AEGIS-Marine_Architecture.md` (Service Contracts & Data Model), `AEGIS-Marine_Tech_Stack_Recommendation.md`, `DESIGN.md` (Visual Tokens & UI Spec), `ADR.md`, and `corrected_version.pdf`.
4. **Rule Enforcement:** Enforces Product Rule 1 (Confidence on every estimate), Rule 2 (Persisted sub-scores), Rule 3 (No distance-only heuristics), Rule 4 (Flag dark vessels/gaps), Rule 5 (Alternative explanation engine), Rule 6 (Banned term enforcement), Rule 7 (Show math / `GET /ahp-config`).

---

## Phase 0: Repository, Environment & Foundation Setup

### [x] TASK-001: Git Repository Initialization & Monorepo Directory Skeleton (Completed)
- **Status:** Completed
- **Domain:** Infrastructure / Repository
- **Prerequisites:** None
- **Objective:** Initialize the Git repository and create the canonical monorepo directory structure separating backend microservices, frontend application, shared contracts, scripts, and documentation fixtures.
- **Implementation Details:**
  - Initialize git repository (`git init`).
  - Create directory layout:
    - `backend/`: Python FastAPI services (`backend/app/`, `backend/core/`, `backend/services/`, `backend/workers/`)
    - `frontend/`: Next.js 15 application (`frontend/src/app/`, `frontend/src/components/`, `frontend/src/lib/`)
    - `data/`: Curated test fixtures (`data/sar/`, `data/ais/`, `data/metocean/`, `data/benchmarks/`)
    - `docker/`: Dockerfiles and Compose configurations
    - `scripts/`: Development and database migration scripts
    - `tests/`: End-to-end and integration test suites
  - Create `.gitignore` ignoring virtualenvs (`.venv/`), Node modules (`node_modules/`, `.next/`), bytecode (`__pycache__/`), data rasters (`*.nc`, `*.grd`, `*.tif`), and environment secrets (`.env`, `.env.*`).
- **Deliverables:** Directory tree, `.gitignore`.
- **Verification:** Run `git status` verifying clean untracked layout; run `find . -maxdepth 3 -type d` verifying directory structure.

---

### [x] TASK-002: Tooling Configuration & Banned-Language CI Linter (Rule 6 Enforcement) (Completed)
- **Status:** Completed
- **Domain:** Quality Assurance / Compliance
- **Prerequisites:** TASK-001
- **Objective:** Configure Python and TypeScript linting/formatting and build a pre-commit / CI linter enforcing PRD Rule 6 (banned terms).
- **Implementation Details:**
  - Create `pyproject.toml` configuring `ruff` (formatting and linting, line length 100, Python 3.12 target) and `mypy` (strict mode: `disallow_untyped_defs = true`, `check_untyped_defs = true`).
  - Configure ESLint and Prettier for the frontend (`frontend/.eslintrc.json`, `frontend/.prettierrc`).
  - Implement a dedicated compliance script `scripts/lint_banned_terms.py` that scans UI source files, templates, API error strings, and documentation for banned strings:
    - Banned: `"responsible vessel"`, `"guilty"`, `"polluter"` (as determination), `"proven"`, `"confirmed the culprit"`.
    - Allowed / required: `"most correlated vessel"`, `"candidate suspect"`, `"potential source"`.
- **Deliverables:** `pyproject.toml`, `scripts/lint_banned_terms.py`, `.pre-commit-config.yaml`.
- **Verification:** Run `python3 scripts/lint_banned_terms.py --test` with test fixtures containing banned and valid strings; ensure non-zero exit code on violation.

---

### [x] TASK-003: Core Infrastructure Orchestration (Docker Compose & Local Storage) (Completed)
- **Status:** Completed
- **Domain:** Infrastructure
- **Prerequisites:** TASK-002
- **Objective:** Configure containerized infrastructure for PostgreSQL (with PostGIS and TimescaleDB), Redis (Celery broker), and MinIO (S3-compatible object storage).
- **Implementation Details:**
  - Create `docker/docker-compose.yml` defining services:
    - `db`: `timescale/timescaledb-ha:pg16-latest` with PostGIS extension enabled. Port 5432. Healthcheck on `pg_isready`.
    - `redis`: `redis:7-alpine`. Port 6379. Healthcheck on `redis-cli ping`.
    - `minio`: `minio/minio:latest` with default bucket `aegis-storage` auto-created via `minio/mc`. Ports 9000 (API) and 9001 (Console).
  - Create `.env.example` with standard development credentials (`POSTGRES_USER`, `POSTGRES_PASSWORD`, `POSTGRES_DB`, `REDIS_URL`, `MINIO_ROOT_USER`, `MINIO_ROOT_PASSWORD`, `MINIO_BUCKET`).
- **Deliverables:** `docker/docker-compose.yml`, `.env.example`, `scripts/init_minio.sh`.
- **Verification:** Run `docker compose -f docker/docker-compose.yml up -d db redis minio` and test connections to Postgres, Redis, and MinIO S3 API via curl/pg_isready.

---

### [x] TASK-004: Database Migration Pipeline & Core Relational / Spatial Schema (Completed)
- **Status:** Completed
- **Domain:** Database Architecture
- **Prerequisites:** TASK-003
- **Objective:** Implement Alembic migration scaffolding and the core relational schema matching Architecture Section 6.
- **Implementation Details:**
  - Set up Alembic in `backend/alembic/` configured to connect to PostgreSQL with PostGIS extensions (`CREATE EXTENSION IF NOT EXISTS postgis;`, `CREATE EXTENSION IF NOT EXISTS timescaledb;`).
  - Implement migration `0001_initial_schema.py`:
    - `cases`: `id` (UUID PK), `status` (enum: `detecting`, `characterizing`, `hindcasting`, `correlating`, `scoring`, `ready`, `failed`), `region` (geometry polygon EPSG:4326), `source_scene_ref` (text), `created_by` (text), `created_at` (timestamptz).
    - `slick_detections`: `id` (UUID PK), `case_id` (FK), `polygon` (geometry polygon EPSG:4326), `centroid` (geometry point), `area_m2` (float), `confidence` (float), `lookalike_risk` (float), `sensor` (varchar), `detection_time` (timestamptz), `data_source` (enum: `live`, `cached`, `synthetic`).
    - `slick_characterizations`: `id` (UUID PK), `case_id` (FK), `perimeter_m` (float), `principal_axis_deg` (float), `baoac_code` (int), `estimated_volume_m3` (float), `t_age_hours` (float), `age_confidence` (float).
    - `origin_estimates`: `id` (UUID PK), `case_id` (FK), `centroid` (geometry point), `covariance_matrix` (jsonb), `time_window_start` (timestamptz), `time_window_end` (timestamptz), `confidence_pct` (float), `region_area_km2` (float), `particle_trajectory_ref` (text).
    - `forward_forecasts`: `id` (UUID PK), `case_id` (FK), `etb_hours` (float), `cvi_index` (float), `beached_volume_m3` (float), `shoreline_impact_polygon` (geometry polygon EPSG:4326).
    - `vessel_candidates`: `id` (UUID PK), `case_id` (FK), `mmsi` (int), `imo` (int), `name` (text), `flag_state` (text), `vessel_type` (text), `s_culprit` (float), `sub_scores` (jsonb: `{spatial, temporal, kinematic, anomaly, type}`), `anomaly_flags` (jsonb), `ais_coverage` (enum: `full`, `partial`, `dark_gap`, `non_ais_unknown`).
    - `alternative_explanations`: `id` (UUID PK), `case_id` (FK), `hypothesis` (varchar: `natural_seep`, `imaging_artifact`, `non_ais_vessel`), `score` (float), `evidence` (jsonb).
    - `audit_logs`: `id` (UUID PK), `case_id` (FK), `user_id` (text), `action` (text), `details` (jsonb), `timestamp` (timestamptz).
- **Deliverables:** `backend/alembic.ini`, `backend/alembic/env.py`, `backend/alembic/versions/0001_initial_schema.py`.
- **Verification:** Run `alembic upgrade head` against the running Postgres container; verify tables and spatial indices via `psql -c "\dt"`.

---

### [x] TASK-005: TimescaleDB Hypertable Setup for Particle Tracing & AIS Trajectories (Completed)
- **Status:** Completed
- **Domain:** Database Architecture
- **Prerequisites:** TASK-004
- **Objective:** Configure TimescaleDB hypertables for time-series particle advection trajectories and vessel AIS position tracks.
- **Implementation Details:**
  - Implement migration `0002_timescale_hypertables.py`:
    - `ais_tracks`: columns `mmsi` (bigint), `timestamp` (timestamptz), `point` (geometry(Point, 4326)), `sog` (float), `cog` (float), `heading` (float), `nav_status` (int), `data_source` (varchar). Convert to hypertable partitioned by `timestamp` (chunk time interval: 1 day). Spatial index on `point`, composite index on `(mmsi, timestamp DESC)`.
    - `particle_trajectories`: columns `case_id` (UUID), `particle_id` (int), `timestamp` (timestamptz), `point` (geometry(Point, 4326)), `depth_m` (float), `mass_fraction` (float), `status` (varchar: `active`, `beached`, `evaporated`). Convert to hypertable partitioned by `timestamp` (chunk time interval: 12 hours). Index on `(case_id, timestamp)`.
- **Deliverables:** `backend/alembic/versions/0002_timescale_hypertables.py`.
- **Verification:** Run `alembic upgrade head`; run `SELECT * FROM timescaledb_information.hypertables;` in PostgreSQL verifying `ais_tracks` and `particle_trajectories` are active hypertables.

---

### [x] TASK-006: Base Pydantic Data Contracts & Domain Models (Architecture Section 6) (Completed)
- **Status:** Completed
- **Domain:** Backend Core / Shared Contracts
- **Prerequisites:** TASK-005
- **Objective:** Define strongly typed, immutable Pydantic V2 models for all inter-service payloads, API requests, and responses.
- **Implementation Details:**
  - Create `backend/app/schemas/`:
    - `common.py`: `GeoJSONPolygon`, `GeoJSONPoint`, `ConfidenceValue` (bounded float $[0, 100]$), `DataSourceEnum` (`live`, `cached`, `synthetic`).
    - `detection.py`: `SlickDetectionCreate`, `SlickDetectionResponse`.
    - `characterization.py`: `SlickCharacterizationResponse` (`area_m2`, `perimeter_m`, `principal_axis_deg`, `baoac_code`, `estimated_volume_m3`, `t_age_hours`, `age_confidence`).
    - `hindcast.py`: `OriginEstimateResponse`, `ParticleState`, `ForwardForecastResponse`.
    - `vessel.py`: `VesselCandidateResponse` (including mandatory `sub_scores` dict and `ais_coverage`), `AISTrackPoint`.
    - `explainability.py`: `WhyThisVesselPayload`, `AlternativeExplanationPayload`, `EvidenceTimelineItem`, `EvidenceGraphPayload`.
    - `case.py`: `CaseCreateRequest`, `CaseDetailResponse`, `WhatIfRequest`.
  - Add validator ensuring any score or estimate contains an accompanying uncertainty/confidence field (enforcing Rule 1).
- **Deliverables:** `backend/app/schemas/*.py`.
- **Verification:** Run `pytest tests/test_schemas.py` verifying validation passes on valid schemas and fails if confidence or sub-scores are missing.

---

### [x] TASK-007: Celery & Redis Task Queue Infrastructure with Error Handling & Dead-Letter Queue (Completed)
- **Status:** Completed
- **Domain:** Backend Core / Distributed Tasks
- **Prerequisites:** TASK-006
- **Objective:** Establish the Celery application with Redis broker, task progress tracking, dead-letter routing, and automatic fallback handling.
- **Implementation Details:**
  - Create `backend/core/celery_app.py`:
    - Configure broker `REDIS_URL`, result backend `REDIS_URL`.
    - Task routing: `tier1.tasks` -> `queue_tier1` (GPU/Inference), `tier3.tasks` -> `queue_tier3` (Compute/OpenDrift), `tier4.tasks` -> `queue_tier4` (IO/Correlation), `default` -> `queue_default`.
    - Configure Dead Letter Queue (DLQ) / failure handler: upon unhandled network exception in external data fetchers, capture task failure, log degradation audit record, and route to synthetic fixture fallback.
    - Custom task base class `AegisTask` with `update_progress(percent: float, stage: str)` pushing updates to Redis Pub/Sub for WebSocket broadcasting.
- **Deliverables:** `backend/core/celery_app.py`, `backend/workers/worker.py`.
- **Verification:** Run a test celery worker with `celery -A backend.core.celery_app worker -l info --concurrency=1` and dispatch a dummy async task verifying state transition `PENDING -> PROGRESS -> SUCCESS`.

---

### [x] TASK-008: Synthetic Data Generator & Curated Test Fixtures (Completed)
- **Status:** Completed
- **Domain:** Data Platform / Testing
- **Prerequisites:** TASK-007
- **Objective:** Implement the synthetic data generator and load curated test fixtures for SAR scenes, met-ocean fields, and AIS traffic.
- **Implementation Details:**
  - Create `backend/services/data_adapters/synthetic_generator.py`:
    - Generate synthetic SAR slick masks (elliptical and tapering tails, pixel spacing 10m).
    - Generate synthetic CMEMS surface current NetCDF files (current velocity $u, v \in [0.1, 0.6]\text{ m/s}$).
    - Generate synthetic ERA5 10m wind fields (speed $5\text{ to }12\text{ m/s}$, direction $45^\circ\text{ to }90^\circ$).
    - Generate synthetic AIS vessel trajectories (MMSI, SOG, COG, lat/lon) with 5 vessels:
      - Vessel A (Tanker, loitering 5 kts, trajectory intersecting origin cloud, matching spill heading).
      - Vessel B (Cargo, transiting 16 kts without stopping).
      - Vessel C (Fishing, zig-zag pattern outside origin cloud).
      - Vessel D (Dark vessel with transponder gap $A_{dark}$ during spill time window).
      - Vessel E (Offshore supply vessel).
  - Save fixtures into `data/synthetic/` with manifest `manifest.json`.
- **Deliverables:** `backend/services/data_adapters/synthetic_generator.py`, test data fixtures in `data/synthetic/`.
- **Verification:** Run `python3 -m backend.services.data_adapters.synthetic_generator` and verify generation of valid GeoJSON, NetCDF, and CSV files in `data/synthetic/`.

---

## Phase 1: Tier 1 & Tier 2 — Detection, Characterization & Aging

### [x] TASK-009: SAR & EO Ingestion Adapters (Sentinel-1 / Sentinel-2 & Local GeoTIFF) (Completed)
- **Status:** Completed
- **Domain:** Tier 1 — Earth Observation Ingestion
- **Prerequisites:** TASK-008
- **Objective:** Build ingestion adapters supporting Copernicus Open Access Hub / CDSE and local GeoTIFF files with automatic fallback to synthetic fixtures.
- **Implementation Details:**
  - Create `backend/services/data_adapters/copernicus_adapter.py`:
    - Adapter for Sentinel-1 IW GRD (SAR VV/VH polarization) and Sentinel-2 L2A MSI products.
    - Support query by Bounding Box (WGS84) and timestamp.
    - Preprocessing pipeline using `rasterio`: radiometric calibration to $\sigma^0$ (dB), speckle filtering (Lee filter $5\times 5$), terrain correction, and tiling into $512\times 512$ patches with 20% overlap.
    - Fallback mechanism: if Copernicus API fails or credentials not configured, load matching synthetic scene from `data/synthetic/` and set `data_source = "synthetic"`.
- **Deliverables:** `backend/services/data_adapters/copernicus_adapter.py`, unit test in `tests/test_copernicus_adapter.py`.
- **Verification:** Execute `pytest tests/test_copernicus_adapter.py` asserting proper loading, speckle filtering, and fallback execution.

---

### [x] TASK-010: Radar Backscatter Polarimetry & Lookalike Rejection Filters (Completed)
- **Status:** Completed
- **Domain:** Tier 1 — Physics Diagnostics
- **Prerequisites:** TASK-009
- **Objective:** Implement physical polarimetric algorithms (Bragg resonance, Co-Polarization Difference, Damping Ratio) to reject low-wind and biogenic lookalikes.
- **Implementation Details:**
  - Create `backend/services/tier1_segmentation/physics_filters.py`:
    - Implement Bragg resonance scattering condition check:
      $$\lambda_B = \frac{\lambda_r}{2 \sin \theta_i}$$
    - Calculate Damping Ratio:
      $$DR = \frac{\sigma^0_{clean}}{\sigma^0_{slick}} \quad (\text{threshold } DR \ge 4.5\text{ dB})$$
    - Calculate Co-Polarization Difference (where dual-pol VV/HH available):
      $$PD = \sigma^0_{VV} - \sigma^0_{HH}$$
    - Low-wind lookalike filter: if local wind speed $U_{10} < 3.0\text{ m/s}$, flag low-wind calm water lookalike risk; if $U_{10} > 14.0\text{ m/s}$, flag high-wind dispersion.
    - Multispectral biogenic rejection: calculate NDVI / FAI (Floating Algae Index) on optical Sentinel-2 overlap; reject if vegetation/algal bloom detected.
- **Deliverables:** `backend/services/tier1_segmentation/physics_filters.py`, unit test `tests/test_physics_filters.py`.
- **Verification:** Run `pytest tests/test_physics_filters.py` with known input values and verify correct mathematical output and lookalike risk scoring.

---

### [x] TASK-011: Semantic Segmentation Model Architecture & Inference Service (DeepLabv3+) (Completed)
- **Status:** Completed
- **Domain:** Tier 1 — Deep Learning Segmentation
- **Prerequisites:** TASK-010
- **Objective:** Implement the DeepLabv3+ segmentation model with ASPP backbone and compound loss, with PyTorch inference engine and weight loader.
- **Implementation Details:**
  - Create `backend/services/tier1_segmentation/model.py`:
    - DeepLabv3+ architecture with ResNet-50 / ConvNeXt backbone, Atrous Spatial Pyramid Pooling (ASPP rates: 6, 12, 18).
    - Compound loss definition for training/evaluation:
      $$\mathcal{L}_{total} = \lambda_1 \mathcal{L}_{Focal} + \lambda_2 \mathcal{L}_{Lovasz}$$
  - Create `backend/services/tier1_segmentation/inference.py`:
    - Load pretrained weights (or synthetic-trained baseline checkpoint from `models/checkpoints/`).
    - Sliding window inference on $512\times 512$ tiles with Gaussian blend window smoothing.
    - Binarize mask with Otsu thresholding / fixed probability threshold $p \ge 0.5$.
    - Polygonize output into GeoJSON (WGS84 EPSG:4326) via `rasterio.features.shapes`.
    - Compute confidence score and lookalike risk score for each polygon.
- **Deliverables:** `backend/services/tier1_segmentation/model.py`, `backend/services/tier1_segmentation/inference.py`.
- **Verification:** Run `python3 -m backend.services.tier1_segmentation.inference --test-tile` on test fixture; verify generated GeoJSON polygon geometry and confidence.

---

### [x] TASK-012: Tier 1 Celery Pipeline Task & Integration Test (Completed)
- **Status:** Completed
- **Domain:** Tier 1 — Pipeline Integration
- **Prerequisites:** TASK-011
- **Objective:** Wrap Tier 1 into an idempotent Celery task that stores detections in PostGIS and pushes progress updates.
- **Implementation Details:**
  - Create `backend/workers/tasks/tier1_tasks.py`:
    - Define Celery task `run_tier1_segmentation(case_id: str, scene_ref: str)`.
    - Ingest scene, run physics filters, execute segmentation inference.
    - Persist `SlickDetection` record in PostgreSQL (`polygon`, `area_m2`, `confidence`, `lookalike_risk`).
    - Update case status to `characterizing`.
    - Publish progress to Redis channel `cases:{case_id}:progress`.
- **Deliverables:** `backend/workers/tasks/tier1_tasks.py`, integration test `tests/test_tier1_pipeline.py`.
- **Verification:** Run integration test executing the task against test database; assert `slick_detections` table contains valid PostGIS polygon with confidence $> 0$.

---

### [x] TASK-013: Morphometry, Skeletonization & Principal Axis Extraction (Completed)
- **Status:** Completed
- **Domain:** Tier 2 — Slick Morphometry
- **Prerequisites:** TASK-012
- **Objective:** Extract slick spatial properties including perimeter, area, eccentricity, skeleton, and orientation angle ($\theta_{slick}$).
- **Implementation Details:**
  - Create `backend/services/tier2_morphometry/morphometry.py`:
    - Project GeoJSON polygon from EPSG:4326 to local UTM projection for metric accuracy.
    - Compute exact area $A\text{ (m}^2)$ and perimeter $P\text{ (m)}$.
    - Compute hydraulic shape factor / circularity: $C = 4\pi A / P^2$.
    - Perform medial axis skeletonization (`skimage.morphology.skeletonize`) to find the spill's central backbone.
    - Perform Principal Component Analysis (PCA) on boundary contour coordinates to derive the principal axis orientation:
      $$\theta_{slick} = \frac{1}{2} \operatorname{atan2}(2 \mu_{11}, \mu_{20} - \mu_{02})$$
    - Return orientation in degrees $[0^\circ, 360^\circ)$.
- **Deliverables:** `backend/services/tier2_morphometry/morphometry.py`, unit test in `tests/test_morphometry.py`.
- **Verification:** Run `pytest tests/test_morphometry.py` with known geometric shapes (ellipse oriented at $45^\circ$); verify $\theta_{slick} = 45^\circ \pm 0.5^\circ$.

---

### [x] TASK-014: Mechanical Spreading Aging Inversion (Fay's Equations) (Completed)
- **Status:** Completed
- **Domain:** Tier 2 — Spill Aging Physics
- **Prerequisites:** TASK-013
- **Objective:** Implement physical inversion of Fay's three-regime mechanical spreading laws to estimate slick elapsed age ($t_{age}$) and uncertainty bound.
- **Implementation Details:**
  - Create `backend/services/tier2_morphometry/spreading_aging.py`:
    - Implement Fay's gravity-viscous and viscous-surface tension regime equations:
      $$r(t) = k_2 \left(\frac{\Delta \rho g V^2}{\nu^{1/2}}\right)^{1/6} t^{1/4} \quad \text{and} \quad r(t) = k_3 \left(\frac{\sigma^2}{\rho^2 \nu}\right)^{1/4} t^{3/4}$$
    - Invert equations given measured area $A = \pi r_{eff}^2$ and estimated volume $V$ to solve for $t_{age}\text{ (hours)}$:
      $$t_{age} = \left(\frac{r_{eff}}{k_3 (\sigma^2 / (\rho^2 \nu))^{1/4}}\right)^{4/3}$$
    - Physical parameters: water density $\rho_w = 1025\text{ kg/m}^3$, oil density $\rho_o = 880\text{ kg/m}^3$, kinematic viscosity $\nu = 1.05 \times 10^{-6}\text{ m}^2/\text{s}$, interfacial tension $\sigma = 0.03\text{ N/m}$.
    - Compute confidence interval $[t_{age, min}, t_{age, max}]$ based on oil type uncertainty.
    - Inline comments explicitly citing PRD Section 10 and technical specification formulas.
- **Deliverables:** `backend/services/tier2_morphometry/spreading_aging.py`, unit test in `tests/test_spreading_aging.py`.
- **Verification:** Run `pytest tests/test_spreading_aging.py` comparing hand-computed benchmark values with code outputs.

---

### [x] TASK-015: Thickness Profiling & Volumetric Estimation (Bonn Agreement BAOAC) (Completed)
- **Status:** Completed
- **Domain:** Tier 2 — Thickness Profiling
- **Prerequisites:** TASK-014
- **Objective:** Implement the Bonn Agreement Oil Appearance Code (BAOAC) classification to derive spatial thickness map and integrated spill volume.
- **Implementation Details:**
  - Create `backend/services/tier2_morphometry/thickness_profiler.py`:
    - Code table:
      - Code 1 (Sheen): $0.04 - 0.30\ \mu\text{m}$ (Nominal $0.15\ \mu\text{m}$)
      - Code 2 (Rainbow): $0.30 - 5.00\ \mu\text{m}$ (Nominal $2.5\ \mu\text{m}$)
      - Code 3 (Metallic): $5.00 - 50.0\ \mu\text{m}$ (Nominal $25\ \mu\text{m}$)
      - Code 4 (Discontinuous True Oil): $50.0 - 200.0\ \mu\text{m}$ (Nominal $100\ \mu\text{m}$)
      - Code 5 (Continuous True Oil): $> 200.0\ \mu\text{m}$ (Nominal $300\ \mu\text{m}$)
    - Map SAR damping ratio and optical reflectance contrast to BAOAC code per sub-polygon segment.
    - Calculate integrated volume:
      $$V_{total} = \sum_{i=1}^5 A_i \cdot d_i \quad (\text{m}^3)$$
- **Deliverables:** `backend/services/tier2_morphometry/thickness_profiler.py`, unit test in `tests/test_thickness_profiler.py`.
- **Verification:** Run `pytest tests/test_thickness_profiler.py` verifying volume calculation across test segments.

---

### [x] TASK-016: Tier 2 Celery Pipeline Task & Integration Test (Completed)
- **Status:** Completed
- **Domain:** Tier 2 — Pipeline Integration
- **Prerequisites:** TASK-015
- **Objective:** Wrap morphometry, age inversion, and thickness profiling into an idempotent Celery task updating `SlickCharacterization`.
- **Implementation Details:**
  - Create `backend/workers/tasks/tier2_tasks.py`:
    - Define task `run_tier2_characterization(case_id: str)`.
    - Fetch `SlickDetection` from PostgreSQL.
    - Execute morphometry, Fay spreading age inversion, and thickness profiling.
    - Persist `SlickCharacterization` record in PostgreSQL (`perimeter_m`, `principal_axis_deg`, `baoac_code`, `estimated_volume_m3`, `t_age_hours`, `age_confidence`).
    - Advance case status to `hindcasting`.
    - Publish progress to Redis channel `cases:{case_id}:progress`.
- **Deliverables:** `backend/workers/tasks/tier2_tasks.py`, integration test `tests/test_tier2_pipeline.py`.
- **Verification:** Run integration test executing Tier 2 against database with existing Tier 1 output; verify record creation in `slick_characterizations`.

---

## Phase 2: Tier 3 — Hydrodynamic Advection-Diffusion Modeling

### [x] TASK-017: Met-Ocean Data Ingestion Adapter (CMEMS GLO12 Currents & ERA5 Winds) (Completed)
- **Status:** Completed
- **Domain:** Tier 3 — Environmental Forcing
- **Prerequisites:** TASK-016
- **Objective:** Implement data adapter fetching ocean surface currents (CMEMS GLO12) and surface wind fields (ERA5/GFS) with local NetCDF caching and synthetic generator fallback.
- **Implementation Details:**
  - Create `backend/services/data_adapters/metocean_adapter.py`:
    - CMEMS adapter using Copernicus Marine Toolbox / `xarray` to query zonal and meridional surface velocities $(u_{curr}, v_{curr})$.
    - ECMWF ERA5 / GFS adapter using `cdsapi` / `cfgrib` to query 10-meter wind components $(u_{10}, v_{10})$.
    - Spatial-temporal subsetting for the case bounding box and time span $[t_{obs} - t_{age} - 12\text{h}, t_{obs} + 72\text{h}]$.
    - Fallback mechanism: if CMEMS/ERA5 API is unavailable, load local cached NetCDF from `data/metocean/` or generate synthetic field; flag `data_source = "synthetic"`.
- **Deliverables:** `backend/services/data_adapters/metocean_adapter.py`, unit test in `tests/test_metocean_adapter.py`.
- **Verification:** Run `pytest tests/test_metocean_adapter.py` verifying subsetting, interpolation, and fallback execution.

---

### [x] TASK-018: Total Drift Velocity Engine (Currents + Ekman Wind Drift + Stokes Wave Drift) (Completed)
- **Status:** Completed
- **Domain:** Tier 3 — Hydrodynamic Physics
- **Prerequisites:** TASK-017
- **Objective:** Implement the three-component drift velocity vector composition with Coriolis deflection.
- **Implementation Details:**
  - Create `backend/services/tier3_hindcast/drift_physics.py`:
    - Formulate total drift velocity:
      $$\vec{u}_{drift} = \vec{u}_{current} + c_w \mathbf{R}(\theta_w) \vec{u}_{wind} + \vec{u}_{stokes}$$
    - Wind drift factor: $c_w \in [0.025, 0.035]$ (nominal $0.030$, $3\%$).
    - Wind deflection rotation matrix $\mathbf{R}(\theta_w)$:
      - Northern Hemisphere: $\theta_w \in [+10^\circ, +15^\circ]$ (clockwise / right of wind).
      - Southern Hemisphere: $\theta_w \in [-10^\circ, -15^\circ]$ (counter-clockwise / left of wind).
    - Stokes wave drift estimation from wind speed if wave spectra not directly supplied: $\vec{u}_{stokes} \approx 0.012 \vec{u}_{wind}$.
    - Interpolator returning interpolated $\vec{u}_{drift}(x, y, t)$ at arbitrary coordinates and timestamps.
- **Deliverables:** `backend/services/tier3_hindcast/drift_physics.py`, unit test in `tests/test_drift_physics.py`.
- **Verification:** Run `pytest tests/test_drift_physics.py` with known current and wind vectors; verify deflection angle and magnitude accuracy.

---

### [x] TASK-019: OpenDrift / OpenOil Backward Lagrangian Hindcasting Runner (Sub-Module 3A) (Completed)
- **Status:** Completed
- **Domain:** Tier 3 — Backward Lagrangian Advection
- **Prerequisites:** TASK-018
- **Objective:** Wrap OpenDrift/OpenOil to seed $\ge 10,000$ numerical particles across the slick polygon and simulate backward advection to the release window.
- **Implementation Details:**
  - Create `backend/services/tier3_hindcast/hindcast_runner.py`:
    - Initialize OpenDrift `OpenOil` or custom `LagrangianParticleTracker` engine.
    - Uniformly seed $N = 10,000$ particles across the `SlickDetection` PostGIS polygon using random rejection sampling.
    - Set negative time step: $\Delta t = -15\text{ minutes}$.
    - Advect particles backward in time from $t_{obs}$ to $t_{obs} - t_{age}$.
    - Account for horizontal turbulent diffusion:
      $$\Delta \vec{r}_{diff} = \sqrt{2 K_h \Delta t} \cdot \vec{\mathcal{N}}(0, 1) \quad (K_h \approx 1.0\text{ to }10.0\text{ m}^2/\text{s})$$
    - Record particle positions $(lat, lon, t)$ at 15-minute intervals.
- **Deliverables:** `backend/services/tier3_hindcast/hindcast_runner.py`, unit test in `tests/test_hindcast_runner.py`.
- **Verification:** Run `pytest tests/test_hindcast_runner.py` verifying reverse trajectory convergence on benchmark synthetic dataset.

---

### [x] TASK-020: Origin Density Estimation (2D Gaussian Kernel Density Estimation) (Completed)
- **Status:** Completed
- **Domain:** Tier 3 — Probabilistic Origin
- **Prerequisites:** TASK-019
- **Objective:** Estimate origin probability centroid ($\mu_p$), spatial covariance matrix ($\Sigma_p$), and release time window from the backward particle ensemble.
- **Implementation Details:**
  - Create `backend/services/tier3_hindcast/origin_estimator.py`:
    - Extract particle ensemble slice at estimated release time $t_{release} = t_{obs} - t_{age}$.
    - Perform 2D Gaussian Kernel Density Estimation (KDE) using `scipy.stats.gaussian_kde` with Scott's rule bandwidth.
    - Calculate spatial centroid $\mu_p = [\bar{lat}, \bar{lon}]$ of maximum density.
    - Compute $2\times 2$ spatial covariance matrix $\Sigma_p$:
      $$\Sigma_p = \begin{bmatrix} \sigma_{lat}^2 & \sigma_{lat, lon} \\ \sigma_{lat, lon} & \sigma_{lon}^2 \end{bmatrix}$$
    - Generate $1\sigma, 2\sigma, 3\sigma$ (39%, 86%, 98.9%) confidence error ellipse polygons as GeoJSON.
    - Compute origin uncertainty region area ($\text{km}^2$) and confidence percentage.
- **Deliverables:** `backend/services/tier3_hindcast/origin_estimator.py`, unit test in `tests/test_origin_estimator.py`.
- **Verification:** Run `pytest tests/test_origin_estimator.py` validating $\mu_p$, $\Sigma_p$ and error ellipse generation.

---

### [x] TASK-021: Forward Trajectory Forecasting & Mackay Weathering (Sub-Module 3B) (Completed)
- **Status:** Completed
- **Domain:** Tier 3 — Forward Modeling & Impact
- **Prerequisites:** TASK-020
- **Objective:** Implement forward $+72\text{h}$ trajectory forecasting incorporating Mackay evaporative loss, emulsification, and shoreline beaching detection.
- **Implementation Details:**
  - Create `backend/services/tier3_hindcast/forecast_runner.py`:
    - Forward advection: seed particles across current slick polygon, advect forward with $\Delta t = +15\text{ minutes}$ over $[t_{obs}, t_{obs} + 72\text{h}]$.
    - Implement Mackay evaporative loss:
      $$F_{evap} = \left(\frac{T_B}{T}\right) \ln\left(1 + \frac{K_{evap} t}{V_0}\right)$$
    - Implement water-in-oil emulsification equation for viscosity increase.
    - Shoreline interaction: intersect particle trajectories with Global Self-consistent Hierarchical High-resolution Geography (GSHHG) coastline polygons. Particles within $50\text{ m}$ of coast are marked `beached`.
    - Compute Estimated Time of Beaching (ETB), Coastal Vulnerability Index (CVI), and beached volume ($m^3$).
- **Deliverables:** `backend/services/tier3_hindcast/forecast_runner.py`, unit test in `tests/test_forecast_runner.py`.
- **Verification:** Run `pytest tests/test_forecast_runner.py` asserting beaching detection on simulated coastal impact test case.

---

### [x] TASK-022: Tier 3 Celery Pipeline Task, Particle Persistence & Integration Test (Completed)
- **Status:** Completed
- **Domain:** Tier 3 — Pipeline Integration
- **Prerequisites:** TASK-021
- **Objective:** Wrap hindcast and forecast into a Celery task that stores origin estimates in Postgres and streams particle trajectories to TimescaleDB.
- **Implementation Details:**
  - Create `backend/workers/tasks/tier3_tasks.py`:
    - Define task `run_tier3_hindcast(case_id: str)`.
    - Retrieve slick characterization and detection.
    - Execute backward Lagrangian hindcast and forward forecast.
    - Bulk insert particle trajectory snapshots into `particle_trajectories` TimescaleDB hypertable for UI replay.
    - Persist `OriginEstimate` and `ForwardForecast` records in PostgreSQL.
    - Advance case status to `correlating`.
    - Publish progress to Redis channel `cases:{case_id}:progress`.
- **Deliverables:** `backend/workers/tasks/tier3_tasks.py`, integration test `tests/test_tier3_pipeline.py`.
- **Verification:** Execute integration test; verify TimescaleDB contains inserted particle records and `origin_estimates` record is populated with covariance matrix.

---

## Phase 3: Tier 4 — AIS Spatio-Temporal Correlation & Attribution Scoring

### [x] TASK-023: Historical AIS Data Ingestion Adapter & Spatio-Temporal Spatial Query (Completed)
- **Status:** Completed
- **Domain:** Tier 4 — AIS Data Ingestion
- **Prerequisites:** TASK-022
- **Objective:** Build AIS ingestion adapter querying AIS feeds (MarineCadastre / AISHub) within the origin spatio-temporal window, with synthetic fallback.
- **Implementation Details:**
  - Create `backend/services/data_adapters/ais_adapter.py`:
    - Spatial query: filter vessels within bounding box defined by $\mu_p \pm 3 \Sigma_p$ (expanded by search buffer).
    - Temporal query: filter reports within $[t_{obs} - t_{age} - 3\text{h}, t_{obs} + 1\text{h}]$.
    - Parse AIS Messages: Type 1, 2, 3 (Position Reports: MMSI, SOG, COG, lat, lon, heading, timestamp) and Type 5 (Static & Voyage: IMO, name, callsign, vessel_type, dimensions, destination).
    - Bulk load ingested points into TimescaleDB `ais_tracks` hypertable.
    - Fallback: if external AIS API unavailable, load from `data/synthetic/` and set `data_source = "synthetic"`.
- **Deliverables:** `backend/services/data_adapters/ais_adapter.py`, unit test in `tests/test_ais_adapter.py`.
- **Verification:** Run `pytest tests/test_ais_adapter.py` asserting correct parsing, spatial-temporal bounding filtering, and fallback loading.

---

### [x] TASK-024: Vessel Kinematic Trajectory Reconstruction (Cubic-Spline Interpolation) (Completed)
- **Domain:** Tier 4 — Trajectory Interpolation
- **Prerequisites:** TASK-023
- **Objective:** Reconstruct continuous vessel trajectories from discrete AIS reports using cubic-spline interpolation.
- **Implementation Details:**
  - Create `backend/services/tier4_correlation/trajectory_reconstruction.py`:
    - Group discrete AIS points by MMSI.
    - Validate temporal monotonicity and discard duplicated timestamps.
    - Apply Catmull-Rom or cubic spline interpolation (`scipy.interpolate.CubicSpline`) in UTM space to produce continuous coordinates, velocity vectors, and heading angles at 1-minute uniform intervals.
    - Compute closest point of approach (CPA) between vessel trajectory and estimated origin centroid $\mu_p$.
    - Calculate timestamp $t_{CPA}$ and spatial distance $d_{CPA}$.
- **Deliverables:** `backend/services/tier4_correlation/trajectory_reconstruction.py`, unit test in `tests/test_trajectory_reconstruction.py`.
- **Verification:** Run `pytest tests/test_trajectory_reconstruction.py` comparing discrete vs continuous interpolated trajectories.

---

### [x] TASK-025: Vessel Kinematic Anomaly Detector & Transponder Dark Gap Flagger (FR-19, Rule 4) (Completed)
- **Domain:** Tier 4 — Anomaly Detection
- **Prerequisites:** TASK-024
- **Objective:** Detect behavioral anomalies (speed drops into discharge band, abnormal course turns) and flag transponder gaps ($A_{dark}$).
- **Implementation Details:**
  - Create `backend/services/tier4_correlation/anomaly_detector.py`:
    - Speed drop anomaly ($A_{speed}$): flag vessels slowing down into the characteristic bilge/ballast dumping speed band ($4\text{ to }8\text{ knots}$), while operating in open transit lanes:
      $$A_{speed} = \begin{cases} 1.0 & \text{if } 4 \le v \le 8\text{ kts} \\ \max(0, 1 - \frac{|v - 6|}{6}) & \text{otherwise} \end{cases}$$
    - Course deviation anomaly ($A_{course}$): flag sudden zig-zag or loitering turns ($> 45^\circ$ course deviation from general traffic separation lane).
    - Dark ship / Transponder gap detection ($A_{dark}$): per FR-19 and Rule 4, inspect time deltas $\Delta t_{AIS}$ between consecutive reports. If $\Delta t_{AIS} > 30\text{ minutes}$ within the bounding zone:
      - Set `ais_coverage = "dark_gap"`.
      - Compute gap duration and extrapolate unobserved path.
    - Non-AIS vessel detection integration (P4): flag radar/optical detections with no corresponding AIS transponder as `ais_coverage = "non_ais_unknown"`.
- **Deliverables:** `backend/services/tier4_correlation/anomaly_detector.py`, unit test in `tests/test_anomaly_detector.py`.
- **Verification:** Run `pytest tests/test_anomaly_detector.py` validating that synthetic Vessel D triggers `dark_gap` flag and Vessel A triggers $A_{speed} = 1.0$.

---

### [x] TASK-026: Analytic Hierarchy Process (AHP) Weight Manager & Consistency Verifier (Rule 7) (Completed)
- **Domain:** Tier 4 — Multi-Criteria Decision Analysis
- **Prerequisites:** TASK-025
- **Objective:** Implement AHP matrix weight derivation, consistency ratio check ($CR < 0.10$), and configuration persistence.
- **Implementation Details:**
  - Create `backend/services/tier4_correlation/ahp_manager.py`:
    - Define pairwise comparison matrix for criteria $[C_{spatial}, C_{temporal}, C_{kinematic}, C_{anomaly}, C_{type}]$:
      $$\mathbf{A} = \begin{bmatrix}
      1 & 2 & 3 & 2 & 4 \\
      1/2 & 1 & 2 & 1 & 3 \\
      1/3 & 1/2 & 1 & 1/2 & 2 \\
      1/2 & 1 & 2 & 1 & 3 \\
      1/4 & 1/3 & 1/2 & 1/3 & 1
      \end{bmatrix}$$
    - Compute principal eigenvector and normalized weights:
      $$\vec{w} = [0.30, 0.25, 0.15, 0.20, 0.10]$$
    - Calculate maximum eigenvalue $\lambda_{max}$, Consistency Index $CI = (\lambda_{max} - n)/(n - 1)$, and Consistency Ratio $CR = CI / RI$ (where $RI_{n=5} = 1.12$).
    - Assert strictly $CR = 0.0094 < 0.10$. Raise exception if consistency criterion is violated.
    - Expose method `get_ahp_config()` returning matrix, weights, and $CR$ for `GET /ahp-config` endpoint (Rule 7).
- **Deliverables:** `backend/services/tier4_correlation/ahp_manager.py`, unit test in `tests/test_ahp_manager.py`.
- **Verification:** Run `pytest tests/test_ahp_manager.py` verifying $CR < 0.10$ and exact weight vector derivation.

---

### [x] TASK-027: Multi-Criteria Attribution Scoring Engine ($S_{culprit}$) (Completed)
- **Domain:** Tier 4 — Attribution Scoring
- **Prerequisites:** TASK-026
- **Objective:** Compute the 5 normalized sub-scores and AHP-weighted composite attribution score ($S_{culprit} \in [0, 100]$) per candidate vessel.
- **Implementation Details:**
  - Create `backend/services/tier4_correlation/scoring_engine.py`:
    - Spatial sub-score ($S_{spatial}$): Mahalanobis distance to origin centroid:
      $$D_M = \sqrt{(\vec{x}_{CPA} - \vec{\mu}_p)^T \Sigma_p^{-1} (\vec{x}_{CPA} - \vec{\mu}_p)}, \quad S_{spatial} = 100 \cdot \exp\left(-\frac{1}{2} D_M^2\right)$$
    - Temporal sub-score ($S_{temporal}$): exponential decay from closest approach to estimated release time ($\tau = 1.5\text{ hours}$):
      $$S_{temporal} = 100 \cdot \exp\left(-\frac{|t_{CPA} - t_{release}|}{\tau}\right)$$
    - Kinematic alignment sub-score ($S_{kinematic}$): cosine similarity between vessel heading $\theta_{vessel}$ and slick orientation $\theta_{slick}$:
      $$S_{kinematic} = 100 \cdot |\cos(\theta_{vessel} - \theta_{slick})| \times f(v)$$
    - Behavioral anomaly sub-score ($S_{anomaly}$):
      $$S_{anomaly} = 100 \cdot (0.4 A_{speed} + 0.3 A_{course} + 0.3 A_{dark})$$
    - Vessel type prior sub-score ($S_{type}$): Tanker $100$, Cargo $75$, Offshore $50$, Fishing $30$, Pleasure $5$.
    - Composite score:
      $$S_{culprit} = \sum_{i=1}^5 w_i S_i = 0.30 S_{spatial} + 0.25 S_{temporal} + 0.15 S_{kinematic} + 0.20 S_{anomaly} + 0.10 S_{type}$$
    - Enforce Product Rule 2: Sub-scores and evidence references must be returned as discrete stored fields, never aggregated away or calculated client-side.
- **Deliverables:** `backend/services/tier4_correlation/scoring_engine.py`, unit test in `tests/test_scoring_engine.py`.
- **Verification:** Run `pytest tests/test_scoring_engine.py` verifying mathematical calculations and sub-score preservation.

---

### [x] TASK-028: Tier 4 Celery Pipeline Task & Integration Test (Completed)
- **Domain:** Tier 4 — Pipeline Integration
- **Prerequisites:** TASK-027
- **Objective:** Wrap AIS ingestion, trajectory reconstruction, anomaly detection, and scoring into a Celery task persisting `VesselCandidate` rows.
- **Implementation Details:**
  - Create `backend/workers/tasks/tier4_tasks.py`:
    - Define task `run_tier4_correlation(case_id: str)`.
    - Fetch origin estimate from PostgreSQL.
    - Ingest AIS, reconstruct trajectories, compute anomalies, and calculate $S_{culprit}$.
    - Bulk persist ranked candidate vessels to `vessel_candidates` table with sub-scores, anomaly flags, and AIS coverage status.
    - Advance case status to `scoring`.
    - Publish progress to Redis channel `cases:{case_id}:progress`.
- **Deliverables:** `backend/workers/tasks/tier4_tasks.py`, integration test `tests/test_tier4_pipeline.py`.
- **Verification:** Run integration test verifying candidate vessels are persisted with correct sub-scores and rankings.

---

## Phase 4: Forensic Explainability, Counterfactual & Dossier Services

### [x] TASK-029: "Why This Vessel?" Structured Evidence Composer (Architecture 4.5, Feature 1) (Completed)
- **Domain:** Explainability Service
- **Prerequisites:** TASK-028
- **Objective:** Build service generating structured, human-readable forensic rationales for any candidate vessel based on persisted sub-scores.
- **Implementation Details:**
  - Create `backend/services/explainability/why_this_vessel.py`:
    - Read candidate vessel's persisted sub-scores and evidence references.
    - Generate breakdown items:
      - Spatial: Mahalanobis distance, physical distance in km, whether inside $1\sigma, 2\sigma, 3\sigma$ error ellipse.
      - Temporal: time delta $|t_{CPA} - t_{release}|$ in minutes, decay factor.
      - Kinematic: heading difference $|\theta_{vessel} - \theta_{slick}|$ in degrees, vessel speed at CPA.
      - Anomaly: explicit breakdown of speed loitering or dark transponder gap intervals.
      - Type: vessel category justification and IMO registry reference.
    - Assemble radar chart / bar chart payload for frontend visualization.
    - Enforce Rule 6: strictly ensure output copy contains zero banned terms.
- **Deliverables:** `backend/services/explainability/why_this_vessel.py`, unit test in `tests/test_why_this_vessel.py`.
- **Verification:** Run `pytest tests/test_why_this_vessel.py` verifying explanation generation and absence of banned words.

---

### [x] TASK-030: Alternative Explanation Engine (FR-18, Rule 5, Feature 7) (Completed)
- **Domain:** Explainability Service
- **Prerequisites:** TASK-029
- **Objective:** Score non-vessel hypotheses (natural seep, imaging artifact, non-AIS vessel) to guarantee balanced forensic evaluation.
- **Implementation Details:**
  - Create `backend/services/explainability/alternative_engine.py`:
    - Load natural seep geospatial catalog (`data/geospatial/natural_seeps.geojson`).
    - Compute proximity of slick centroid to known natural hydrocarbon seeps ($d_{seep} < 5\text{ km} \implies$ high seep hypothesis score).
    - Evaluate imaging artifact score based on Tier 1 lookalike risk and radar incidence angle.
    - Evaluate unlisted/non-AIS dark vessel hypothesis based on SAR wake detection and AIS traffic gaps.
    - Enforce Product Rule 5: every case must persist at least one alternative explanation hypothesis into `alternative_explanations` table before case is marked `ready`.
- **Deliverables:** `backend/services/explainability/alternative_engine.py`, unit test in `tests/test_alternative_engine.py`.
- **Verification:** Run `pytest tests/test_alternative_engine.py` validating that alternative hypotheses are always produced even when vessel attribution is high.

---

### [x] TASK-031: Counterfactual Forward Simulation Engine (Feature 2 / D2) (Completed)
- **Domain:** Forensic Verification
- **Prerequisites:** TASK-030
- **Objective:** Implement counterfactual forward simulation: re-simulate oil release from a suspect vessel's actual track to evaluate visual and spatial similarity with the observed slick.
- **Implementation Details:**
  - Create `backend/services/explainability/counterfactual_simulator.py`:
    - For candidate vessel $MMSI_k$, seed 5,000 particles at position $\vec{x}_{vessel}(t_{release})$.
    - Run forward Lagrangian simulation from $t_{release}$ to $t_{obs}$ using recorded met-ocean currents.
    - Compute geometric intersection-over-union (IoU) and Hausdorff distance between simulated particle cloud at $t_{obs}$ and observed `SlickDetection` polygon:
      $$S_{counterfactual} = \operatorname{IoU}(\text{SimulatedCloud}(t_{obs}), \text{ObservedSlick})$$
    - Return counterfactual trajectory and similarity percentage.
- **Deliverables:** `backend/services/explainability/counterfactual_simulator.py`, unit test in `tests/test_counterfactual_simulator.py`.
- **Verification:** Run `pytest tests/test_counterfactual_simulator.py` verifying IoU computation between counterfactual cloud and target polygon.

---

### [x] TASK-032: Evidence Timeline & Node-Edge Graph Builders (Features 8 & 11) (Completed)
- **Domain:** Explainability Service
- **Prerequisites:** TASK-031
- **Objective:** Construct chronological event reconstruction timeline and interactive node-edge graph data structures.
- **Implementation Details:**
  - Create `backend/services/explainability/evidence_graph.py`:
    - Evidence Timeline: chronological array of verified events:
      1. Satellite acquisition timestamp & sensor details.
      2. Estimated oil release window $[t_{start}, t_{end}]$.
      3. Candidate vessel entry into bounding zone.
      4. Anomaly trigger (e.g., speed drop to 6 kts or dark gap start).
      5. Closest approach to origin centroid $\mu_p$.
      6. Slick drift and spreading progression.
    - Evidence Graph: nodes (Observation, Slick, Origin Region, Time Window, AIS Transponder Track, Vessel Entity, Alternative Hypothesis) and directed edges (e.g., `DRIFTED_FROM`, `CORRELATED_WITH`, `FLAGGED_BY`).
- **Deliverables:** `backend/services/explainability/evidence_graph.py`, unit test in `tests/test_evidence_graph.py`.
- **Verification:** Run `pytest tests/test_evidence_graph.py` verifying graph topology and acyclic structure.

---

### [x] TASK-033: Replay State Server (Feature 4 / D4) (Completed)
- **Domain:** Backend API / Scrubber Support
- **Prerequisites:** TASK-032
- **Objective:** Implement time-slice query engine serving particle and vessel positions for the frontend time-scrubber.
- **Implementation Details:**
  - Create `backend/services/explainability/replay_service.py`:
    - Query `particle_trajectories` and `ais_tracks` from TimescaleDB at arbitrary requested timestamp $t$.
    - Interpolate particle positions and vessel positions between 15-minute keyframes.
    - Dynamically compute evolving $S_{culprit}(t)$ as vessel moves closer to / further from origin cloud.
    - Expose function `get_replay_state(case_id: str, timestamp: datetime)`.
- **Deliverables:** `backend/services/explainability/replay_service.py`, unit test in `tests/test_replay_service.py`.
- **Verification:** Run `pytest tests/test_replay_service.py` verifying state interpolation at intermediate timestamps.

---

### [x] TASK-034: Automated Forensic PDF Legal Dossier Generator with Cryptographic Chain-of-Custody (FR-20, C13) (Completed)
- **Domain:** Legal Dossier Service
- **Prerequisites:** TASK-033
- **Objective:** Implement PDF dossier generator with WeasyPrint/ReportLab, embedding SAR chips, drift skill scores, vessel rankings, and SHA-256 integrity hash.
- **Implementation Details:**
  - Create `backend/services/dossier/dossier_generator.py`:
    - HTML/CSS dossier template styled according to `DESIGN.md` (clean typography, official maritime agency header, structured tables).
    - Sections:
      1. Executive Incident Summary & Satellite Acquisition Metadata.
      2. Slick Morphometry, Volume & Spreading Aging Inversion.
      3. Hydrodynamic Hindcast Origin Cloud & Environmental Forcing Summary.
      4. Ranked Candidate Suspects Table with full 5-subscore breakdown and confidence.
      5. Alternative Explanations Evaluated (natural seeps, artifacts).
      6. Mandatory Responsible-Use Disclaimer & Legal Notice (FR-20).
    - Compute SHA-256 cryptographic digest of case inputs and results; stamp hash and verification QR on dossier footer for chain-of-custody.
    - Render to PDF via WeasyPrint / ReportLab and upload to MinIO `aegis-storage/dossiers/`.
    - Persist `Dossier` record in PostgreSQL.
    - Run `scripts/lint_banned_terms.py` across output HTML/PDF text to verify 0 banned words.
- **Deliverables:** `backend/services/dossier/dossier_generator.py`, `backend/templates/dossier_template.html`, unit test in `tests/test_dossier_generator.py`.
- **Verification:** Run `pytest tests/test_dossier_generator.py`; verify valid PDF generation and verify SHA-256 checksum in test fixture.

---

## Phase 5: API Gateway, Case Orchestration & Security

### [x] TASK-035: FastAPI Application Scaffolding, Middleware & RBAC Security (Architecture 10) (Completed)
- **Domain:** API Gateway / Security
- **Prerequisites:** TASK-034
- **Objective:** Establish the FastAPI core application with JWT authentication, CORS, exception handling, and Role-Based Access Control (RBAC).
- **Implementation Details:**
  - Create `backend/app/main.py` and `backend/core/security.py`:
    - Configure CORS for frontend origin.
    - JWT bearer token validation supporting OIDC claims.
    - RBAC dependency `require_roles(["investigator", "analyst", "legal_reviewer", "admin"])`:
      - `investigator`: full case creation, rerun, what-if, dossier export.
      - `analyst`: case viewing, what-if, replay.
      - `legal_reviewer`: read-only case view, dossier review and download.
      - `admin`: user management, system audit logs, AHP matrix configuration.
    - Global exception handlers mapping internal domain errors to RFC 7807 problem details.
- **Deliverables:** `backend/app/main.py`, `backend/core/security.py`, unit test in `tests/test_security.py`.
- **Verification:** Run `pytest tests/test_security.py` testing authorized and unauthorized requests against protected routes.

---

### [x] TASK-036: Complete REST & WebSocket API Endpoints (Architecture Section 7) (Completed)
- **Domain:** API Gateway
- **Prerequisites:** TASK-035
- **Objective:** Implement all REST endpoints and WebSocket channels defined in Architecture Document Section 7.
- **Implementation Details:**
  - Implement routes in `backend/app/api/`:
    - `POST /cases`: Create new case from scene ref or file upload.
    - `GET /cases/{id}`: Fetch complete case aggregate with status and tier summaries.
    - `GET /cases/{id}/vessels`: Return ranked `VesselCandidate` list.
    - `GET /cases/{id}/vessels/{mmsi}/explain`: Why-This-Vessel breakdown.
    - `POST /cases/{id}/vessels/{mmsi}/counterfactual`: Trigger counterfactual run.
    - `GET /cases/{id}/alternatives`: Return alternative explanation scores.
    - `GET /cases/{id}/replay`: Return particle and vessel positions for given timestamp `t`.
    - `GET /cases/{id}/evidence-graph`: Return node-edge graph payload.
    - `POST /cases/{id}/dossier`: Trigger dossier generation.
    - `GET /cases/{id}/dossier`: Download generated PDF.
    - `GET /ahp-config`: Return active AHP pairwise matrix, weights, and $CR$ (Rule 7).
    - `WS /cases/{id}/status`: WebSocket connection streaming live case-state updates.
- **Deliverables:** `backend/app/api/*.py`, endpoint tests in `tests/test_api_endpoints.py`.
- **Verification:** Run `pytest tests/test_api_endpoints.py` testing all API routes with mock database session.

---

### [x] TASK-037: "What-If" Scenario Simulation Engine & Partial Task Re-Execution (P3) (Completed)
- **Domain:** Backend Case Orchestration
- **Prerequisites:** TASK-036
- **Objective:** Implement `POST /cases/{id}/whatif` to re-execute hindcasting and attribution under overridden parameters without re-running Tier 1 segmentation.
- **Implementation Details:**
  - Create `backend/services/orchestration/what_if_service.py`:
    - Accept overrides: adjusted `t_age` window, wind drift factor $c_w$, horizontal diffusivity $K_h$, search radius, or custom AHP weights.
    - Leverage Celery task idempotency to trigger only Tier 3, Tier 4, and Explainability tasks (`hindcast -> correlate -> explain`).
    - Cache scenario runs under child scenario keys so user can compare baseline vs what-if outcomes.
- **Deliverables:** `backend/services/orchestration/what_if_service.py`, unit test in `tests/test_what_if.py`.
- **Verification:** Run `pytest tests/test_what_if.py` verifying that modifying $t_{age}$ re-executes Tiers 3 & 4 while preserving Tier 1 segmentation outputs.

---

### [x] TASK-038: Audit Logging System (rules.md Section 5) (Completed)
- **Domain:** Security / Auditability
- **Prerequisites:** TASK-037
- **Objective:** Build audit logging middleware recording every case mutation, parameter override, and dossier export.
- **Implementation Details:**
  - Create `backend/core/audit.py`:
    - Middleware intercepting mutating HTTP requests (`POST`, `PUT`, `DELETE`).
    - Extract authenticated user ID, client IP, action name, target case ID, and request payload digest.
    - Write immutable record to `audit_logs` table in PostgreSQL.
    - Expose `GET /admin/audit-logs` restricted strictly to `admin` role.
- **Deliverables:** `backend/core/audit.py`, unit test in `tests/test_audit.py`.
- **Verification:** Run `pytest tests/test_audit.py` confirming audit log entry creation upon case modification.

---

## Phase 6: Frontend — Geospatial War Room & Interactive Forensic UI

### TASK-039: Next.js 15 App Router Scaffolding, Design System Tokens & Tailwind Configuration
- **Domain:** Frontend Infrastructure
- **Prerequisites:** TASK-038
- **Objective:** Initialize the Next.js 15 App Router frontend and configure the theme, fonts, and CSS custom properties strictly adhering to `DESIGN.md`.
- **Implementation Details:**
  - Set up Next.js 15 with TypeScript strict mode in `frontend/`.
  - Configure TailwindCSS in `frontend/tailwind.config.ts`:
    - Brand Colors:
      - `brand-green`: `#00ed64`, `brand-green-dark`: `#00684a`, `brand-green-mid`: `#00a35c`, `brand-green-soft`: `#c3f0d2`
      - `brand-teal-deep`: `#001e2b`, `brand-teal`: `#003d4f`, `brand-teal-mid`: `#00684a`
      - Canvas & Surfaces: `canvas-dark`: `#001e2b`, `surface`: `#f9fbfa`, `surface-soft`: `#f4f7f6`
      - Hairlines: `hairline`: `#e1e5e8`, `hairline-dark`: `#1c2d38`
      - Semantic accents: `accent-purple`: `#7b3ff2`, `accent-orange`: `#fa6e39`, `accent-blue`: `#3d4f9f`
    - Typography tokens matching `DESIGN.md` (Euclid Circular A / Inter sans for UI, JetBrains Mono for coordinates/MMSI/timestamps).
    - Elevation, border-radius (`border-radius-sm`: 4px, `border-radius-md`: 8px, `border-radius-lg`: 12px, `pill`: 9999px).
  - Install and initialize shadcn UI primitives (Button, Card, Dialog, Slider, Tabs, Badge, Tooltip).
- **Deliverables:** `frontend/package.json`, `frontend/tailwind.config.ts`, `frontend/src/app/globals.css`.
- **Verification:** Run `npm run build` inside `frontend/` verifying zero compile or lint errors.

---

### TASK-040: OpenAPI Type Generation & Typed API Client
- **Domain:** Frontend Core / Data Contracts
- **Prerequisites:** TASK-039
- **Objective:** Automatically generate TypeScript interfaces from FastAPI's OpenAPI specification to guarantee end-to-end contract type safety.
- **Implementation Details:**
  - Set up `openapi-typescript` in `frontend/package.json`.
  - Create script `scripts/generate_types.sh` querying FastAPI `/openapi.json` and generating `frontend/src/types/api.ts`.
  - Create typed HTTP client `frontend/src/lib/api-client.ts` using native `fetch` with JWT token injection and error handling.
  - Implement WebSocket client `frontend/src/lib/websocket-client.ts` with automatic reconnection for `/cases/{id}/status`.
- **Deliverables:** `frontend/src/types/api.ts`, `frontend/src/lib/api-client.ts`, `frontend/src/lib/websocket-client.ts`.
- **Verification:** Run `bash scripts/generate_types.sh` against the running backend; verify generated types match Pydantic schemas.

---

### TASK-041: MapLibre GL Base Map Container with Dark Marine Canvas
- **Domain:** Frontend Geospatial
- **Prerequisites:** TASK-040
- **Objective:** Build the interactive base map component styled with dark marine cartography conforming to `DESIGN.md`.
- **Implementation Details:**
  - Create `frontend/src/components/map/MarineMap.tsx` using `maplibre-gl`:
    - Base vector style: dark nautical theme (`#001e2b` deep ocean canvas, subtle bathymetry contour lines, muted coastal boundaries).
    - Map controls: zoom, pitch, bearing reset, scale indicator in nautical miles ($NM$) and kilometers.
    - Viewport state management with automatic fitting to case bounding box.
    - Support layer toggling: Bathymetry, EEZ Boundaries, Shipping Lanes (TSS), Marine Protected Areas.
- **Deliverables:** `frontend/src/components/map/MarineMap.tsx`.
- **Verification:** Render component in browser; verify map loads vector tiles smoothly and controls function.

---

### TASK-042: deck.gl High-Performance Data Layers (Particles & AIS Trips)
- **Domain:** Frontend Geospatial / High Performance
- **Prerequisites:** TASK-041
- **Objective:** Integrate deck.gl overlay onto MapLibre GL to render 10,000+ advection particles and vessel tracks at 60 FPS.
- **Implementation Details:**
  - Create `frontend/src/components/map/DeckOverlay.tsx`:
    - `GeoJsonLayer`: render SAR slick polygon and origin error ellipses ($1\sigma, 2\sigma, 3\sigma$).
    - `ScatterplotLayer` / `PointCloudLayer`: render $\ge 10,000$ advected particles colored by density / age.
    - `TripsLayer`: render animated AIS vessel trajectories with fading wake trails.
    - Custom shader optimization ensuring stable 60 FPS under 10,000 active particles (NFR verification).
- **Deliverables:** `frontend/src/components/map/DeckOverlay.tsx`.
- **Verification:** Mount component with synthetic 10,000-particle dataset; verify browser FPS counter remains $\ge 55$ FPS during pan/zoom.

---

### TASK-043: Interactive Replay Time-Scrubber & Playback Controls (D4)
- **Domain:** Frontend UI / Investigation Replay
- **Prerequisites:** TASK-042
- **Objective:** Build the temporal playback scrubber driving particle reverse convergence and vessel track advancement.
- **Implementation Details:**
  - Create `frontend/src/components/investigation/TimeScrubber.tsx`:
    - Time slider spanning $[t_{obs} - t_{age}, t_{obs}]$.
    - Play / Pause / Reverse buttons, speed multiplier selector ($1\times, 5\times, 10\times, 30\times$).
    - Display current simulation timestamp $t$ and relative elapsed time $\Delta t$.
    - Drive `DeckOverlay` particle timestamps and sync with `VesselRankingList` live ranking updates.
- **Deliverables:** `frontend/src/components/investigation/TimeScrubber.tsx`.
- **Verification:** Test scrubber manipulation in browser; verify deck.gl layers update synchronously without lag.

---

### TASK-044: Incident Case Dashboard & Active Spill Monitor
- **Domain:** Frontend UI / Operations
- **Prerequisites:** TASK-043
- **Objective:** Build the case management view displaying active spill incidents, satellite detection chips, and creation modal.
- **Implementation Details:**
  - Create `frontend/src/app/cases/page.tsx` and `frontend/src/components/dashboard/CaseTable.tsx`:
    - Table of cases: ID, Region, Detection Time, Sensor (Sentinel-1 / Sentinel-2), Estimated Area ($km^2$), Status badge (`detecting`, `hindcasting`, `ready`, etc.).
    - Case creation dialog: upload GeoTIFF / enter Copernicus scene reference, select region of interest.
    - Search, status filtering, and sorting by recency or area.
    - Styled with `DESIGN.md` surface tokens, cards, and green pill CTAs.
- **Deliverables:** `frontend/src/app/cases/page.tsx`, `frontend/src/components/dashboard/CaseTable.tsx`.
- **Verification:** Load page; verify case listing, creation modal popup, and status badge color coding.

---

### TASK-045: Suspect Vessel Ranking Panel & Candidate Cards (Rules 1, 3, 6)
- **Domain:** Frontend UI / Forensic Attribution
- **Prerequisites:** TASK-044
- **Objective:** Build the suspect vessel ranking list displaying composite Culprit Score ($S_{culprit}$) and mandatory confidence metrics.
- **Implementation Details:**
  - Create `frontend/src/components/attribution/VesselRankingList.tsx` and `VesselCandidateCard.tsx`:
    - Ordered list of vessels sorted by $S_{culprit} \in [0, 100]$.
    - Card displays: Vessel Name, Flag, IMO, MMSI, Vessel Type prior badge.
    - Prominent score display accompanied by required Confidence Chip (Rule 1).
    - Status badges for AIS coverage (`full`, `dark_gap`, `non_ais_unknown`) (Rule 4).
    - Strict adherence to Rule 6: use labels "Candidate Suspect", "Attribution Score", never "Guilty" or "Polluter".
    - Clicking a card highlights vessel track on map and opens Explainability Drawer.
- **Deliverables:** `frontend/src/components/attribution/VesselRankingList.tsx`, `frontend/src/components/attribution/VesselCandidateCard.tsx`.
- **Verification:** Inspect rendered candidate cards; confirm confidence score is rendered adjacent to every score.

---

### TASK-046: "Why This Vessel?" Explainability Drawer & AHP Radar Chart (Rule 2, Feature 1)
- **Domain:** Frontend UI / Explainability
- **Prerequisites:** TASK-045
- **Objective:** Build the forensic explainability drawer displaying the 5 persisted sub-scores, evidence breakdown, and AHP radar chart.
- **Implementation Details:**
  - Create `frontend/src/components/attribution/ExplainabilityDrawer.tsx`:
    - Recharts / SVG Radar Chart displaying the 5 sub-scores:
      - Spatial Proximity ($S_{spatial}$)
      - Temporal Proximity ($S_{temporal}$)
      - Kinematic Heading Alignment ($S_{kinematic}$)
      - Behavioral Anomaly ($S_{anomaly}$)
      - Vessel Type Prior ($S_{type}$)
    - Detailed evidence breakdown cards for each dimension.
    - Link to view Counterfactual forward simulation comparison.
- **Deliverables:** `frontend/src/components/attribution/ExplainabilityDrawer.tsx`.
- **Verification:** Select candidate vessel in UI; verify drawer slides out displaying radar chart and 5 sub-score values.

---

### TASK-047: Alternative Hypotheses & Lookalike Comparison Panel (Rule 5, Feature 7)
- **Domain:** Frontend UI / Alternative Explanations
- **Prerequisites:** TASK-046
- **Objective:** Build the alternative explanations panel presenting non-vessel hypothesis scores alongside candidate vessels.
- **Implementation Details:**
  - Create `frontend/src/components/attribution/AlternativeExplanationsPanel.tsx`:
    - Displays scored hypotheses:
      - Natural Hydrocarbon Seep (geological bathymetry alignment, historical seep distance).
      - Atmospheric / Oceanic Lookalike (low wind calm water patch, biogenic surfactant, algal bloom).
      - Unregistered / Non-AIS Dark Vessel.
    - Evidence tags and risk assessment meters.
- **Deliverables:** `frontend/src/components/attribution/AlternativeExplanationsPanel.tsx`.
- **Verification:** Verify panel renders within case view and displays alternative hypotheses.

---

### TASK-048: Interactive Counterfactual Comparison View (Feature 2 / D2)
- **Domain:** Frontend UI / Counterfactual
- **Prerequisites:** TASK-047
- **Objective:** Build the counterfactual comparison modal showing side-by-side observed slick vs forward simulated vessel release.
- **Implementation Details:**
  - Create `frontend/src/components/attribution/CounterfactualModal.tsx`:
    - Dual map viewport or toggle overlay comparing:
      - Layer A: Observed SAR slick polygon.
      - Layer B: Forward drift cloud simulated from suspect's historical position.
    - IoU shape overlap score indicator and displacement error (km).
- **Deliverables:** `frontend/src/components/attribution/CounterfactualModal.tsx`.
- **Verification:** Click "Simulate Counterfactual" on candidate card; confirm simulation cloud renders and IoU displays.

---

### TASK-049: Interactive Evidence Graph Component (Feature 11 / P5)
- **Domain:** Frontend UI / Evidence Graph
- **Prerequisites:** TASK-048
- **Objective:** Build interactive node-edge graph visualization mapping evidence relationships from satellite scene to candidate vessel.
- **Implementation Details:**
  - Create `frontend/src/components/attribution/EvidenceGraphView.tsx` using React Flow or Vis.js:
    - Nodes styled with `DESIGN.md` surface tokens and icons for Scene, Slick, Origin Region, Time Window, AIS Track, Vessel Entity, Seep Catalog.
    - Directed edges with relationship labels (`ORIGINATED_AT`, `TRAVERSED`, `FLAGGED_LOITERING`).
    - Interactive node selection panning the main map to the associated feature.
- **Deliverables:** `frontend/src/components/attribution/EvidenceGraphView.tsx`.
- **Verification:** Open graph tab; verify nodes and edges render and clicking a node triggers coordinate focus.

---

### TASK-050: "What-If" Scenario Control Drawer & Parameter Sliders (Feature 3 / P3)
- **Domain:** Frontend UI / Scenario Exploration
- **Prerequisites:** TASK-049
- **Objective:** Build the "What-If" drawer enabling interactive parameter overrides and live scenario re-calculation.
- **Implementation Details:**
  - Create `frontend/src/components/investigation/WhatIfDrawer.tsx`:
    - Sliders and input controls:
      - Spill Age Range ($t_{age} \pm \Delta t$ hours)
      - Wind Drift Factor ($c_w: 2.0\% - 4.0\%$)
      - Origin Search Radius ($1\sigma, 2\sigma, 3\sigma$)
      - Custom AHP Weight sliders (automatically normalized to sum to $1.0$).
    - "Run Scenario" CTA button calling `POST /cases/{id}/whatif`.
    - Live comparison view highlighting ranking rank changes (e.g. Vessel A moves from #1 to #2).
- **Deliverables:** `frontend/src/components/investigation/WhatIfDrawer.tsx`.
- **Verification:** Adjust slider and click run; verify API call dispatches and updated rankings update smoothly.

---

### TASK-051: Legal Dossier Preview & PDF Export Modal (FR-20, C13)
- **Domain:** Frontend UI / Reporting
- **Prerequisites:** TASK-050
- **Objective:** Build dossier preview modal allowing investigators to inspect the generated report and download signed PDF.
- **Implementation Details:**
  - Create `frontend/src/components/dossier/DossierModal.tsx`:
    - Modal embedding PDF preview via browser viewer / canvas.
    - Displays SHA-256 integrity hash, model checkpoint versions, and generation timestamp.
    - "Download Official Dossier" button fetching PDF from `/cases/{id}/dossier`.
- **Deliverables:** `frontend/src/components/dossier/DossierModal.tsx`.
- **Verification:** Open dossier modal; confirm PDF renders in iframe/canvas and download button triggers file download.

---

## Phase 7: End-to-End Integration, Historical Validation & Packaging

### TASK-052: Full Pipeline End-to-End Integration Test on Benchmark Historical Spills
- **Domain:** System Testing / Empirical Validation
- **Prerequisites:** TASK-051
- **Objective:** Execute full end-to-end integration tests on synthetic and historical benchmark scenes (e.g., CSIRO/DARTIS benchmark data).
- **Implementation Details:**
  - Create `tests/e2e/test_full_pipeline.py`:
    - Trigger `POST /cases` with benchmark scene.
    - Wait for asynchronous Celery chain (`tier1 -> tier2 -> tier3 -> tier4 -> explain -> dossier`) to complete.
    - Verify:
      - Tier 1: mIoU $\ge 82.5\%$, lookalike rejected.
      - Tier 2: spreading age $t_{age}$ within $\pm 20\%$ of known ground truth.
      - Tier 3: origin centroid within $1.5\text{ km}$ of true discharge point; Liu-Weisberg skill score $ss \ge 0.80$.
      - Tier 4: true culprit vessel ranked in Top-1 ($S_{culprit} \ge 85$).
      - Dossier: valid PDF generated with SHA-256 stamped and zero banned words.
- **Deliverables:** `tests/e2e/test_full_pipeline.py`.
- **Verification:** Run `pytest tests/e2e/test_full_pipeline.py` and ensure all assertions pass.

---

### TASK-053: Automated Benchmark Validation Suite & Metrics Reporter (PRD Section 14)
- **Domain:** Quality Assurance / Scientific Benchmarking
- **Prerequisites:** TASK-052
- **Objective:** Build validation benchmarking CLI that evaluates system accuracy across the validation targets in PRD Section 14.
- **Implementation Details:**
  - Create `scripts/run_validation_benchmarks.py`:
    - Evaluates Tier 1 on test dataset: calculates mIoU, F1 score, False Discovery Rate (FDR). Target: mIoU $\ge 82.5\%$, F1 $\ge 87\%$, FDR $\le 12\%$.
    - Evaluates Tier 3 on historical drift cases: calculates separation error $s \le 0.15$, skill score $ss \ge 0.80$.
    - Evaluates Tier 4 attribution: calculates Top-1 accuracy ($\ge 85\%$), Top-3 accuracy ($\ge 95\%$), dark gap flag rate ($100\%$).
    - Output formatted summary table and JSON metrics report.
- **Deliverables:** `scripts/run_validation_benchmarks.py`.
- **Verification:** Run `python3 scripts/run_validation_benchmarks.py --fixture-set standard` and verify metrics meet thresholds.

---

### TASK-054: Production Packaging (Production Dockerfile, Compose & Healthchecks)
- **Domain:** DevOps / Deployment
- **Prerequisites:** TASK-053
- **Objective:** Package frontend, backend gateway, workers, and database into a unified, production-ready Docker Compose environment.
- **Implementation Details:**
  - Create multi-stage `docker/Dockerfile.backend` with Python 3.12, GDAL/GEOS system libraries, and poetry/pip dependencies.
  - Create multi-stage `docker/Dockerfile.frontend` with Next.js standalone build.
  - Create `docker/Dockerfile.worker` for Celery workers.
  - Create `docker-compose.prod.yml` configuring healthchecks, volume mounts, restart policies, and resource limits.
  - Provide automated initialization script `scripts/deploy_local.sh`.
- **Deliverables:** `docker/Dockerfile.backend`, `docker/Dockerfile.frontend`, `docker/Dockerfile.worker`, `docker-compose.prod.yml`, `scripts/deploy_local.sh`.
- **Verification:** Run `docker compose -f docker-compose.prod.yml up --build -d` and verify all containers reach healthy state via `docker compose ps`.

---

### TASK-055: Architecture Decision Record (ADR) Log Verification & Final Documentation Sign-off
- **Domain:** Documentation & Governance
- **Prerequisites:** TASK-054
- **Objective:** Verify synchronization between code, PRD, Architecture document, Tech Stack recommendation, and ADR log per `rules.md` Section 10.
- **Implementation Details:**
  - Run `scripts/lint_banned_terms.py` across entire codebase and documentation.
  - Verify all architectural decisions and external libraries match `AEGIS-Marine_Tech_Stack_Recommendation.md` or have approved entries in `ADR.md`.
  - Validate that OpenAPI spec, database schemas, and frontend interfaces are fully synchronized.
  - Generate final system deployment README and operational runbook.
- **Deliverables:** `README.md`, updated `ADR.md`, verification report.
- **Verification:** Run `python3 scripts/lint_banned_terms.py` (exit 0) and verify end-to-end user journey from scene upload to signed PDF dossier.

---

## Task Dependency Matrix & Sequential Execution Flow

```
TASK-001 (Repo Init & Skeleton)
   └── TASK-002 (Linting & Banned Term Linter)
        └── TASK-003 (Docker Compose Infra)
             └── TASK-004 (Postgres & Spatial Schema)
                  └── TASK-005 (Timescale Hypertables)
                       └── TASK-006 (Base Pydantic Schemas)
                            └── TASK-007 (Celery Task Queue & DLQ)
                                 └── TASK-008 (Synthetic Data Generator)
                                      └── TASK-009 (SAR/EO Ingestion Adapter)
                                           └── TASK-010 (Radar Backscatter Physics)
                                                └── TASK-011 (DeepLabv3+ Inference)
                                                     └── TASK-012 (Tier 1 Celery Pipeline)
                                                          └── TASK-013 (Morphometry & Skeleton)
                                                               └── TASK-014 (Fay Spreading Inversion)
                                                                    └── TASK-015 (BAOAC Thickness)
                                                                         └── TASK-016 (Tier 2 Celery Pipeline)
                                                                              └── TASK-017 (Met-Ocean Ingestion)
                                                                                   └── TASK-018 (Drift Physics Engine)
                                                                                        └── TASK-019 (OpenDrift Hindcast)
                                                                                             └── TASK-020 (Origin KDE Estimation)
                                                                                                  └── TASK-021 (Forward Forecast)
                                                                                                       └── TASK-022 (Tier 3 Celery Pipeline)
                                                                                                            └── TASK-023 (AIS Ingestion Adapter)
                                                                                                                 └── TASK-024 (Trajectory Spline)
                                                                                                                      └── TASK-025 (Anomaly Detector)
                                                                                                                           └── TASK-026 (AHP Weight Manager)
                                                                                                                                └── TASK-027 (Scoring Engine)
                                                                                                                                     └── TASK-028 (Tier 4 Celery Pipeline)
                                                                                                                                          └── TASK-029 (Why-This-Vessel)
                                                                                                                                               └── TASK-030 (Alternative Engine)
                                                                                                                                                    └── TASK-031 (Counterfactual)
                                                                                                                                                         └── TASK-032 (Evidence Graph)
                                                                                                                                                              └── TASK-033 (Replay Service)
                                                                                                                                                                   └── TASK-034 (PDF Dossier)
                                                                                                                                                                        └── TASK-035 (FastAPI RBAC)
                                                                                                                                                                             └── TASK-036 (REST/WS APIs)
                                                                                                                                                                                  └── TASK-037 (What-If Service)
                                                                                                                                                                                       └── TASK-038 (Audit Logging)
                                                                                                                                                                                            └── TASK-039 (Next.js & Tokens)
                                                                                                                                                                                                 └── TASK-040 (Type Generation)
                                                                                                                                                                                                      └── TASK-041 (MapLibre Canvas)
                                                                                                                                                                                                           └── TASK-042 (deck.gl Layers)
                                                                                                                                                                                                                └── TASK-043 (Time Scrubber)
                                                                                                                                                                                                                     └── TASK-044 (Case Dashboard)
                                                                                                                                                                                                                          └── TASK-045 (Vessel Cards)
                                                                                                                                                                                                                               └── TASK-046 (Explainability)
                                                                                                                                                                                                                                    └── TASK-047 (Alternatives UI)
                                                                                                                                                                                                                                         └── TASK-048 (Counterfactual UI)
                                                                                                                                                                                                                                              └── TASK-049 (Evidence Graph UI)
                                                                                                                                                                                                                                                   └── TASK-050 (What-If Drawer)
                                                                                                                                                                                                                                                        └── TASK-051 (Dossier Modal)
                                                                                                                                                                                                                                                             └── TASK-052 (E2E Test)
                                                                                                                                                                                                                                                                  └── TASK-053 (Benchmarks)
                                                                                                                                                                                                                                                                       └── TASK-054 (Docker Pack)
                                                                                                                                                                                                                                                                            └── TASK-055 (Sign-off)
```
