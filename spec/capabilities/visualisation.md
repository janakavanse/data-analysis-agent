# Capability: Visualisation

## What & why

A user requests a chart or visualisation in natural language (e.g., "show revenue by region as a bar
chart"). The agent runs the appropriate SELECT query to get the data, then calls `generate_chart` to
produce a Plotly JSON chart spec. The `finish` tool returns the spec in the answer field; the UI detects
the Plotly payload and renders the chart inline in the chat thread without a page reload. Charts are
always user-requested — the agent never auto-generates a dashboard. Serves the "chart request returns
valid Plotly JSON and the UI renders it inline" success criterion in `spec/product.md`.

## Acceptance criteria (EARS — these ARE the eval inputs)

- WHEN the user requests a chart or visualisation the system SHALL call `query_dataset` to obtain the underlying data, call `generate_chart` to produce a Plotly JSON spec, and return the spec in the `finish` answer field with a non-empty `data` array and a `type` field on each trace.
- WHEN the agent returns a Plotly JSON spec the system SHALL include a human-readable prose description of the chart (title, axes, what the chart shows) alongside the JSON so the user understands the visualisation before it renders.
- WHILE in a multi-turn session WHEN the user asks to refine a previously generated chart (e.g., "make it a line chart instead") the system SHALL regenerate the chart spec using the same query results and return a new Plotly JSON spec reflecting the requested change.
- IF the requested chart type is not supported by Plotly (e.g., an unrecognised chart name) THEN the system SHALL suggest the closest supported Plotly chart type and generate that instead, noting the substitution in the prose.
- IF the query underlying the chart returns zero rows THEN the system SHALL NOT generate a chart spec and SHALL instead return a message explaining that there is no data to visualise.

## Tools & layers touched

- tool: `query_dataset`  (in-process @tool — runs the SELECT that feeds the chart)
- tool: `generate_chart`  (in-process @tool — accepts column names + data rows + chart type, returns Plotly JSON spec)
- tool: `finish`  (in-process @tool — returns the Plotly JSON spec in the answer field)
- layers: Guardrails (`on_tool_call` hook; query_dataset still blocks non-SELECT SQL) — `harness/patterns/guardrails-and-hitl.md`
- layers: Context engineering (active dataset schema in context so the model maps column names to chart axes) — `harness/patterns/context-engineering.md`

## Evaluation

- outcome evaluation_steps:
  - Does the answer field contain a JSON object with a non-empty `data` array (Plotly trace list)?
  - Does each trace in `data` have a `type` field matching a valid Plotly trace type (e.g., `bar`, `scatter`, `pie`)?
  - Does the answer also include a prose description naming the chart type, the x/y axes or dimensions, and what the chart shows?
  - When the data is empty, does the answer explain there is nothing to visualise rather than returning a malformed or empty chart spec?
- expect_tools: [query_dataset, generate_chart, finish]
- forbid_tools: []

## Notes

- The `generate_chart` tool signature: `generate_chart(chart_type: str, columns: list[str], rows: list[dict], title: str) -> dict` — returns a Plotly-compatible dict with `data` (list of traces) and `layout` keys.
- Supported chart types to begin with: `bar`, `line` (scatter with mode=lines), `scatter`, `pie`, `histogram`. Map user phrasing to these; substitute the nearest type for unrecognised names.
- The answer field produced by `finish` must be a JSON string (or a dict that the server serialises) containing both a `chart_spec` key (the Plotly dict) and a `summary` key (the prose description). The UI reads `answer.chart_spec` to decide whether to render a chart.
- Chart prompts are user-driven only — the agent must not proactively generate charts unless asked. Chart suggestions (one-click affordances based on schema) are a UI concern, not an agent behaviour.
- Out of scope for this capability: static image export, chart theming beyond Plotly defaults, compound multi-chart layouts, live-refreshing charts.
