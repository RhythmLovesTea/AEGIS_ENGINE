# Product Requirements Document (PRD)
## AEGIS-Marine: Automated Spaceborne Oil Spill Detection, Hydrodynamic Hindcasting & AIS Vessel Attribution Platform

**Document Version:** 2.0 (Supersedes v1.0)
**Date:** September 3, 2026
**Aligned Problem Statement:** SIH/PS 26143 — Leveraging Satellite Imagery and AIS Data to Identify Oil-Spill-Causing Vessels (NTRO, Disaster Management)
**Status:** Draft for Build

> **Revision note:** This version incorporates the detailed technical architecture (SAR/EO physics, Fay spreading-age inversion, OpenDrift/OpenOil Lagrangian hindcasting, AHP-weighted culprit scoring) from the corrected technical specification, layered onto the plain-language problem framing and the differentiating-feature catalog from earlier drafts. All formulas, tools, and datasets below are taken directly from that specification and should be treated as the technical source of truth.

---

## 1. Executive Summary

AEGIS-Marine is an end-to-end forensic pipeline that closes the gap between **satellite detection of a marine oil slick** and **legally usable identification of the most likely vessel responsible**. It fuses four coupled technical tiers — SAR/EO segmentation, slick morphometry & age inversion, hydrodynamic Lagrangian hindcasting, and AIS spatio-temporal correlation — into a single automated workflow, and packages the result as an explainable, exportable evidence dossier.

The system's core value proposition is that it replaces a **~3-week manual investigation** with a **near-real-time (~4.5 minute) automated attribution pipeline**, while remaining explicit that outputs are ranked, probabilistic evidence rather than legal proof.

---

## 2. Background & Problem Context

Illegal hydrocarbon discharges (bilge flushing, oily ballast dumping, tank washing, illicit ship-to-ship bunkering) typically occur at night, under cloud cover, or in remote EEZ corridors — by the time a slick is detected, the responsible vessel may be hundreds of miles away. More than 300 research efforts address slick *detection*; essentially none close the loop to *attribution* by correlating detections with AIS vessel kinematics and reverse hydrodynamic modeling.

Existing tools are siloed by domain:

| Pipeline Component | State-of-the-Art Tools | Limitation |
|---|---|---|
| SAR oil slick segmentation | DeepLabv3+, CBD-Net, U-Net, ESA SNAP | Static 2D masks; no temporal tracking or polluter ID |
| Slick spreading & aging | Fay spreading models, Mackay exposure models | Standalone physics scripts, no live satellite parameter injection |
| Hydrodynamic drift simulation | OpenDrift/OpenOil, MEDSLIK-II, NOAA GNOME | Forward-only forecasting by default; not used for backward attribution |
| Vessel traffic monitoring | MarineTraffic, Spire AIS, exactEarth | Pure geographic tracking; no linkage to pollution events |

AEGIS-Marine's job is to integrate these four silos into one pipeline: **detect → characterize/age → hindcast origin → correlate AIS → rank & explain → report.**

### Why "Nearest Ship" Attribution Fails
A ship near the current slick location may have arrived after the spill, been travelling away from it, or simply transited without discharging. Meanwhile the true source vessel may be identified only by combining **estimated release time + estimated release location + vessel kinematics + behavioral anomalies + physical plausibility of drift**. This is the central problem AEGIS-Marine solves.

---

## 3. Goals & Objectives

### 3.1 Primary Goals
- **G1 — Detect & Characterize:** Segment candidate oil slicks from SAR/EO imagery with strong lookalike rejection (wind-thresholding, polarimetric entropy).
- **G2 — Estimate Spill Age:** Invert Fay's mechanical spreading law against observed slick area to estimate elapsed time since discharge (`t_age`), which sets the hindcast search window.
- **G3 — Hindcast the Origin:** Run reverse-time Lagrangian particle simulation (OpenDrift/OpenOil) to produce a probabilistic origin region (centroid + covariance), not a single point.
- **G4 — Reconstruct & Correlate AIS Traffic:** Interpolate historical vessel trajectories and intersect them with the origin probability cloud in both space and time.
- **G5 — Rank Suspects With a Defensible, Weighted Score:** Combine spatial, temporal, kinematic, behavioral-anomaly, and vessel-type-prior signals into a single composite Culprit Score using AHP-derived weights.
- **G6 — Explain Every Score:** Every ranking must be decomposable into the sub-scores and evidence that produced it.
- **G7 — Generate Actionable Output:** Auto-generate an evidence dossier suitable for Coast Guard / DG Shipping review.

