# AEGIS-Marine — Project Rules (rules.md)

**Purpose:** This is the constitution for any AI assistant (Claude, Claude Code, Copilot, or otherwise) working on the AEGIS-Marine codebase. It governs *how* work gets done, not *what* gets built — for the "what," always defer to the source-of-truth documents below. When this file and a source-of-truth document disagree, the source-of-truth document wins for product/architecture decisions; this file wins for process, style, and conduct.

**Source-of-truth documents (read before making non-trivial changes):**
- `AEGIS-Marine_PRD.md` — goals, user stories, functional/non-functional requirements, success metrics
- `AEGIS-Marine_Architecture.md` — service decomposition, data contracts, API surface, deployment topology
- `AEGIS-Marine_Tech_Stack_Recommendation.md` — approved technology choices and justification

If a task requires deviating from any of these three documents, stop and flag the deviation explicitly rather than silently implementing something different — see Section 9.

---

## 1. Non-Negotiable Product Rules

These come directly from the PRD's Guiding Principles (Section 17) and are **hard constraints**, not style preferences. Code review (human or AI) must reject any change that violates them, regardless of how small the change seems.

1. **Never assert certainty the evidence doesn't support.** Any API response, database record, or UI element that presents a detection, an origin estimate, or a vessel score MUST include an accompanying confidence/uncertainty field. A PR that adds a new score or estimate without a paired confidence value is incomplete.
2. **Explainability is structural, not cosmetic.** The scoring engine (Tier 4) must persist its sub-scores (`spatial`, `temporal`, `kinematic`, `anomaly`, `type`) and evidence references as stored fields, not values computed on-the-fly in the frontend. Never "explain" a score by reverse-engineering plausible reasons after the fact.
3. **The nearest vessel is not automatically the source.** Do not implement, suggest, or default to distance-only ranking anywhere in the codebase, including debug tooling, admin panels, or "quick" scripts. If a shortcut version of the scoring engine is needed for testing, it must still combine at least spatial + temporal signals and must be clearly labeled as a test/mock scorer, never surfaced to an end user.
4. **Silence is not evidence of innocence.** Code must never silently exclude vessels with AIS transponder gaps or no AIS at all. They must be flagged (`ais_coverage: "dark_gap" | "non_ais_unknown"`) and surfaced, per FR-19.
5. **Always consider the alternative.** Any case-completion code path must ensure the Alternative Explanation Engine has run and produced at least one non-vessel hypothesis (natural seep, imaging artifact) before a case is marked `ready`, even if that hypothesis scores near zero.
6. **Language matters — enforce it in code, not just copy review.** The following terms are **banned** in any user-facing string (UI copy, PDF dossier templates, API error messages, notification text): "responsible vessel," "guilty," "polluter" (as a determination rather than a category label), "proven," "confirmed the culprit." Approved phrasing: "most correlated vessel," "candidate suspect," "potential source." Add/maintain a lint check or string-constant registry that fails CI if banned terms are introduced.
7. **Show your math.** The AHP pairwise comparison matrix, derived weights, and consistency ratio must always be available via `GET /ahp-config` and must never be hardcoded inline in the scoring function without also being exposed through this endpoint.

---

## 2. Technology Stack Constraints

The stack in `AEGIS-Marine_Tech_Stack_Recommendation.md` is approved and should be treated as fixed unless a documented architectural decision changes it (see Section 9). Specifically:

- **Backend:** Python + FastAPI. Do not introduce a second backend language/framework for new services without an explicit ADR (Section 9) — the PRD's core modules (segmentation, hindcasting, AIS correlation) depend on Python-only scientific libraries (PyTorch, OpenDrift/OpenOil, GeoPandas), and fragmenting the backend increases integration risk for no benefit.
- **Frontend:** Next.js (App Router) + MapLibre GL + deck.gl + Tailwind/shadcn. Do not swap MapLibre for Mapbox GL (licensing) or deck.gl for a lower-performance charting library for anything touching particle/AIS visualization (performance NFR: 10,000+ points at 60 FPS).
- **Database:** PostgreSQL + PostGIS + TimescaleDB extension. Do not introduce a second database technology for spatial or time-series data without an ADR — this fragments the data platform and duplicates operational burden.
- **Job orchestration:** Celery + Redis for all async/long-running work (segmentation inference, particle simulation, AIS correlation, dossier generation). Do not implement ad hoc background threads or cron scripts for pipeline stages — they bypass the task-chain idempotency and progress-reporting the "what-if" feature and replay UI depend on.
- **Auth:** OIDC via Auth.js in the frontend, JWT validation in FastAPI. Do not implement custom session/token logic.
- **Deployment:** Docker Compose during active development phases (PRD Phases 0–4); Kubernetes from Phase 5 onward. Any new service must ship with both a Compose service definition and a Kubernetes manifest/Helm chart entry before being considered complete.

