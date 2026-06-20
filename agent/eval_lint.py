import argparse
import ast
import pathlib
import re
import sys

EARS = re.compile(r"^\s*-?\s*(WHEN|WHILE|IF|WHERE)\b.*\bSHALL\b")
TOKEN = re.compile(r"\[@eval:\s*([^\]:]+)::([^\]]+)\]")

_PLACEHOLDERS = ("WHEN asked about refund timing the system SHALL state 5 business days.",
                 "How long do refunds take?")


def _defined_cases(path: pathlib.Path) -> set:
    cases: set = set()
    try:
        tree = ast.parse(path.read_text())
    except (OSError, SyntaxError):
        return cases
    for node in ast.walk(tree):
        if isinstance(node, (ast.FunctionDef, ast.AsyncFunctionDef)):
            cases.add(node.name)
            for dec in node.decorator_list:
                if (isinstance(dec, ast.Call) and getattr(dec.func, "attr", "") == "parametrize"):
                    for kw in dec.keywords:
                        if kw.arg == "ids" and isinstance(kw.value, (ast.List, ast.Tuple)):
                            for elt in kw.value.elts:
                                if isinstance(elt, ast.Constant) and isinstance(elt.value, str):
                                    cases.add(f"{node.name}[{elt.value}]")
    return cases


def _ears_lines() -> list:
    out = []
    for f in pathlib.Path("spec/capabilities").glob("*.md"):
        if f.name.startswith("_"):
            continue
        for ln in f.read_text().splitlines():
            if EARS.search(ln):
                out.append(re.sub(r"\s*\[@eval:[^\]]*\]", "", ln).strip(" -"))
    return out


def _gate_eval_sync(ears: list) -> list:
    probs = []
    try:
        from . import gate_eval
    except Exception:
        return probs
    crit = getattr(gate_eval, "CRITERION", "").strip()
    if crit in _PLACEHOLDERS:
        probs.append("agent/gate_eval.py CRITERION is still the refund placeholder — set it from the P1 EARS line")
    elif crit and crit not in {e.strip() for e in ears}:
        probs.append(f"agent/gate_eval.py CRITERION does not match any EARS line in spec/capabilities/*: {crit!r}")
    return probs


def main(preflight: bool = False) -> int:
    problems, seen = [], {}
    for f in pathlib.Path("spec/capabilities").glob("*.md"):
        if f.name.startswith("_"):
            continue
        lines = f.read_text().splitlines()
        for i, ln in enumerate(lines):
            if not EARS.search(ln):
                continue
            window = ln + ("\n" + lines[i + 1] if i + 1 < len(lines) else "")
            m = TOKEN.search(window)
            if not m:
                problems.append(f"{f}:{i+1}  EARS line has no [@eval] token")
                continue
            path, case = pathlib.Path(m.group(1).strip()), m.group(2).strip()
            ref = f"{path}::{case}"
            if ref in seen:
                problems.append(f"{f}:{i+1}  [@eval] duplicates {seen[ref]}: {ref}")
            seen[ref] = f"{f}:{i+1}"
            if preflight:
                continue
            if not path.exists():
                problems.append(f"{f}:{i+1}  [@eval] unresolved (no file): {ref}")
                continue
            if case not in _defined_cases(path):
                problems.append(f"{f}:{i+1}  [@eval] unresolved (no collectable case `{case}`): {ref}")
    if not preflight:
        problems += _gate_eval_sync(_ears_lines())
    for p in problems:
        print(f"EVAL-LINT FAIL{' (preflight)' if preflight else ''}: {p}", file=sys.stderr)
    return 1 if problems else 0


if __name__ == "__main__":
    a = argparse.ArgumentParser()
    a.add_argument("--preflight", action="store_true")
    sys.exit(main(a.parse_args().preflight))
