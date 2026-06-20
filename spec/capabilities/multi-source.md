# Capability: Multi-Source Analysis  ·  Priority: P3

## What & why

A user connects multiple external data sources (Google Sheets, REST APIs, cloud storage) and asks
analytical questions that span or combine them. The agent fetches data from each source, joins or
correlates it, and surfaces a unified insight. This is the P3 vision in `spec/product.md` — deferred
external source integration for cross-source analytical questions. Until promoted from P3 stub status,
this capability is wired into the graph and reachable end-to-end but returns a fixed stub response:
`"Multi-source analysis coming in v3 — external data source connectors (Google Sheets, REST APIs)
will be available once this capability is promoted."` The stub `[@eval]` asserts this fixed contract so
the journey stays green and the capability is registered. Promote via `/spec-new-capability`.

## Acceptance criteria (EARS — these ARE the eval inputs)

- WHEN the user asks about external data source connectivity in v1 the system SHALL return the stub message "Multi-source analysis coming in v3" confirming the feature is registered but not yet active. [@eval: tests/test_multi_source_gate.py::test_multi_source_stub]
- WHILE in stub mode WHEN the user provides an external data source URL or reference the system SHALL acknowledge and return the stub sentinel without making any external HTTP requests. [@eval: tests/test_multi_source_gate.py::test_multi_source_stub_no_http]

## Tools & layers touched

- tool: `multi_source_fetch` (in-process @tool — stub: returns fixed sentinel; real implementation will use MCP adapters for external integrations with OAuth 2.1)
- layers: MCP OFF in stub phase — real implementation would enable MCP for external OAuth-gated integrations

## Evaluation

- outcome evaluation_steps:
  - Does the response contain the stub sentinel phrase "Multi-source analysis coming in v3"?
  - Does the response NOT contain any externally fetched data or API results (which would indicate real external requests instead of the stub)?
- expect_tools: [multi_source_fetch]
- forbid_tools: []
