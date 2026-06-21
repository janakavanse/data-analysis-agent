# Reconcile — the closing of the loop

Reconciliation is the practice that makes Zer0 more than a code generator. It is the
continuous check that the **outcome** (`logs/`) matches the **goal** (`spec/`), with
the **action** (`src/`) as the thing adjusted.

## The three truths

- `spec/` — the goal. What the system should be.
- `src/` — the action. What it is, in code.
- `logs/` — the outcome. What it actually does, in reality.

Drift can appear between any pair:

| Drift       | Meaning                          | Default correction                       |
|-------------|----------------------------------|------------------------------------------|
| spec ≠ src  | code doesn't implement the goal  | fix `src/`                               |
| src ≠ logs  | code doesn't behave as written   | fix `src/` (a bug)                       |
| logs ≠ spec | reality doesn't meet the goal    | fix `src/`, or amend `spec/` if the goal was wrong |

## The analyst's standing job

The analyst never stops. It reads runtime logs and traces, test and gate results,
timing and error rates, and the user's prompts, history, and recurring frustrations.
It represents reality and the user back to the team. It decides on its own when to act
and whom to tell (manager, designer, engineer, qa).

Findings are written to `logs/analysis/`. When the outcome diverges from the goal
because the **goal** was wrong, the analyst proposes a concrete `spec/` amendment; qa
and the human approve it. The analyst never silently edits the goal.

## When reconcile runs

At every phase gate, and on any signal the analyst judges material — not on a fixed
schedule. The loop is closed when spec ↔ src ↔ logs agree and the analyst has nothing
outstanding.
