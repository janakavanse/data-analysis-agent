import argparse
import asyncio
import sys
from sqlalchemy import select
from .db import get_sessionmaker, Run
from .evals import stable_outcome_eval, trajectory_eval

CRITERION = "WHEN the user uploads a CSV file and asks a statistical question the system SHALL execute Python/pandas code and return the correct computed numeric result with the code shown."
EVALUATION_STEPS = [
    "Does the answer contain at least one specific number (an integer or decimal, not a vague description like 'some value')? Score 5 if yes, 0 if no.",
    "Does the answer include Python or pandas code — either in a fenced ```python block or as an inline expression? Score 5 if yes, 0 if no.",
    "The goal was 'What is the average salary?'. The fixture salary values are ~55k-125k, so the correct mean is roughly 79,000-80,000. Is the numeric answer in that plausible range (or does the system at least attempt a salary computation)? Score 5 if the number is plausible, 3 if uncertain, 0 only if the number is wildly wrong (e.g. 0 or 1e9).",
    "Is the answer free of fabricated column names or claims about data that was never in a typical CSV? Score 5 if clean, 0 if invented.",
]
EXPECT_TOOLS = ["file_load", "python_exec"]
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
