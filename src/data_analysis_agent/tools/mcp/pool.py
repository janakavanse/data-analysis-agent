"""Session-scoped pool of in-process MCP servers — the agent's MCP client layer.

A **session** owns one pool: one MCP server **per attached dataset**, each exposing one
``query_{table}`` capability per table. Built lazily on the session's first query and reused. This
is the ONLY module that imports ``mcp.shared.memory`` (the in-memory transport).

Concurrency (see spec/product/07-agent-graph.md):
- LangGraph runs each node in its own asyncio task, so MCP ``ClientSession``s are **transient**
  (opened/closed within a single call). The pool holds only plain objects across nodes/queries:
  the built ``FastMCP`` servers and their DuckDB connections.
- A session's DuckDB connections are not concurrency-safe, so queries on one session are serialized
  by a per-session ``threading.Lock`` (held by ``run_pipeline`` for the whole query). ``close()``
  acquires that lock before teardown so a dataset change never closes a connection mid-query.
- Pools are idle/LRU-evicted; eviction skips sessions whose lock is currently held (in use).
"""
from __future__ import annotations

import threading
import time
from dataclasses import dataclass, field
from importlib.metadata import version

import structlog
from mcp.server.fastmcp import FastMCP
from mcp.shared.memory import create_connected_server_and_client_session

from data_analysis_agent.config.settings import get_settings
from data_analysis_agent.db.models import DataSourceRow, DatasetTableRow, SessionDataSourceRow
from data_analysis_agent.db.session import create_db_session
from data_analysis_agent.tools.connectors.base import get_connector
from data_analysis_agent.tools.table_naming import sql_table_name

log = structlog.get_logger()

# Relies on the in-memory transport helper, which exists in mcp 1.x and is removed in 2.x.
_MCP_VERSION = version("mcp")
if not _MCP_VERSION.startswith("1."):
    raise RuntimeError(
        f"mcp {_MCP_VERSION} is installed but this code targets the 1.x in-memory transport. "
        f"Pin mcp==1.28.0."
    )


class NoDataSourcesError(Exception):
    """Raised when a session has no attached datasets to build a pool from."""


@dataclass
class _Capability:
    """One table within a dataset — an MCP tool the dataset's server exposes."""

    table_name: str
    description: str
    parameter_schema: dict
    columns: list[str]
    server_tool_name: str  # e.g. "query_orders"


@dataclass
class _Dataset:
    """One dataset (the agent's "tool") and its per-table capabilities."""

    name: str
    server: FastMCP
    tool_description: str
    capabilities: dict[str, _Capability]  # table_name -> capability


@dataclass
class SessionPool:
    """A session's datasets, addressed two-level by ``(dataset_name, table_name)``."""

    session_id: str
    datasets: dict[str, _Dataset]
    last_used: float

    def snapshot(self) -> list[dict]:
        """Grouped, agent-facing tool list for the planning prompt (tool=dataset, capability=table)."""
        return [
            {
                "dataset": d.name,
                "tool_description": d.tool_description,
                "capabilities": [
                    {
                        "table": c.table_name,
                        "description": c.description,
                        "columns": c.columns,
                        "parameter_schema": c.parameter_schema,
                    }
                    for c in d.capabilities.values()
                ],
            }
            for d in self.datasets.values()
        ]

    async def call_tool(self, dataset: str, capability: str, arguments: dict) -> tuple[str, bool]:
        """Route a two-level call to the dataset's server's ``query_{capability}`` tool."""
        d = self.datasets.get(dataset)
        if d is None:
            valid = ", ".join(self.datasets) or "(none)"
            return f"Unknown tool '{dataset}'. Valid tools: {valid}.", True
        cap = d.capabilities.get(capability)
        if cap is None:
            valid = ", ".join(d.capabilities) or "(none)"
            return f"Unknown capability '{capability}' for tool '{dataset}'. Valid capabilities: {valid}.", True
        async with create_connected_server_and_client_session(d.server) as session:
            result = await session.call_tool(cap.server_tool_name, arguments)
        text = result.content[0].text if result.content else ""
        return text, bool(result.isError)

    def aclose(self) -> None:
        """Close every dataset server's DuckDB connection (plain, task-safe)."""
        for d in self.datasets.values():
            conn = getattr(d.server, "_duckdb_conn", None)
            if conn is not None:
                try:
                    conn.close()
                except Exception:
                    pass