Introducing a new library, framework, or infrastructure component that isn't in the tech stack doc requires updating that document (with justification, following its existing format) as part of the same change — not as a follow-up.

---

## 3. Coding Standards

### 3.1 Python (backend services)
- Python 3.12+, fully type-hinted. Pydantic models for every API request/response and every inter-service data contract described in `AEGIS-Marine_Architecture.md` Section 6.
- Formatting/linting: `ruff` (format + lint) and `mypy` for type checking; both must pass in CI before merge.
- Every FastAPI endpoint must have a docstring and a corresponding entry in the OpenAPI schema (FastAPI generates this automatically — do not disable it).
- Scientific/physics code (Fay spreading inversion, OpenDrift wrappers, AHP scoring) must include inline comments citing the corresponding formula/section number from `AEGIS-Marine_PRD.md` Section 10, so the code and the documented math never silently drift apart.
- No bare `except:` blocks. Failures in external data adapters (Copernicus, CMEMS, AIS feeds) must be caught specifically and routed to the documented fallback path (Architecture doc Section 12), with the degradation logged — never fail silently and never crash the whole pipeline for one adapter's failure.

### 3.2 TypeScript / Frontend
- TypeScript strict mode. No `any` without an inline comment justifying it.
- Components consuming map/particle data must use the typed data contracts matching the backend's Pydantic schemas (generate types from the OpenAPI spec rather than hand-maintaining a parallel type definition).
- Tailwind utility classes only for styling (per the approved stack); no ad hoc CSS files or CSS-in-JS libraries introduced without an ADR.
- Any new UI element displaying a score or estimate must render its confidence/uncertainty alongside it — this is a direct extension of Product Rule 1 into the frontend layer.

### 3.3 General
- No hardcoded secrets, API keys, or credentials anywhere in the repository, including test fixtures and comments. Use environment variables / the secrets manager referenced in the Architecture doc's Security section.
- No commented-out blocks of dead code left in merged PRs.
- Every new module/service must include a `README.md` describing its input/output contract, consistent with its entry in the Architecture doc.

---

## 4. Scientific & Data Integrity Rules

- **Formulas are not to be approximated or "simplified" without sign-off.** The Fay spreading-age inversion, drift-velocity composition, KDE origin estimation, and AHP scoring formulas in the PRD (Section 10) are the specification. If a numerically simpler approximation is used for performance reasons, it must be documented as an approximation with its expected error bound, not silently substituted.
- **Real vs. synthetic data must always be distinguishable.** Every `SlickDetection`, `OriginEstimate`, and `AISTrack` record must carry a `data_source: "live" | "cached" | "synthetic"` field. Never merge synthetic and live data into a single unlabeled dataset — this is essential both for the responsible-use rules (Section 1) and for anyone auditing a case later.
- **Model and configuration versioning is mandatory.** Any change to the segmentation model weights, the AHP pairwise comparison matrix, or the OpenDrift physical parameters (wind-drift factor, diffusivity, etc.) must be versioned, and every downstream record produced using that version must store the version identifier (per Architecture doc Section 11). Do not overwrite a model/config "in place" without a version bump.
- **Validation targets are gates, not aspirations.** Before a Tier 1/2/3/4 change is merged, it must be checked against the relevant validation metric from the PRD's Empirical Validation Strategy (Section 14) — e.g., a segmentation model change must not regress mIoU below 82.5% on the CSIRO/DARTIS benchmark. If a change knowingly regresses a metric, that must be called out explicitly in the PR description, not discovered later.

---

## 5. Security & Access Control Rules

