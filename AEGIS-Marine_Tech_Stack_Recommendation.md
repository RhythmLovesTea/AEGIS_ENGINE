# AEGIS-Marine — Recommended Tech Stack (2026)

**Companion to:** AEGIS-Marine PRD v2.0
**Date:** September 3, 2026
**Scope:** Frontend, Backend, Auth, Database, Deployment — with justification tied directly to PRD requirements.

---

## Summary Table

| Layer | Choice | Primary PRD Driver |
|---|---|---|
| Frontend | Next.js + MapLibre GL + deck.gl + Tailwind/shadcn | FR-17, NFR rendering (10k+ particles @ 60fps) |
| Backend | Python/FastAPI + Celery/Redis | C1, C5, C7, C9, C13 — all Python-only scientific tooling |
| Auth | Auth.js + Clerk/Auth0 (MVP) → Keycloak (production) | RBAC across investigator/analyst/reviewer personas, auditability |
| Database | PostgreSQL + PostGIS + TimescaleDB, S3/MinIO for rasters | Spatial queries (FR-7, FR-11), AIS time-series, large raster/PDF assets |
| Deployment | Docker Compose (early MVP) → Kubernetes (scaled production) | GPU-bursty ML/simulation workloads, path to sovereign/on-prem hosting |

---

## 1. Frontend — Next.js 15 (App Router) + MapLibre GL + deck.gl + TailwindCSS

This is what the PRD already specifies (Module 4), and it's the right call:

- **deck.gl** is essentially mandatory for FR-17 / the rendering NFR — rendering 10,000+ Lagrangian particles at 60 FPS requires WebGL-layer composition, not SVG/Canvas. deck.gl's `ScatterplotLayer` / `TripsLayer` is purpose-built for exactly this (animated particle trajectories over time).
- **MapLibre GL** (not Mapbox GL) — an open-source fork, no vendor licensing cost, integrates natively with deck.gl as a base map, and avoids Mapbox's post-2023 pricing/licensing changes, which matters for a government-adjacent NTRO deployment.
- **Next.js App Router** gives you server components for the heavier dashboard pages (dossier list, case history) while keeping the map/replay view fully client-rendered — a good split for a mixed data-heavy + interactive-heavy UI.
- Use **shadcn/ui** on top of Tailwind for the ranked-suspect cards, AHP weight tables, and the "Why this vessel?" panel — fast to build accessible, consistent components without a heavy design system.

---

## 2. Backend — Python (FastAPI) as the core service, not Node

This is the one place to deviate from a "typical" web stack, and it's non-negotiable given the PRD:

- Every core computational module (C1 segmentation via PyTorch/DeepLabv3+, C7 OpenDrift/OpenOil hindcasting, C9 GeoPandas/Shapely AIS matching, C13 WeasyPrint dossier generation) is Python-only. There is no mature JS equivalent for OpenDrift or segmentation-models-pytorch. Fighting this by wrapping Python in a Node backend just adds a translation layer for no benefit.
- **FastAPI** specifically because:
  - Async support matters when a single case run chains a segmentation call → hindcast simulation → AIS query → PDF export (FR-6 through FR-18).
  - Pydantic models give clean validation for the AHP scoring payloads and GeoJSON schemas.
  - It ships OpenAPI docs for free — useful when the system needs to be defensible/auditable (NFR "Auditability").
- Long-running jobs (the ~2-minute 10,000-particle hindcast, within the NFR latency budget) should run as background tasks via **Celery + Redis** (or **Arq**, lighter-weight) rather than blocking a request thread — the frontend polls or gets a WebSocket push when a stage completes, which also naturally supports the Investigation Replay (D4) staged reveal.
- Next.js talks to FastAPI over a typed REST/JSON boundary (or tRPC-style OpenAPI-generated client) rather than trying to merge them into one runtime.

---

## 3. Auth — Auth.js (NextAuth) fronting an OIDC-compliant identity provider (Keycloak self-hosted, or Auth0/Clerk for speed)

