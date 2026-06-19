#!/usr/bin/env python3
"""Generate the host front-ends from the single canonical source (`harness/`).

CLAUDE.md, AGENTS.md, .claude/agents/, .github/agents/, and .claude/commands/ are GENERATED — never edit
them by hand. Edit `harness/` and re-run `python harness/generate.py`. The pre-commit hook checks they are
not stale, so the parallel-harness drift that broke v1 is impossible by construction (decision Q70).
"""
from __future__ import annotations

from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
HARNESS = ROOT / "harness"
BANNER = "<!-- GENERATED from harness/ — do not edit; run `python harness/generate.py` -->\n\n"

ENTRY = BANNER + """# {title}

**First action: read [`harness/harness.md`](harness/harness.md)** — the operating manual. Then read the
spec in `spec/` if it is filled in; otherwise run `/build "<your idea>"`.

## What this repo is
A frontier spec-driven harness that builds a production agentic AI agent from a spec. A coding agent
generates the agent fresh from the recipes in `harness/patterns/` (current library versions), gated by
mechanical checks. Nothing is a frozen app — the harness ships knowledge, not lock-in.

## Map
- `harness/harness.md` — the rules · `harness/workflows/` — procedures (/build, /deploy, …)
- `harness/agents/` — sub-agent roles · `harness/patterns/` — the frontier code recipes (all 11 layers)
- `spec/` — the 4-file input contract you fill · `.githooks/` — mechanical guardrails

A funded `APP_LLM_API_KEY` is required for a real run.
"""


def _write(path: Path, text: str) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(text)
    print("wrote", path.relative_to(ROOT))


def main() -> None:
    _write(ROOT / "CLAUDE.md", ENTRY.format(title="Claude Code — Entry Point"))
    _write(ROOT / "AGENTS.md", ENTRY.format(title="Agents — Entry Point (Codex / Copilot / others)"))

    agents = sorted((HARNESS / "agents").glob("*.md"))
    for dest in (ROOT / ".claude" / "agents", ROOT / ".github" / "agents"):
        for a in agents:
            _write(dest / a.name, BANNER + a.read_text())

    for w in sorted((HARNESS / "workflows").glob("*.md")):
        _write(ROOT / ".claude" / "commands" / w.name, BANNER + w.read_text())

    print(f"generated front-ends from harness/ ({len(agents)} agents)")


if __name__ == "__main__":
    main()