### 3.2 Secondary Goals
- **G8 — Forecast Downstream Impact:** Run a forward +72h simulation (with evaporation/emulsification weathering) to predict shoreline impact for disaster-response prioritization.
- **G9 — Operate Credibly on Sample/Open Data:** Function fully on Sentinel-1/Sentinel-2 open imagery, CMEMS/ERA5 met-ocean data, and NOAA MarineCadastre/AISHub AIS data, with synthetic AIS as fallback.
- **G10 — Be Fast:** Target end-to-end latency from image ingestion to dossier export of ~4.5 minutes.

### 3.3 Non-Goals (Out of Scope for v1)
- Establishing legal/regulatory liability — outputs are decision-support evidence, not adjudication.
- Live, always-on global monitoring; v1 is incident/region-triggered analysis.
- Processing raw unprocessed Level-0 SAR sensor telemetry (system consumes Level-1 GRD products).
- Real-time integration with operational Coast Guard command-and-control systems (dossier export only in v1).

---

## 4. Target Users & Personas

| Persona | Description | Needs |
|---|---|---|
| **Coast Guard / DG Shipping Investigator** | Investigates reported or detected spills within Indian EEZ corridors. | Fast, defensible suspect shortlist; exportable legal-grade evidence dossier. |
| **NTRO / Disaster Management Analyst** | Monitors coastal/EEZ regions for environmental incidents. | Rapid detection, age estimation, drift forecasting for shoreline-impact prioritization. |
| **Maritime Enforcement / Legal Reviewer** | Uses the dossier to decide whether to pursue prosecution. | Confidence-qualified scoring, transparent methodology, audit trail. |
| **Technical Reviewer / Program Evaluator** | Evaluates the system's technical rigor and defensibility against PS 26143's requirements, whether during internal review, procurement, or independent audit. | Clear architecture, defensible math (AHP weights, drift physics), a working live demonstration. |

---

## 5. User Stories

### 5.1 Detection, Characterization & Aging
- **US-1:** As an analyst, I want to upload a Sentinel-1 GRD scene and have the system segment any candidate oil slick, so I don't have to inspect imagery manually.
- **US-2:** As an analyst, I want the system to reject lookalikes (low-wind calm zones, biogenic surfactants, algae blooms) so I'm not chasing false positives.
- **US-3:** As an investigator, I want the system to estimate how long ago the spill occurred (`t_age`), so the hindcast search window is correctly sized.
- **US-4:** As an analyst, I want slick geometry (area, perimeter, orientation, thickness class via BAOAC) reported, so I understand the scale and severity.

### 5.2 Hindcasting
- **US-5:** As an investigator, I want the system to reverse-simulate ocean drift from the observed slick backward through `t_age` hours, so I get a probable origin region and time window instead of guessing.
- **US-6:** As an analyst, I want the origin shown as a probability cloud (centroid + covariance ellipse), not a single pin, so I understand the uncertainty.
- **US-7:** As a disaster-management analyst, I want a +72h forward forecast with weathering (evaporation, emulsification) and shoreline-impact estimates, so I can prioritize containment response.

### 5.3 AIS Correlation & Ranking
- **US-8:** As an investigator, I want the system to pull historical AIS tracks within the origin corridor (`μ_p ± 3Σ_p`) and time window, so I get a manageable, relevant suspect list.
- **US-9:** As an investigator, I want each candidate vessel scored on spatial proximity, temporal coincidence, kinematic/heading alignment, behavioral anomalies, and vessel-type risk, so the ranking isn't based on distance alone.
- **US-10:** As an investigator, I want vessels that disabled their AIS transponder during the estimated release window ("dark ship" behavior) to be automatically flagged and penalized upward in risk, so evasive actors aren't missed.
- **US-11:** As a jury/reviewer, I want to see the AHP weight-derivation and consistency check, so I trust that the scoring isn't arbitrary.

### 5.4 Explainability & Reporting
- **US-12:** As an investigator, I want to click any ranked vessel and see the breakdown of its composite score into sub-scores and supporting evidence, so I can justify the ranking to others.
- **US-13:** As an investigator, I want a one-click "Export Legal/Forensic Dossier" (PDF) containing SAR metadata, drift skill scores, and vessel kinematic logs, so I can hand off a complete case package.
- **US-14:** As an analyst, I want to replay the investigation on a time-scrubber (particle convergence + vessel motion), so I can visually verify the reasoning.
- **US-15:** As any user, I want the system to consistently use language like "most correlated vessel" / "candidate suspect," never "responsible vessel," so outputs are never mistaken for a legal conclusion.

