# Roadmap — the full product vision beyond FR-1

Users express bigger visions than a single FR can build. This file holds the whole picture —
populated by the researcher at intake from the user's brief — so nothing gets lost and every
future FR has a clear place in the product arc. FR-1 is the first shaped release; this roadmap
is everything it points toward.

**Two tiers:**

| Tier | Use when | Format |
|------|----------|--------|
| **`proposed` FR** | The idea is concrete enough to spec now — it has a clear deliverable, users, and testable criteria. Author the full FR with status `proposed`; it enters the pipeline when the user promotes it to `approved` after testing the core. | `spec/features/FR-NNN-title.md` with `Status: proposed` |
| **Roadmap entry (here)** | The idea is real but not yet concrete enough to spec — a direction, a capability class, a "what if". Park it here so it isn't lost; promote to a `proposed` FR when it crystallises. | A row in the table below |

---

## Parked ideas

> Add a row here whenever scope is split out of a core FR and isn't concrete enough for a full
> `proposed` FR yet. Format: what the idea is, which FR it came from, and why it was deferred.

| Idea | Source FR | Why deferred | Ready to FR? |
|------|-----------|-------------|--------------|
| <!-- e.g. Multi-tenant auth --> | <!-- FR-001 --> | <!-- outside 30-min ceiling; not critical for first delight --> | <!-- no / yes → FR-002 --> |

---

## Proposed FRs (approved queue)

> FRs with status `proposed` — fully specced, waiting for user approval after the core ships.
> The supervisor surfaces these after each core delivery.

| FR | Title | Depends on | Status |
|----|-------|-----------|--------|
| <!-- FR-002 --> | <!-- --> | <!-- FR-001 done + user accepted --> | <!-- proposed --> |
