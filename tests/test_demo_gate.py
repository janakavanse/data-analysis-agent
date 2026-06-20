"""Demo gate test — runs with real LLM key; skipped when key is fake/absent."""
import os
import pytest
import csv
import tempfile

from agent.db import init_db
from agent.evals import outcome_eval, trajectory_eval
from agent.runner import run_agent

CRITERION = (
    "WHEN the user sends a natural-language question about an active dataset "
    "the system SHALL generate a valid SQL SELECT statement, execute it, "
    "and return a formatted answer derived from the actual result rows."
)
EVALUATION_STEPS = [
    "Does the answer reference actual data values from the dataset?",
    "Is it a direct, relevant response to the question?",
    "Does it avoid inventing data not in the dataset?",
]


def _has_real_key():
    key = os.environ.get("APP_LLM_API_KEY", "")
    return bool(key) and key != "fake-key-for-tests"


@pytest.mark.asyncio
@pytest.mark.skipif(not _has_real_key(), reason="No real APP_LLM_API_KEY — skipping live gate test")
async def test_demo_gate():
    await init_db()

    # Create a small CSV fixture for the gate
    with tempfile.NamedTemporaryFile(suffix=".csv", mode="w", delete=False, newline="") as f:
        writer = csv.writer(f)
        writer.writerow(["product", "revenue", "region"])
        writer.writerow(["Widget A", 1500, "North"])
        writer.writerow(["Widget B", 2300, "South"])
        writer.writerow(["Widget C", 800, "North"])
        tmp_path = f.name

    # Upload the dataset
    from agent.tools import upload_dataset
    upload_result = await upload_dataset.ainvoke({"file_path": tmp_path, "name": "gate_dataset"})
    assert "dataset_id" in upload_result, f"Upload failed: {upload_result}"

    dataset_id = None
    for line in upload_result.splitlines():
        if line.startswith("dataset_id:"):
            dataset_id = line.split(":", 1)[1].strip()
            break
    assert dataset_id, "Could not extract dataset_id from upload result"

    import os as _os
    _os.unlink(tmp_path)

    goal = "What are the total revenues by region in the gate_dataset?"
    result = await run_agent(goal, dataset_id=dataset_id, run_id="gate-run-1")

    assert result["answer"], "Agent must return an answer"

    ok_o, score, _ = await outcome_eval(
        goal=goal,
        answer=result["answer"],
        criterion=CRITERION,
        evaluation_steps=EVALUATION_STEPS,
    )
    ok_t, reasons = await trajectory_eval(
        "gate-run-1",
        expect_tools=["query_dataset"],
        forbid_tools=[],
    )

    assert ok_o, f"OUTCOME FAILED: score {score} < 4"
    assert ok_t, f"TRAJECTORY FAILED: {reasons}"