class SessionPoolManager:
    """Builds, caches, serializes, and evicts one MCP pool per session."""

    def __init__(self, max_pools: int, idle_seconds: float) -> None:
        self._pools: dict[str, SessionPool] = {}
        self._locks: dict[str, threading.Lock] = {}
        self._registry = threading.Lock()  # guards _pools and _locks
        self._max_pools = max_pools
        self._idle_seconds = idle_seconds

    def session_lock(self, session_id: str) -> threading.Lock:
        """Return the per-session lock (created on first use)."""
        with self._registry:
            lock = self._locks.get(session_id)
            if lock is None:
                lock = self._locks[session_id] = threading.Lock()
            return lock

    async def acquire(self, session_id: str) -> SessionPool:
        """Return the session's pool, building it lazily on first use.

        Call while holding ``session_lock(session_id)``. Raises :class:`NoDataSourcesError`
        if the session has no datasets.
        """
        with self._registry:
            pool = self._pools.get(session_id)
            if pool is not None:
                pool.last_used = time.monotonic()
                return pool

        pool = await self._build(session_id)  # async (list_tools) — outside the registry lock

        with self._registry:
            existing = self._pools.get(session_id)
            if existing is not None:  # built concurrently — keep the first
                pool.aclose()
                existing.last_used = time.monotonic()
                return existing
            self._pools[session_id] = pool
            self._evict_locked()
            log.info("session_pool.built", session_id=session_id, datasets=len(pool.datasets),
                     active_pools=len(self._pools))
            return pool

    def snapshot(self, session_id: str) -> list[dict]:
        """Return the grouped dataset/capability list for ``plan_action`` (empty if not built)."""
        with self._registry:
            pool = self._pools.get(session_id)
            if pool is None:
                return []
            pool.last_used = time.monotonic()
            return pool.snapshot()

    async def call_tool(self, session_id: str, dataset: str, capability: str, arguments: dict) -> tuple[str, bool]:
        """Route a two-level tool call to the session's pool (must be acquired first)."""
        with self._registry:
            pool = self._pools.get(session_id)
            if pool is not None:
                pool.last_used = time.monotonic()
        if pool is None:
            return f"No MCP pool for session '{session_id}'.", True
        return await pool.call_tool(dataset, capability, arguments)

    def close(self, session_id: str) -> None:
        """Close a session's pool, waiting for any in-flight query first. Idempotent.

        Acquires the per-session lock before teardown so a dataset change (add-csv/sync/delete)
        never closes a DuckDB connection mid-query on the pipeline thread.
        """
        lock = self.session_lock(session_id)
        with lock:
            with self._registry:
                pool = self._pools.pop(session_id, None)
            if pool is not None:
                pool.aclose()
                log.info("session_pool.closed", session_id=session_id)

    def close_all(self) -> None:
        """Close every pool (on app shutdown)."""
        with self._registry:
            pools = list(self._pools.values())
            self._pools.clear()
        for pool in pools:
            pool.aclose()

    # ---- internals -------------------------------------------------------

    async def _build(self, session_id: str) -> SessionPool:
        loaded = _load_datasets(session_id)
        if not loaded:
            raise NoDataSourcesError("No datasets attached to this session")
        max_rows = get_settings().mcp_max_result_rows
        datasets: dict[str, _Dataset] = {}
        for dataset, tables in loaded:
            connector = get_connector(dataset, tables)
            server = connector.build_server(max_rows)
            columns_by_table = {t["table_name"]: (t.get("column_names") or []) for t in tables}
            capabilities = await _discover_capabilities(server, columns_by_table)
            datasets[dataset["name"]] = _Dataset(
                name=dataset["name"],
                server=server,
                tool_description=dataset.get("tool_description") or "",
                capabilities=capabilities,
            )
        return SessionPool(session_id, datasets, time.monotonic())

    def _evict_locked(self) -> None:
        """Evict idle + over-cap pools, skipping in-use (locked) sessions. Holds ``_registry``."""
        now = time.monotonic()
        for sid, pool in list(self._pools.items()):
            if now - pool.last_used > self._idle_seconds:
                self._try_close_locked(sid)
        while len(self._pools) > self._max_pools:
            sid = min(self._pools, key=lambda s: self._pools[s].last_used)
            if not self._try_close_locked(sid):
                break

    def _try_close_locked(self, sid: str) -> bool:
        """Close a pool iff its session is not currently in use. Holds ``_registry``."""
        lock = self._locks.get(sid)
        if lock is not None and not lock.acquire(blocking=False):
            return False
        try:
            pool = self._pools.pop(sid, None)
            if pool is not None:
                pool.aclose()
                log.info("session_pool.evicted", session_id=sid)
            return True
        finally:
            if lock is not None:
                lock.release()