### 5.5 Robustness
- **US-16:** As an analyst, I want the system to still function using synthetic AIS data and sample Sentinel-1 scenes when live feeds are unavailable, so a demo or offline analysis is never blocked.
- **US-17:** As an investigator, I want vessels without AIS (non-cooperative targets) to be flagged as "unknown" using SAR-based ship-wake/vessel detection, so non-AIS actors aren't invisible to the investigation.

---

## 6. System Architecture (4-Tier Pipeline)

```
TIER 1 — Multi-Modal Earth Observation Ingestion & Segmentation
   Sentinel-1/ALOS-2 SAR (all-weather, day/night) + Sentinel-2/Landsat-8/9 EO (daytime cross-validation)
                    │
                    ▼
TIER 2 — Slick Morphometry, Thickness & Spreading-Age Inversion
   Area/perimeter/orientation, BAOAC thickness class, Fay spreading-law inversion → t_age
                    │
                    ▼
TIER 3 — Hydrodynamic Advection-Diffusion Modeling (OpenDrift/OpenOil)
   3A: Backward Lagrangian hindcast → origin PDF cloud P(x,y,t_k)
   3B: Forward +72h forecast + weathering → shoreline impact
                    │
                    ▼
TIER 4 — AIS Spatio-Temporal Correlation & Culprit Attribution
   Trajectory reconstruction, anomaly detection, AHP-weighted S_culprit scoring,
   automated Coast Guard / DG Shipping evidence dossier generation
```

---

## 7. Feature List

### 7.1 Core Features (MVP — Modules 1–4, must ship)

| # | Feature | Technical Basis |
|---|---|---|
| C1 | SAR/EO Oil Slick Segmentation | DeepLabv3+ (ResNet-50 encoder, ASPP dilation rates {1,6,12,18}), compound loss (Focal + Dice + Boundary), Lee speckle filter, land mask |
| C2 | Lookalike Rejection | Cloude-Pottier polarimetric entropy (H) & mean alpha angle, co-located ERA5 wind thresholding (4–10 m/s operating window) |
| C3 | EO Cross-Validation | Sentinel-2/Landsat multispectral indices (SFOI, NDOI), red-edge (705 nm) biogenic discrimination |
| C4 | Slick Morphometry | Spatial central moments → area, perimeter, principal dispersion axis |
| C5 | Spill Age Inversion | Fay spreading-law inversion of segmented area → `t_age` (hours), sets hindcast window |
| C6 | Volumetric Thickness Profiling | BAOAC codes 1–5 + polarimetric dielectric inversion |
| C7 | Lagrangian Backward Hindcasting | OpenDrift/OpenOil, N ≥ 10,000 particles, Δt = −15 min, CMEMS currents + ERA5 winds + Stokes drift + Coriolis rotation |
| C8 | Origin Probability Cloud | 2D Gaussian KDE over particle ensemble → centroid `μ_p`, covariance `Σ_p` |
| C9 | AIS Trajectory Reconstruction | Cubic spline interpolation of historical AIS (MarineCadastre / AISHub) within `μ_p ± 3Σ_p` and `t_obs ± t_age` |
| C10 | Behavioral Anomaly Detection | Speed drops (4–8 kt), abnormal turns, AIS transponder gaps ("dark ship" `A_dark`) |
| C11 | AHP-Weighted Culprit Scoring | Composite `S_culprit ∈ [0,100]` from spatial, temporal, kinematic, anomaly, and vessel-type sub-scores |
| C12 | Geospatial War Room UI | Next.js + MapLibre GL/Deck.gl; layer toggling (SAR, slick polygon, currents, AIS); time-scrubber for particle convergence |
| C13 | Automated Evidence Dossier Export | One-click PDF (WeasyPrint/ReportLab) with SAR stamps, drift skill scores, vessel kinematic logs |

### 7.2 Differentiating Features (strong build target)

| # | Feature | Description |
|---|---|---|
| D1 | Explainable "Why This Vessel?" Panel | Decomposes `S_culprit` into its 5 weighted sub-scores with an evidence checklist per vessel |
| D2 | Counterfactual Vessel Testing | Simulates a hypothetical forward spill from a candidate vessel's actual track/time and compares it against the observed slick polygon |
| D3 | Probabilistic Origin/Uncertainty Map | Renders `P(x,y,t_k)` as a heatmap/confidence ellipse, reports origin-region area (km²) and confidence |
| D4 | Investigation Replay | Time-scrubber animating reverse particle convergence, vessel motion, and evolving `S_culprit` rankings |
| D5 | Forward Forecast & Shoreline Impact | +72h forecast with evaporation (Mackay model) and emulsification (water-uptake kinetics), Estimated Time of Beaching (ETB), Coastal Vulnerability Index (CVI), beached volume |
| D6 | AHP Weight Transparency & Consistency Check | Displays the pairwise comparison matrix, eigenvector weights, and consistency ratio (CR < 0.10) used for scoring |

