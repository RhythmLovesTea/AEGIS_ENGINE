# AEGIS-Marine — Architecture Decision Records (ADR)

**Purpose:** This file is the mechanism referenced by `rules.md` (Sections 2 and 9) and `AEGIS-Marine_Tech_Stack_Recommendation.md` for approving any deviation from the approved stack, a service boundary in `AEGIS-Marine_Architecture.md`, or a non-negotiable rule's implementation detail. No stack substitution, new infrastructure component, or cross-cutting technical decision should happen without a corresponding entry here.

**When an ADR is required** (per `rules.md` Section 2 and Section 9):
- Introducing a technology, library, or framework not already named in the Tech Stack doc.
- Changing a service boundary or data contract defined in the Architecture doc in a way that isn't a simple additive field.
- Any decision that a future engineer (or AI) would reasonably ask "wait, why did we do it this way?" about.

**When an ADR is *not* required:** routine implementation choices within an already-approved technology (e.g., which Pydantic validator to use, which Tailwind spacing scale) — use normal code review for those.

**Process:**
1. Copy the template in Section A below into a new numbered entry in Section B (Log).
2. Set status to `Proposed`.
3. Get human sign-off (per `rules.md` Section 9 — stack/architecture deviations always need explicit human approval).
4. Update status to `Accepted`, `Rejected`, or `Superseded by ADR-XXX`.
5. If accepted, update the affected source-of-truth document (PRD / Architecture / Tech Stack) in the **same change**, per `rules.md` Section 10.

---

## A. ADR Template

```
### ADR-NNN: <short decision title>

**Date:** YYYY-MM-DD
**Status:** Proposed | Accepted | Rejected | Superseded by ADR-XXX
**Deciders:** <names/roles>
**Affected documents:** <e.g., Tech Stack Recommendation Section 2, Architecture Section 4.3>

**Context**
What problem or constraint is forcing this decision? What triggered it (a limitation
discovered during implementation, a new requirement, a performance issue)?

**Options Considered**
1. <Option A> — pros / cons
2. <Option B> — pros / cons
3. <Option C, if any> — pros / cons

**Decision**
Which option was chosen, and why — tie this back to specific PRD requirements or
NFRs where possible (e.g., "chosen because it preserves the 10,000-particle @ 60fps
rendering NFR").

**Consequences**
- What becomes easier as a result?
- What becomes harder, or what new risk/debt does this introduce?
- What existing rule, component, or document does this require updating?

**Rule/Document Updates Required**
- [ ] rules.md
- [ ] AEGIS-Marine_PRD.md
- [ ] AEGIS-Marine_Architecture.md
- [ ] AEGIS-Marine_Tech_Stack_Recommendation.md
- [ ] None — purely additive, no conflict with existing docs
```

---

## B. ADR Log

> Entries are added here in ascending numeric order and are never deleted, even if superseded — mark superseded entries as such rather than removing them, so the history of *why* a decision changed stays intact.

### ADR-001: Example — Adopting this ADR process itself

**Date:** 2026-09-05
**Status:** Accepted
**Deciders:** Project team
**Affected documents:** rules.md (Sections 2, 9)

**Context**
`rules.md` and the Tech Stack doc both required an "ADR process" as the mechanism for approving stack or architecture deviations, but no such mechanism existed yet — the rule referenced a process with no defined shape.

**Options Considered**
1. Lightweight single Markdown file with a template + running log (this file) — low overhead, version-controlled alongside the code, easy to diff and review in a normal PR.
2. A dedicated ADR tool (e.g., `adr-tools` generating one file per decision) — more structure, but adds tooling overhead disproportionate to project size.
3. No formal ADR process; rely on PR descriptions alone — rejected because PR descriptions get buried in git history and don't give a single place to see "why is the stack the way it is."

**Decision**
Adopted Option 1 — a single `ADR.md` file with a reusable template and an append-only log — because it matches the project's existing documentation style (plain Markdown, version-controlled, no extra tooling dependency) and is easy for both humans and AI assistants to read and append to correctly.

**Consequences**
- Any future stack or architecture deviation now has a defined place to be recorded and approved, closing the gap `rules.md` had already assumed was closed.
- As the log grows, this file may eventually need splitting by area (backend/frontend/infra) — acceptable future work, not a blocker now.

**Rule/Document Updates Required**
- [x] rules.md — already referenced this process; no further change needed.
- [ ] AEGIS-Marine_PRD.md
- [ ] AEGIS-Marine_Architecture.md
- [ ] AEGIS-Marine_Tech_Stack_Recommendation.md
- [x] None further — this entry documents the process's own creation.

---

*Next entry: ADR-002*