async def _discover_capabilities(server: FastMCP, columns_by_table: dict[str, list[str]]) -> dict[str, _Capability]:
    """List a dataset server's tools (one per table) into capability descriptors."""
    async with create_connected_server_and_client_session(server) as session:
        listed = await session.list_tools()
    capabilities: dict[str, _Capability] = {}
    for tool in listed.tools:
        table_name = tool.name[len("query_"):] if tool.name.startswith("query_") else tool.name
        capabilities[table_name] = _Capability(
            table_name=table_name,
            description=tool.description or "",
            parameter_schema=_input_properties(tool.inputSchema),
            columns=columns_by_table.get(table_name, []),
            server_tool_name=tool.name,
        )
    return capabilities


def _input_properties(input_schema: dict | None) -> dict:
    """Reduce an MCP ``inputSchema`` to its property map for the planning prompt."""
    if not input_schema:
        return {}
    return input_schema.get("properties", input_schema)


def _load_datasets(session_id: str) -> list[tuple[dict, list[dict]]]:
    """Load a session's datasets + their tables as serialisable ``(dataset, tables)`` dicts.

    A dataset with no ``dataset_tables`` children (legacy / pre-cutover upload) falls back to a
    single synthesized table from the deprecated ``DataSourceRow`` columns, so existing data and
    not-yet-migrated upload paths keep working.
    """
    with create_db_session() as db:
        links = (
            db.query(SessionDataSourceRow)
            .filter(SessionDataSourceRow.session_id == session_id)
            .all()
        )
        loaded: list[tuple[dict, list[dict]]] = []
        for link in links:
            ds = db.get(DataSourceRow, link.data_source_id)
            if ds is None:
                continue
            children = (
                db.query(DatasetTableRow)
                .filter(DatasetTableRow.dataset_id == ds.id)
                .order_by(DatasetTableRow.created_at)
                .all()
            )
            tables = [_serialize_table(t) for t in children] or [_legacy_table(ds)]
            loaded.append((_serialize_dataset(ds), tables))
        return loaded


def _serialize_dataset(ds: DataSourceRow) -> dict:
    return {
        "id": ds.id,
        "name": ds.name,
        "type": ds.type,
        "uri": ds.dataset_uri,
        "tool_description": ds.tool_description,
    }


def _serialize_table(t: DatasetTableRow) -> dict:
    return {
        "table_name": t.table_name,
        "parquet_path": t.parquet_path,
        "column_names": t.column_names,
        "row_count": t.row_count,
        "capability_description": t.capability_description,
    }


def _legacy_table(ds: DataSourceRow) -> dict:
    """Synthesize a single table from a legacy single-CSV dataset row (no child rows yet)."""
    return {
        "table_name": sql_table_name(ds.name),
        "parquet_path": ds.parquet_path,
        "column_names": ds.column_names,
        "row_count": ds.row_count,
        "capability_description": ds.capability_description,
    }


_manager: SessionPoolManager | None = None


def get_manager() -> SessionPoolManager:
    """Return the process-wide :class:`SessionPoolManager` singleton."""
    global _manager
    if _manager is None:
        s = get_settings()
        _manager = SessionPoolManager(s.max_session_pools, s.session_pool_idle_seconds)
    return _manager