- Given the persona set (Coast Guard/DG Shipping investigators, NTRO analysts, legal reviewers), this needs **role-based access control**, not just login — investigators shouldn't see the same admin surface as a legal reviewer exporting a dossier.
- For the initial build phase, while iterating on the core computational pipeline: **Clerk** or **Auth0** gets you RBAC, session management, and audit logs (needed for the NFR "Auditability" requirement — every case run should be traceable to a user) with near-zero setup, so auth doesn't become a distraction from the harder ML/hydrodynamics work.
- For the operational, government-facing deployment: self-hosted **Keycloak** is the realistic long-term answer — NTRO/Coast Guard deployments will require on-prem or sovereign-cloud identity rather than a third-party SaaS holding investigator credentials. This should be treated as a required migration on the roadmap (see PRD Section 16, Phase 6 hardening), not an optional upgrade — plan the cutover early rather than bolting it on right before field trial. Auth.js in the Next.js layer can point at either provider without a rewrite, since both speak OIDC.

---

## 4. Database — PostgreSQL + PostGIS as primary, plus object storage for rasters

- **PostGIS** is the obvious choice the moment you have polygons (slick GeoJSON), point clouds (particle positions), and trajectories (AIS tracks/splines) that need spatial queries — `ST_DWithin`, `ST_Intersects`, etc. map directly onto FR-11 ("query AIS within `μ_p ± 3Σ_p`") and FR-7's polygon geometry needs. A generic relational DB or NoSQL store would force a poor reimplementation of spatial indexing.
- **TimescaleDB extension on the same Postgres** for the AIS time-series data (Type 1–3 position reports arrive as a dense time series per MMSI) — keeps you on one database instead of standing up a separate time-series store, and Timescale's hypertables handle the cubic-spline interpolation source data efficiently at AIS volumes.
- **Object storage** (S3-compatible — AWS S3, or MinIO if self-hosted/on-prem for sovereignty reasons) for the actual Sentinel-1 GRD tiles, CMEMS/ERA5 NetCDF files, and generated PDF dossiers — these are large binary/raster assets that don't belong in Postgres rows.
- **Redis** doubles as the Celery broker and a cache for hot AHP-weight configs / in-progress job status.

---

## 5. Deployment — Containerized microservices on Kubernetes (or a lighter-weight equivalent for MVP)

- **Docker Compose** for Phases 0–4 of the build (PRD Section 16) — while the team is iterating on the segmentation model, hindcasting engine, and scoring logic, you don't need Kubernetes complexity yet; Compose gets FastAPI + Postgres/PostGIS + Redis + Next.js running consistently across developer machines, staging, and early integration testing.
- Migrate to **Kubernetes** (self-managed or a managed offering) once the system moves into Phase 5–6 (hardening and field trial) and needs to run continuously against live data rather than fixture data, because:
  - The segmentation (C1) and hindcasting (C7) workloads are GPU/CPU-heavy and bursty (triggered per incident) — K8s lets you autoscale those as separate deployments/jobs from the always-on API and frontend, rather than over-provisioning a fixed VM for peak load.
  - A government/defense-adjacent NTRO deployment will require **on-prem or sovereign cloud** (e.g., a domestic Indian cloud provider or on-prem data center) rather than public hyperscaler SaaS, given the sensitivity of EEZ surveillance and vessel-attribution data — Kubernetes is cloud-agnostic and portable to that environment, whereas leaning on Vercel/AWS-specific serverless would lock the project out of that requirement later.
  - Treat this migration as a planned milestone on the roadmap, not a rewrite done under pressure — provision the target Kubernetes environment (or at least validate access to it) well before Phase 6, since sovereign/on-prem infrastructure procurement can itself take longer than the software work.
- **Next.js frontend**: Vercel is fine for early internal builds and stakeholder demos (zero-config, instant iteration), but plan to containerize it (Next.js supports standalone Docker output out of the box) for the sovereign/on-prem deployment — this is a configuration change, not a rewrite, as long as the app avoids Vercel-specific APIs from day one.
- **CI/CD**: GitHub Actions is sufficient at this scale — build/test the FastAPI services and Next.js app, push images, and deploy to whichever environment (Compose host or Kubernetes cluster) is current for that phase.

---

## 6. Open Tension to Flag

The PRD's stated end use (dossier generation for Coast Guard/DG Shipping legal use — FR-18, FR-20) implies eventual on-prem/sovereign deployment constraints that a pure convenience-first stack (Vercel + hosted Auth0 + public-cloud-only infrastructure) won't ultimately satisfy. Since this is being built for real operational use rather than a one-off demo, the team should decide *now* — not late in the project — whether the target deployment environment is sovereign/on-prem from the start, or public cloud with a planned migration. This decision should be locked in during Phase 0 (Section 16), because it affects the choice of identity provider, object storage, and cluster tooling early enough that later phases aren't built against assumptions that have to be unwound.

---

*End of Document*
