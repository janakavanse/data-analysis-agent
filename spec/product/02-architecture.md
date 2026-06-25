# Architecture

## System Overview

The data analysis agent is a single-process FastAPI application. Users interact via a browser UI (Jinja2 templates). Uploaded files are converted to **Parquet** on disk; data-source metadata, sessions, and query history live in **SQLite**.

A **session** is the long-lived agent context. The first time a session is queried, the app builds a **per-session MCP pool** — one in-process Model Context Protocol (MCP) **server** per attached data source, each wrapping that source's Parquet via DuckDB. That pool is **reused by every subsequent query** in the session (not rebuilt per query). Each query is one LangGraph ReAct run acting as an MCP **client**: `plan_action → execute_action (call_tool) → finalize`, looping until the LLM signals a final answer. The agent's **memory is durable per session** via a LangGraph `SqliteSaver` checkpointer keyed by `thread_id = session_id`.

Key decisions: **(1)** a data source's capabilities are exposed through an MCP server, not hardcoded — adding a data-source type means writing a new MCP server; **(2)** MCP is only the agent↔tool transport (the LLM↔agent ReAct protocol stays hand-rolled); **(3)** all MCP/tool code lives under `tools/`.

## Component Map

```
Browser (HTML form)
    ↓ POST /datasources/upload  |  POST /sessions  |  POST /sessions/{id}/query
FastAPI (uvicorn, sync endpoints)
    │  upload : CSV → Parquet (FileIngester) + DataSource row (+ LLM descriptions)
    │  session: create SessionRow + links; best-effort warm the session pool
    │  query  : create QueryRecord + AgentRun, spawn a daemon thread
    │
    └─► Pipeline thread → SessionPoolManager.acquire(session_id)   (lazy build, reused)
                        → per-session lock → asyncio.run:
                            AsyncSqliteSaver(checkpoint_db) → build_graph().compile(checkpointer)
                            → ainvoke(input, thread_id=session_id)
            ├── plan_action    (reads tools/schema/memory; LLM picks next tool, or FINAL ANSWER)
            ├── execute_action (MCP client call_tool → DuckDB SELECT over Parquet)
            └── finalize       (persist QueryRecord; append turn to durable `conversation`)
                ↓
        SQLite (metadata) + checkpoint SQLite (memory) + Parquet files (DuckDB)
```

## MCP Layer

```
        tools/mcp/pool.py — SessionPoolManager (the ONLY importer of mcp.shared.memory)
        ┌────────────────────────────────────────────────────────────────┐
 agent  │  per session_id (held, reused across queries; LRU/idle evicted):│
        │     N FastMCP servers + DuckDB conns  + a per-session lock       │
        │  per call (transient): ClientSession ──► FastMCP(ds_i) ─► DuckDB ─► Parquet_i
        └────────────────────────────────────────────────────────────────┘
                         build_server() lives in tools/mcp/server.py
```

- **Transport:** in-process / in-memory (`create_connected_server_and_client_session`). Sessions are **transient** (opened/closed within a single graph node); the servers + DuckDB connections persist for the **session** and are reused by every query.
- **One server per data source**, tool key `<table_name>__run_query`; the manager namespaces + routes `call_tool` to the owning server.
- **Lifecycle:** lazy build on first query; reused; **idle/LRU eviction**; closed on session delete + app shutdown; invalidated when a session's sources change. Queries on one session are **serialized** by a per-session lock (the DuckDB connection is not concurrency-safe).
- **Isolation seam:** every MCP import lives in `tools/mcp/`. The `mcp` SDK is pinned `==1.28.0`.

## Layers

| Layer | Responsibility |
|-------|----------------|
| API (FastAPI) | HTTP routing, upload, forms, templates; warms/closes session pools on create/delete |
| Ingestion | CSV/XLSX/JSON → Parquet; schema + row-count extraction (`tools/ingester.py`) |
| MCP server | Per-source `FastMCP` over one Parquet; `run_query` via read-only DuckDB (`tools/mcp/server.py`) |
| Session pool manager | Build/cache/evict per-session pools; namespacing, routing, per-session lock (`tools/mcp/pool.py`) |
| Graph (LangGraph) | Async ReAct pipeline: plan → execute → loop → finalize (no `load_data`) |
| Memory | Durable per-session checkpointer (`SqliteSaver`, `thread_id = session_id`) |
| LLM (OpenRouter) | Chat completions; falls back to stub when key not set |
| DB (SQLAlchemy + SQLite) | Persistence of metadata, sessions, query history |
| Templates (Jinja2) | Server-rendered HTML |

## Data Flow

1. **Upload:** file → Parquet (`FileIngester`); a `DataSource` row stores parquet_path, schema, row_count, and LLM-generated `tool_description`/`capability_description`.
2. **New session:** create `Session` + `SessionDataSource` links; **best-effort warm** the session pool (`SessionPoolManager.acquire`).
3. **Query:** create `QueryRecord` + `AgentRun`; spawn a daemon thread → `run_pipeline()`.
4. **Per-query run:** acquire the session pool (lazy-build if evicted/restarted) and the per-session lock; inside one `asyncio.run`, open the checkpointer and `ainvoke` the graph with `thread_id = session_id`:
   - `plan_action`: read tools/schema from the manager + the durable `conversation`; ask the LLM for a `{"tool","arguments"}` call or `FINAL ANSWER:`.
   - `execute_action`: `manager.call_tool` → DuckDB `SELECT`; append result/error to the per-query `action_history`.
   - loop until `FINAL ANSWER:` or max iterations; `finalize` persists the record and appends `{question, answer}` to `conversation` (memory). **The pool is not closed here.**
5. **Result:** redirect to the session page (polls `/status`); the new answer renders inline.

## External Dependencies

| Dependency | Purpose | Failure Mode |
|------------|---------|--------------|
| OpenRouter (Gemini 2.5 Flash) | NL reasoning / planning | Falls back to stub — "(stub mode)" |
| `mcp` SDK (in-process) | Agent↔tool protocol | Server build / session failure → fatal for that run |
| DuckDB | Read-only SQL over Parquet | SQL errors recoverable; missing Parquet fatal |
| `langgraph-checkpoint-sqlite` | Durable per-session memory | Checkpoint DB unwritable → memory disabled / run error (degrade clearly) |
| SQLite | Metadata + checkpoint stores | App fails to start if unwritable |
| Local filesystem | Parquet files | Upload fails with a user-visible error |

## Concurrency, Async & Memory Model

- FastAPI endpoints stay **sync**; a query runs on a **daemon thread**; `run_pipeline()` owns one `asyncio.run` per query.
- LangGraph runs **each node in its own task** → MCP `ClientSession`s are **transient per node**; the manager holds only plain objects (servers + DuckDB conns) across nodes and across queries.
- **Per-session serialization:** a per-session `threading.Lock` wraps each query (shared DuckDB conn). Eviction skips locked (in-use) sessions.
- **Memory:** `AsyncSqliteSaver` (file-backed) keyed by `thread_id = session_id`; a fresh saver is opened inside each query's loop (durable across these ephemeral savers and across restarts). Only `conversation` is kept in durable state; per-query scratch is reset via the `ainvoke` input.
- **Constraints (non-negotiable):** no LangGraph parallel fan-out; never span an MCP `ClientSession` across nodes; never wrap MCP calls in `anyio.to_thread`.

## Deployment Model

Local single-user service: `uv run python -m data_analysis_agent` on port 8001. Single process — MCP servers are in-memory; the metadata DB, the checkpoint DB, and Parquet files are the only on-disk state.