- Enforce RBAC (`investigator`, `analyst`, `legal_reviewer`, `admin`) at the API layer for every endpoint, per Architecture doc Section 10 — never rely on the frontend to hide an action as the only access control.
- Every case-state transition, dossier export, and what-if override must write an audit-log entry (user, timestamp, action, case ID). Do not add a new mutating endpoint without also adding its audit-log write.
- Object storage (SAR tiles, dossiers, model checkpoints) access must go through the backend, never expose direct signed URLs to raw AIS or vessel-identity data to an unauthenticated or under-privileged client.
- Any new external integration (a new data provider, a new notification channel) must be evaluated for whether it exposes vessel-identity or investigator-identity data outside the system's security boundary, and flagged for human review if it does.

---

## 6. API & Data Contract Rules

- New or modified endpoints must match the shapes defined in `AEGIS-Marine_Architecture.md` Section 7 (API Surface) and Section 6 (Data Model). If a task requires a new endpoint or field not listed there, update the Architecture doc in the same change.
- Breaking changes to an existing data contract require a version bump on the affected endpoint (e.g., `/v2/cases/{id}/vessels`) rather than silently changing the response shape of `/v1`.
- All geospatial data in transit and at rest uses GeoJSON (WGS84 / EPSG:4326) at the API boundary, converting to local UTM only internally for computation, per the Architecture doc's Tier 1 preprocessing description.

---

## 7. Testing Requirements

- Every new backend function that implements a formula from PRD Section 10 needs a unit test with a hand-computed or reference-checked expected value — not just a "does it run without error" test.
- Every Celery task must have a test verifying its fallback path (synthetic/cached data) is triggered correctly when the live adapter raises the documented exception type.
- Any change to the AHP scoring engine must include a test asserting the consistency ratio (`CR`) computation still returns `< 0.10` for the approved weight matrix, and must fail CI if it doesn't.
- Frontend components rendering scores/estimates must have a test asserting the confidence/uncertainty value is present in the rendered output (enforcing Product Rule 1 at the component level).

---

## 8. Git & PR Conventions

- Branch naming: `tier1/…`, `tier2/…`, `tier3/…`, `tier4/…`, `explain/…`, `ui/…`, `infra/…` prefixed by the component it touches, matching the Architecture doc's component boundaries.
- Commit messages reference the PRD requirement ID or Architecture section being implemented where applicable (e.g., `FR-14: implement AHP-weighted composite scoring`).
- PR descriptions must state: (a) which PRD/Architecture section this implements or changes, (b) whether any validation metric was checked and its result, (c) whether any of the source-of-truth documents need updating as a result.
- No direct commits to `main`; all changes via PR with at least one review (human or a designated AI review pass) before merge.

---

## 9. When to Stop and Ask (Escalation Rules)

An AI assistant working on this repo must pause and surface the issue to a human rather than proceeding, when:

- A task appears to require violating any rule in Section 1 (Non-Negotiable Product Rules).
- A task requires introducing a technology outside the approved stack (Section 2) without an existing ADR covering it.
- A task would change a formula or physical constant from PRD Section 10 without an explicit instruction to do so.
- A task's requirements conflict between the PRD, Architecture doc, and this rules file — do not silently pick one; report the conflict.
- A validation metric (Section 4) would regress as a result of the change and no one has explicitly accepted that trade-off.
- A change would touch authentication, RBAC enforcement, or audit logging in a way that could weaken access control (Section 5) — these changes always need explicit human sign-off, regardless of how small they look.

When escalating, state clearly: what was asked, what rule/document it conflicts with, and what the options are — do not just refuse silently or guess.

---

## 10. Keeping This Document (and Its Companions) in Sync

This file, the PRD, the Architecture doc, and the Tech Stack doc are a linked set. A change that affects one often affects another:

| If you change... | Also check/update... |
|---|---|
| A functional requirement or success metric | `AEGIS-Marine_PRD.md` |
| A service boundary, data contract, or API shape | `AEGIS-Marine_Architecture.md` |
| A library, framework, or infrastructure choice | `AEGIS-Marine_Tech_Stack_Recommendation.md` |
| A process, coding standard, or non-negotiable rule | `rules.md` (this file) |

Do not let implementation drift silently away from these documents. If code and documentation disagree, that is itself a bug to fix — either the code is wrong, or the documentation is stale and needs updating in the same PR.

---

*End of Document*