### 7.3 Premium / Stretch Features

| # | Feature | Description |
|---|---|---|
| P1 | Multi-Sensor Cross-Confirmation | Cross-checks detections across Sentinel-1/RADARSAT-2/TerraSAR-X passes to reduce false positives |
| P2 | Alternative Explanation Engine | Explicitly scores non-vessel explanations (natural seep, imaging artifact) alongside vessel candidates |
| P3 | Interactive "What-If" Controls | Adjust `t_age` window, origin radius (`Σ_p` scaling), search window, current/wind uncertainty; live re-ranking |
| P4 | Non-AIS Vessel Detection | SAR ship-wake / optical vessel detection to flag "unknown" non-cooperative targets alongside AIS-ranked suspects |
| P5 | Evidence Graph | Interactive node-graph: observation → slick → origin → time window → AIS records → candidate vessels |
| P6 | Historical Incident Backtesting | Validate hindcast/attribution accuracy against known historical spill events (e.g., verified accident case studies) |

### 7.4 Recommended Build Priority
1. **Core Modules 1–4 (C1–C13)** — required for any credible end-to-end demo.
2. **D1, D3, D6** — highest explainability/trust payoff relative to effort; directly counters "nearest ship = culprit."
3. **D2, D4, D5** — high novelty, higher engineering cost.
4. **P4 (non-AIS detection), P2 (alternative explanations)** — strengthen forensic credibility.
5. Remaining premium features as time/resources allow.

---

## 8. Functional Requirements

| ID | Requirement |
|---|---|
| FR-1 | System shall ingest Level-1 Sentinel-1 GRD (VV/VH) and apply Lee speckle filtering + land masking prior to inference. |
| FR-2 | System shall run a DeepLabv3+ (ResNet-50, ASPP) segmentation model to output a slick polygon (GeoJSON), centroid, and area `A_s`. |
| FR-3 | System shall reject/flag low-confidence detections using ERA5 wind thresholding (reject < 3 m/s and evaluate 4–10 m/s operating band) and polarimetric entropy/alpha-angle checks. |
| FR-4 | System shall optionally cross-validate detections with Sentinel-2/Landsat SFOI/NDOI indices and red-edge biogenic discrimination when co-located optical imagery is available. |
| FR-5 | System shall compute slick morphometry (area, perimeter, principal axis orientation) via spatial central moments. |
| FR-6 | System shall invert Fay's mechanical spreading law against `A_s` to estimate `t_age`, and use it to bound the hindcast simulation window `[t_obs − t_age, t_obs]`. |
| FR-7 | System shall classify slick thickness using BAOAC codes 1–5 and, where feasible, polarimetric dielectric thickness inversion. |
| FR-8 | System shall initialize ≥10,000 Lagrangian particles across the slick polygon in OpenDrift/OpenOil and run backward advection (Δt = −15 min) using CMEMS surface currents, ERA5 winds, Stokes drift, and Coriolis deflection. |
| FR-9 | System shall compute the origin probability density `P(x,y,t_k)` via 2D Gaussian KDE, yielding centroid `μ_p` and covariance `Σ_p`. |
| FR-10 | System shall optionally run a +72h forward simulation with evaporation (Mackay) and emulsification (water-uptake kinetics) weathering, flagging particles within 50 m of coast as stranded and computing ETB, CVI, and beached volume. |
| FR-11 | System shall query historical AIS data (MarineCadastre/AISHub, or synthetic fallback) within the spatial window `μ_p ± 3Σ_p` and temporal window `t_obs ± t_age`. |
| FR-12 | System shall reconstruct continuous vessel trajectories via cubic spline interpolation of discrete AIS messages. |
| FR-13 | System shall detect behavioral anomalies per vessel: speed drops into the 4–8 kt band, abnormal course turns, and AIS transponder gaps (`A_dark`). |
| FR-14 | System shall compute five sub-scores per candidate vessel — spatial (Mahalanobis-distance-based), temporal (exponential decay), kinematic (heading alignment), anomaly, and vessel-type prior — and combine them into `S_culprit ∈ [0,100]` using AHP-derived weights `w = [0.30, 0.25, 0.15, 0.20, 0.10]`. |
| FR-15 | System shall display the AHP pairwise comparison matrix and consistency ratio (target CR < 0.10) on request, for methodological transparency. |
| FR-16 | System shall provide a per-vessel "Why this vessel?" breakdown showing each sub-score and the supporting raw evidence (e.g., closest AIS timestamp, transponder gap duration). |
| FR-17 | System shall render a geospatial UI (SAR layer, slick polygon, current streamlines, AIS tracks) with a time-scrubber replaying reverse particle convergence and forward vessel motion. |
| FR-18 | System shall generate a one-click exportable PDF evidence dossier containing SAR detection metadata, drift/skill scores, ranked suspect list with sub-scores, and vessel kinematic logs. |
| FR-19 | System shall flag vessels with no AIS signal as "unknown/non-cooperative" using supplementary SAR/optical vessel-detection evidence where available, rather than silently excluding them. |
| FR-20 | All UI and report language shall use non-accusatory phrasing ("most correlated vessel," "candidate suspect") — never "responsible vessel," "guilty," or equivalent legal-conclusion language. |
| FR-21 | System shall function end-to-end on open sample data (Sentinel-1/-2, CMEMS, ERA5, MarineCadastre) and on synthetic AIS data when live feeds are unavailable, without code changes. |

