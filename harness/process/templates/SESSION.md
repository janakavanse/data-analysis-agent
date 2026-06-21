# Session Report — YYYY-MM-DD — [branch]

**Started:** YYYY-MM-DD HH:MM  
**Branch:** feature/...  
**FR/CR:** FR-NNN — [title]  
**Current phase:** Phase N — [goal]

---

## API Keys

| Key | Present |
|-----|---------|
| <!-- e.g. OPENAI_API_KEY --> | yes / no |

---

## Phase Plan

| Phase | Goal | Gate command | Status |
|-------|------|-------------|--------|
| 1 | Domain models + data layer | `uv run pytest tests/unit/` | pending |
| 2 | Core loop (stubbed) | `uv run pytest && curl http://localhost:8001/health` | pending |
| ... | | | |

---

<!-- Each agent appends a new section using the format below. -->
<!-- Stamp start/end from the host clock: `date '+%Y-%m-%d %H:%M:%S'` (non-negotiable #12). -->
<!-- ────────────────────────────────────────────────────────── -->

## [Stage] — [Agent name]

**Start:** YYYY-MM-DD HH:MM:SS  
**End:** YYYY-MM-DD HH:MM:SS  
**Duration:** Nm Ns

### Decisions
<!-- What was decided and why. One bullet per decision. -->
-

### Gate result
```
$ <command run>
<output>
```
**Result:** ✓ pass / ✗ fail

### Blockers / open questions
<!-- Anything unresolved that the next agent or human must address. -->
-

### What is next
<!-- One sentence: what the next agent or step should do. -->

---
