# Capability: SQL Explorer  ·  Priority: P2

## What & why

A user provides a SQLite connection string and asks natural-language questions about the database. The
agent introspects the schema and generates and runs SQL queries to answer the question. This serves the
P2 success criterion in `spec/product.md`: schema introspection and SQL-powered NL query answering.
Until promoted from P2 stub status, this capability is wired into the graph and reachable end-to-end
but returns a fixed stub response: `"SQL explorer coming in v2 — connect a SQLite file and ask schema
or query questions once this capability is promoted."` The stub `[@eval]` asserts this fixed contract so
the journey stays green and the capability is registered. Promote via `/spec-new-capability`.

## Acceptance criteria (EARS — these ARE the eval inputs)

- WHEN the user asks about this capability in v1 the system SHALL return the stub message "SQL explorer coming in v2" confirming the feature is registered but not yet active. [@eval: tests/test_sql_explorer_gate.py::test_sql_explorer_stub]
- WHILE in stub mode WHEN the user provides a SQLite connection string the system SHALL acknowledge the input and return the stub sentinel without attempting a real database connection. [@eval: tests/test_sql_explorer_gate.py::test_sql_explorer_stub_no_connection]

## Tools & layers touched

- tool: `sql_explorer` (in-process @tool — stub: returns fixed sentinel; real implementation will use SQLite introspection + query execution)
- layers: Guardrails ON — stub must not attempt real DB connections or file access

## Evaluation

- outcome evaluation_steps:
  - Does the response contain the stub sentinel phrase "SQL explorer coming in v2"?
  - Does the response NOT contain any database schema output or SQL query results (which would indicate real execution happened instead of the stub)?
- expect_tools: [sql_explorer]
- forbid_tools: []