---

## 9. Non-Functional Requirements

| Category | Requirement |
|---|---|
| **Latency** | Target end-to-end pipeline (ingestion → segmentation → age inversion → hindcast → AIS correlation → dossier) ≈ 4.5 minutes; segmentation inference ≤ 30 s, hindcast (10,000 particles) ≤ 2 min. |
| **Explainability** | Every composite score must be decomposable into its weighted sub-scores and underlying evidence. |
| **Data Resilience** | Must run on synthetic AIS / sample SAR scenes without code changes when live data is unavailable. |
| **Scalability (rendering)** | Front-end must render 10,000+ dynamic particle trajectories and AIS vectors via WebGL (Deck.gl/MapLibre GL) at interactive frame rates. |
| **Cross-Sensor Robustness** | Segmentation model must generalize across Sentinel-1, RADARSAT-2, and TerraSAR-X via geometric, speckle-noise, and radiometric-jitter augmentation. |
| **Auditability** | Every case run (inputs, model version, assumptions, weights, outputs) must be logged and reproducible for later review. |
| **Scientific Honesty** | Uncertainty must be surfaced numerically and visually at every stage: detection confidence, origin covariance, and score confidence. |
| **Methodological Transparency** | AHP weight derivation and consistency ratio must be inspectable, not hidden inside the scoring engine. |

---

## 10. Core Mathematical & Physical Basis (Reference)

This section summarizes the key formulas that ground the pipeline's outputs, for engineering and jury-defense reference.

- **Bragg resonance (SAR detection):** `λ_B = λ_0 / (2 sin θ)`
- **Co-polarization difference:** `PD = σ⁰_VV − σ⁰_HH`
- **Damping ratio:** `DR = σ⁰_clean / σ⁰_slick`
- **Cloude-Pottier entropy/alpha:** `H = −Σ Pᵢ log₃(Pᵢ)`, `ᾱ = Σ Pᵢ αᵢ` (clean sea: H < 0.3, ᾱ < 30°; oil: H > 0.6, ᾱ > 30°)
- **Surface Floating Oil Index (SFOI)** and **Normalized Difference Oil Index (NDOI)** — Sentinel-2/Landsat band-ratio indices for optical cross-validation.
- **Compound segmentation loss:** `L_total = L_Focal + L_Dice + λ_bound · L_Boundary` (α=0.75, γ=2.0 for Focal)
- **Fay spreading-age inversion:** `t_age = (A_s / (π k₃²))^(2/3) · (ρ_w² ν_w / σ_net²)^(1/3)`
- **Total drift velocity:** `u_drift = u_current + c_w·R(θ_w)·u_10 + u_Stokes` (c_w = 2.5–3.5% wind drag)
- **Turbulent diffusion (Monte Carlo):** `Δx_diff = R_n √(2 K_h Δt)`
- **Origin PDF (Gaussian KDE):** `P(x,y,t_k) = (1/N) Σ K_H(x − x_p(t_k))` → centroid `μ_p`, covariance `Σ_p`
- **Evaporative loss (Mackay):** `F_evap(t) = ln(1 + K_E θ_evap t_exp) / K_E`
- **Emulsification kinetics:** `dY_w/dt = K_emul (U_10 + 1)² (Y_max − Y_w)`
- **Composite Culprit Score:** `S_culprit(v) = w1·S_spatial + w2·S_temporal + w3·S_kinematic + w4·S_anomaly + w5·S_type`, weights `[0.30, 0.25, 0.15, 0.20, 0.10]` derived via AHP (λ_max = 5.042, CI = 0.0105, CR = 0.0094 < 0.10 → consistent).
  - `S_spatial`: Mahalanobis-distance Gaussian kernel between vessel position and origin centroid.
  - `S_temporal`: exponential decay over time delta (`τ = 1.5 h`).
  - `S_kinematic`: cosine similarity between vessel heading and slick major axis, modulated by speed.
  - `S_anomaly`: bounded combination of speed-drop, course-deviation, and dark-transponder-gap indicators.
  - `S_type`: categorical prior by vessel class (Tanker/Bunker 1.00, Cargo 0.75, Offshore 0.50, Fishing 0.30, Pleasure 0.05).

