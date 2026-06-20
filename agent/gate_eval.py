"""CLI gate evaluator — exit 0 iff the run's answer is correct AND the trajectory is sane."""
import argparse
import asyncio
import sys

from sqlalchemy import select

from .db import Run, get_sessionmaker, init_db
from .evals import outcome_eval, trajectory_eval

# Natural-language-query capability EARS criterion
CRITERION = (
    "WHEN the user sends a natural-language question about an active dataset "
    "the system SHALL generate a valid SQL SELECT statement, execute it, "
    "and return a formatted answer derived from the actual result rows."
)
EVALUATION_STEPS = [
    "Does the answer reference actual data values (rows, numbers, or column values) from the dataset?",
    "Is the answer a direct response to the question asked (not a generic or empty response)?",
    "Does the answer avoid inventing data not in the dataset?",
    "Is the answer well-formatted (table, list, or clear prose)?",
]
EXPECT_TOOLS = ["query_dataset"]
FORBID_TOOLS = []


async def main(run_id: str, goal: str) -> int:
    await init_db()
    async with get_sessionmaker()() as s:
        run = (await s.execute(select(Run).where(Run.id == run_id))).scalar_one_or_none()
    if run is None:
        print(f"GATE FAIL: run {run_id} not found", file=sys.stderr)
        return 1

    ok_o, score, _ = await outcome_eval(goal, run.answer or "", CRITERION, EVALUATION_STEPS)
    ok_t, reasons = await trajectory_eval(run_id, expect_tools=EXPECT_TOOLS, forbid_tools=FORBID_TOOLS)

    if not ok_o:
        print(f"OUTCOME FAIL: score {score} < threshold 4", file=sys.stderr)
    if not ok_t:
        print(f"TRAJECTORY FAIL: {reasons}", file=sys.stderr)

    return 0 if (ok_o and ok_t) else 1


if __name__ == "__main__":
    p = argparse.ArgumentParser()
    p.add_argument("--run-id", required=True)
    p.add_argument("--goal", required=True)
    a = p.parse_args()
    sys.exit(asyncio.run(main(a.run_id, a.goal)))
