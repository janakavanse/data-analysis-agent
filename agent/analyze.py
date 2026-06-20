"""Reconciliation check (deterministic, no LLM): does the spec reconcile with the code?

Two coverage gates: (1) every EARS criterion is bound to a real, collectable test
(via eval_lint); (2) every capability's `targets:` glob matches >=1 existing code file
(so the spec names code that actually exists). Exit 0 iff spec and code reconcile.
This is the `/analyze` coverage check condensed from the SDD field (Spec Kit) — the
deterministic floor under 'code is truth; the spec stays reconciled to it'."""
import glob
import re
import sys
from pathlib import Path

from . import eval_lint


def _targets_problems() -> list[str]:
    probs: list[str] = []
    for f in sorted(Path("spec/capabilities").glob("*.md")):
        m = re.search(r"^targets:\s*(.+)$", f.read_text(), re.MULTILINE)
        if not m:
            continue
        globs = re.findall(r"[`\"']([^`\"']+)[`\"']", m.group(1)) or \
            [g.strip() for g in m.group(1).strip("[]").split(",") if g.strip()]
        for g in globs:
            if not glob.glob(g):
                probs.append(f"{f.name}: `targets:` glob matches no file: {g}")
    return probs


def main() -> int:
    problems: list[str] = []
    if eval_lint.main() != 0:
        problems.append("eval_lint failed — an EARS criterion is unbound or its [@eval] is unresolved")
    problems += _targets_problems()
    for p in problems:
        print(f"ANALYZE FAIL: {p}", file=sys.stderr)
    if not problems:
        print("analyze: spec ↔ code reconciled ✓")
    return 1 if problems else 0


if __name__ == "__main__":
    sys.exit(main())