---

## 11. System Architecture — Module Breakdown (PRD-level)

**Module 1 — SAR/EO Semantic Segmentation**
- Input: Level-1 Sentinel-1 GRD
- Pipeline: Lee speckle filter (5×5) + land mask → DeepLabv3+/U-Net inference on VV amplitude → wind-threshold lookalike filtering (4–10 m/s)
- Output: Slick GeoJSON polygon, centroid (lat/lon), area `A_s` (km²)

**Module 2 — Hydrodynamic Hindcast Engine**
- Input: Slick GeoJSON, `t_obs`, `t_age`
- Pipeline: Seed N=10,000 particles in OpenOil → ingest CMEMS current + ERA5 wind NetCDF → backward simulation (Δt = −15 min) over `[t_obs − t_age, t_obs]`
- Output: Origin PDF cloud `P(x,y,t_k)`, centroid `μ_p`, covariance `Σ_p`

**Module 3 — AIS Correlation & Anomaly Scoring Engine**
- Input: Historical AIS within `μ_p ± 3Σ_p` and `t_obs ± t_age`
- Pipeline: Cubic-spline trajectory interpolation → Mahalanobis distance + temporal delta computation → anomaly heuristics (speed, course, dark-gap) → `S_culprit(v)` computation
- Output: Ranked suspect list (MMSI, IMO, name, flag state, confidence score)

**Module 4 — Web-Based Geospatial War Room**
- Stack: Next.js, TailwindCSS, MapLibre GL / Deck.gl
- Capabilities: multi-layer toggling (SAR, slick polygon, current streamlines, AIS tracks); interactive time-scrubber for reverse particle convergence; ranked suspect cards; one-click "Export Coast Guard Legal Dossier" (PDF).

---

## 12. Data Sources & Tools

### 12.1 Datasets
| Domain | Data Asset | Access | Parameters |
|---|---|---|---|
| SAR Imagery | Sentinel-1 C-SAR | Copernicus Open Access | IW GRD, VV/VH, 10 m, C-band (5.405 GHz) |
| SAR Benchmark | CSIRO (5,630 chips) & DARTIS (4,355 chips) | Kaggle/Zenodo | Annotated oil-vs-lookalike ground truth |
| Ocean Currents | CMEMS GLO12 | Copernicus Marine Service | 1/12° (~8 km), hourly surface (u,v) |
| Winds | ERA5 / NOAA GFS | ECMWF / NOAA | 0.25° grid, hourly u10/v10 |
| AIS Traffic | NOAA MarineCadastre & AISHub | Open feed | Types 1–3 (MMSI, lat, lon, SOG, COG) + Type 5 static (IMO, ship type) |

### 12.2 Software / Frameworks
| Tool | Purpose |
|---|---|
| OpenDrift / OpenOil (Python) | Lagrangian particle tracking, native reverse-time backtracking, oil-weathering (ADIOS) libraries |
| PyTorch / Segmentation Models PyTorch | DeepLabv3+/U-Net/TransUNet inference |
| Rasterio & GDAL | GeoTIFF ingestion, radiometric calibration, CRS reprojection |
| GeoPandas & Shapely | Spatial indexing (R-tree), polygon buffering, AIS interpolation |
| MapLibre GL / Deck.gl | WebGL rendering of particles + AIS vectors |
| WeasyPrint / ReportLab | PDF evidence dossier generation |

---

## 13. Success Metrics

