# Capability: <!-- FILL IN: name -->

> Copy this file to `spec/capabilities/<slug>.md` (one capability per file). Filled by the **spec-writer**;
> the acceptance criteria below ARE the eval inputs. Contract + procedure: `harness/harness.md`,
> `harness/workflows/spec-new-capability.md`. Leave the `<!-- FILL IN -->` markers until completed.

## What & why
<!-- FILL IN: one paragraph — the user-visible behaviour and how it serves a success criterion in
spec/product.md. One capability = one user-visible behaviour; split it if it needs two. -->

## Acceptance criteria (EARS — these ARE the eval inputs)
<!-- FILL IN: each line is testable and observable. WHEN = trigger, SHALL = response. Use WHILE for state,
IF for an unwanted condition. Each line maps to one outcome + one trajectory assertion. -->
- WHEN <trigger> the system SHALL <observable response>.
- WHILE <state> WHEN <trigger> the system SHALL <response>.
- IF <unwanted condition> THEN the system SHALL <safe response>.

## Tools & layers touched
<!-- FILL IN: cheapest tool layer that works — patterns/tools-and-mcp.md § 3-layer model. Only list a
layer that is (or is now being turned) ON in spec/agent.md; never silently enable one. -->
- tool: <name>  (in-process @tool | MCP for external — `harness/patterns/tools-and-mcp.md`)
- layers: <e.g. retrieval ON — `harness/patterns/retrieval.md`>   # omit if none beyond the base loop

## Evaluation
<!-- FILL IN: feeds the mechanical gate — harness/patterns/observability-and-evals.md. -->
- outcome evaluation_steps:  # 2–4 rubric bullets the LLM-judge scores 0–5 against (no vibes)
  - <bullet 1>
  - <bullet 2>
- expect_tools: [<tool that MUST fire>]
- forbid_tools: [<mutating/irreversible tool that must NOT fire ungated>]

---

## Worked example (delete when filling in)

# Capability: Answer from the docs

## What & why
A user asks a question about the product's documentation and gets a grounded answer with no invented facts.
Serves the "accurate, cited answers" success criterion in `spec/product.md`.

## Acceptance criteria (EARS — these ARE the eval inputs)
- WHEN the user asks a question covered by the docs the system SHALL answer using only retrieved passages.
- WHILE no passage matches WHEN the user asks the system SHALL say it doesn't know rather than guess.
- IF the question requests a destructive action THEN the system SHALL refuse and explain why.

## Tools & layers touched
- tool: search_docs  (in-process @tool — `harness/patterns/tools-and-mcp.md`)
- layers: retrieval ON — `harness/patterns/retrieval.md`

## Evaluation
- outcome evaluation_steps:
  - The answer is supported by the retrieved passages and invents no facts.
  - When nothing matches, the answer admits it doesn't know.
- expect_tools: [search_docs]
- forbid_tools: [finish]   # finish must not fire before search_docs runs
