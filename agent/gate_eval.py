import argparse
import asyncio
import sys
from sqlalchemy import select
from .db import get_sessionmaker, Run
from .evals import stable_outcome_eval, trajectory_eval

CRITERION = "WHEN the user provides a document and asks a question answerable from it the system SHALL answer with the correct fact, grounded in the document's content."
EVALUATION_STEPS = [
    "PRIMARY: the question asks how many paid vacation days full-time employees get per year; the document says 20. Does the answer clearly state 20? Score 5 if it states 20, 0 if a different number or no number.",
    "Is the answer on-topic and free of invented policies or numbers? Score 5 if clean, 0 if it fabricates facts.",
]
EXPECT_TOOLS = ["search_document"]
FORBID_TOOLS = []

SAMPLES, THRESHOLD, MARGIN = 5, 3, 0.5


async def main(run_id: str, goal: str) -> int:
    async with get_sessionmaker()() as s:
        run = (await s.execute(select(Run).where(Run.id == run_id))).scalar_one()
    outcome_ok, mean, detail = await stable_outcome_eval(
        goal, run.answer, CRITERION, EVALUATION_STEPS,
        threshold=THRESHOLD, samples=SAMPLES, margin=MARGIN)
    ok_t, reasons = await trajectory_eval(run_id, expect_tools=EXPECT_TOOLS, forbid_tools=FORBID_TOOLS)
    print(f"OUTCOME scores={detail['scores']} mean={mean:.2f} spread={detail['spread']} "
          f"(need mean>={THRESHOLD - MARGIN})", file=sys.stderr)
    if not outcome_ok:
        print("OUTCOME FAIL: below threshold-with-margin or unstable", file=sys.stderr)
    if not ok_t:
        print(f"TRAJECTORY advisory (not blocking until a 2nd capability): {reasons}", file=sys.stderr)
    return 0 if outcome_ok else 1


if __name__ == "__main__":
    p = argparse.ArgumentParser()
    p.add_argument("--run-id", required=True)
    p.add_argument("--goal", required=True)
    a = p.parse_args()
    sys.exit(asyncio.run(main(a.run_id, a.goal)))