### 13.1 Detection & Segmentation (Tier 1)
| Metric | Target |
|---|---|
| Mean IoU (mIoU) on CSIRO/DARTIS benchmark | ≥ 82.5% |
| F1-Score | ≥ 87.0% |
| False Discovery Rate (FDR) | ≤ 12.0% |

### 13.2 Hydrodynamic Hindcasting (Tier 3)
| Metric | Target |
|---|---|
| Liu-Weisberg Skill Score (`ss`) vs. verified historical spills | ≥ 0.80 |
| Cumulative separation error (`s`) | ≤ 0.15 |
| Correct origin intersection with known release point | Within 1.5 km |

### 13.3 AIS Attribution (Tier 4)
| Metric | Target |
|---|---|
| Top-1 attribution accuracy (validated cases / synthetic ground truth) | ≥ 85.0% |
| Top-3 attribution accuracy | ≥ 95.0% |
| Correct dark-transponder-gap flag rate | 100% |
| AHP consistency ratio (CR) | < 0.10 |

### 13.4 System / Product Metrics
| Metric | Target |
|---|---|
| End-to-end pipeline latency (ingestion → dossier) | ≈ 4.5 minutes |
| Dossier generation success rate | 100% of completed analyses |
| Particle rendering performance (front-end) | 10,000+ particles at 60 FPS |
| Uncertainty communicated at every stage | 100% coverage (no bare point-estimates) |

### 13.5 Responsible-Use Metrics
| Metric | Target |
|---|---|
| Instances of accusatory/legal-conclusion language ("responsible," "guilty") in UI/reports | Zero |
| Non-AIS/"unknown" vessels surfaced rather than silently dropped | 100% of cases with detected non-cooperative targets |

---

## 14. Empirical Validation Strategy

| Validation Tier | Benchmark | Metric & Acceptance Criteria |
|---|---|---|
| Tier 1: Segmentation | CSIRO (5,630 chips) & DARTIS (4,355 chips) | mIoU ≥ 82.5%, F1 ≥ 87.0%, FDR ≤ 12.0% |
| Tier 2: Hydrodynamic back/fore-tracking | ≥3 historical verified maritime accidents (e.g., Ennore 2017) | Liu-Weisberg `ss ≥ 0.80`, separation error `s ≤ 0.15`, origin intersection within 1.5 km |
| Tier 3: AIS attribution | Investigation files & IMO casualty reports | Top-1 ≥ 85.0%, Top-3 ≥ 95.0%, dark-gap flag = 100% |

---

## 15. Risks & Assumptions

| Risk | Mitigation |
|---|---|
| Real AIS/SAR coverage may be sparse for a chosen demo region/time | Use pre-downloaded Sentinel-1 tiles + synthetic AIS fallback (Section 12, FR-21). |
| Hindcast/drift model is a physical approximation, not ground truth | Represent origin as a probability cloud (`μ_p`, `Σ_p`), validate against Liu-Weisberg skill score on historical spills, and report confidence explicitly. |
| AHP weights could be perceived as arbitrary | Publish the full pairwise comparison matrix and consistency ratio (D6); allow "what-if" reweighting (P3). |
| Users could over-trust a high `S_culprit` score as proof | Enforce responsible-use language (FR-20), always show sub-score breakdown, and flag non-AIS/alternative explanations. |
| Vessels without AIS ("dark" targets or non-equipped) evade attribution entirely | Flag as "unknown/non-cooperative" using supplementary SAR ship-wake/optical detection (P4, FR-19), rather than omitting them. |
| Multi-day-old slicks: evaporation/emulsification degrade signal reliability | Apply Mackay evaporative-loss and emulsification models; reduce attribution confidence for `t_age > 72h`. |
| Scope creep across 4 tiers + 6 differentiators + 6 premium features | Follow phased build priority (Section 7.4); Core Modules 1–4 must work end-to-end before any differentiator/premium feature. |

---

## 16. Roadmap / Phasing (Production Build Plan)

This roadmap assumes an ongoing engineering effort building toward a real, operationally usable system — not a time-boxed demo. Phases are sequenced by dependency and risk, not by an artificial deadline; durations are indicative and should be re-baselined against actual team size and data-access lead times (especially CMEMS/AIS provider onboarding, which can be the long pole).

| Phase | Indicative Duration | Scope | Outcome / Exit Criteria |
|---|---|---|---|
| **Phase 0 — Data & Infrastructure Foundation** | 2–4 weeks | Stand up core infra (Section on Tech Stack); establish data pipelines for Sentinel-1/-2 (Copernicus), CMEMS GLO12, ERA5, and MarineCadastre/AISHub AIS feeds; build the synthetic-AIS generator and curated offline SAR/AIS test fixtures for reproducible development. | All four data sources ingest reliably into storage; synthetic-data fallback path is functional and covers the same schema as live data. |
| **Phase 1 — Core Computational Engine (Tier 1–2)** | 4–8 weeks | Train/fine-tune the DeepLabv3+ segmentation model (C1) on CSIRO/DARTIS benchmarks; implement lookalike rejection (C2), EO cross-validation (C3), morphometry (C4), Fay spreading-age inversion (C5), and BAOAC thickness profiling (C6). | Tier 1 validation targets met (mIoU ≥ 82.5%, F1 ≥ 87.0%, FDR ≤ 12.0% — Section 14). |
| **Phase 2 — Hydrodynamic Engine (Tier 3)** | 4–6 weeks | Integrate OpenDrift/OpenOil for backward Lagrangian hindcasting (C7) and origin-cloud computation (C8); implement forward +72h forecasting with weathering (D5). | Tier 2 validation targets met against ≥3 historical verified spills (Liu-Weisberg `ss ≥ 0.80`, separation error `s ≤ 0.15`, origin intersection within 1.5 km). |
| **Phase 3 — AIS Correlation & Scoring Engine (Tier 4)** | 4–6 weeks | Build AIS trajectory reconstruction (C9), anomaly detection (C10), and the AHP-weighted `S_culprit` scoring engine (C11), including the AHP consistency-ratio computation (D6). | Tier 3 validation targets met (Top-1 ≥ 85.0%, Top-3 ≥ 95.0%, dark-gap flag = 100% — Section 14). |
| **Phase 4 — Geospatial UI & Evidence Dossier** | 4–6 weeks | Build the Next.js/MapLibre/deck.gl war room (C12), the "Why this vessel?" explainability panel (D1), the probabilistic origin/uncertainty map (D3), and the automated PDF dossier export (C13). | Full end-to-end flow (image in → ranked, explained suspect list → exportable dossier) working against both live and synthetic data. |
| **Phase 5 — Forensic Depth & Trust Features** | 4–8 weeks | Investigation Replay (D4), Counterfactual Vessel Testing (D2), Alternative Explanation Engine (P2), Non-AIS vessel detection (P4). | System explicitly considers and scores non-vessel explanations; replay and counterfactual features are demo-ready and reviewed for scientific defensibility. |
| **Phase 6 — Hardening, Validation & Field Trial** | 6–10 weeks | Full empirical validation against the three-tier strategy (Section 14) using additional historical incidents; security/auth hardening; performance tuning against the latency budget (Section 9); pilot deployment with a real investigator/analyst user group. | System meets all success metrics (Section 13) under real operational conditions; sign-off from pilot users. |
| **Phase 7 — Ongoing / Stretch** | Continuous | Multi-sensor cross-confirmation (P1), interactive what-if controls (P3), evidence graph (P5), historical incident backtesting library (P6); ongoing model retraining as new labeled spill data becomes available. | Incremental feature releases; system accuracy and coverage improve over time as a maintained product, not a one-off deliverable. |

**Note on sequencing:** Phases 1–3 (the three computational tiers) can be parallelized across separate engineers/sub-teams once Phase 0's data contracts are stable, since they have well-defined input/output boundaries (GeoJSON → origin PDF → ranked vessel list). Phase 4 (UI) should begin against mocked/fixture outputs from Phases 1–3 rather than waiting for all three to fully complete, to avoid the UI becoming the critical-path bottleneck.

---

## 17. Guiding Principles

1. **Never assert certainty the evidence doesn't support.** Every score, origin region, and ranking carries an explicit confidence indicator.
2. **Explainability is a feature, not an afterthought.** No `S_culprit` value is shown without its 5-component breakdown.
3. **The nearest vessel is not automatically the source.** Time, drift physics, and kinematic plausibility outrank raw distance.
4. **Silence is not evidence of innocence.** Dark-transponder gaps and non-AIS vessels must be surfaced, not dropped.
5. **Always consider the alternative.** A credible forensic tool actively scores non-vessel explanations (natural seep, imaging artifact) alongside vessel candidates.
6. **Language matters.** Use "most correlated vessel" / "candidate suspect" / "potential source" — never "responsible" or "guilty."
7. **Show your math.** AHP weight derivation, consistency ratios, and skill scores should be inspectable on demand, not hidden inside a black box.

---

*End of Document*
