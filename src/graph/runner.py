"""Run the analysis pipeline and stream SSE-shaped events for the API.

Two entry points:

- :func:`stream_query` — async generator the API consumes for the SSE endpoint
  ``POST /sessions/{session_id}/query``. Yields event dicts (see below).
- :func:`run_query` — synchronous, non-streaming convenience used by tests; runs
  the compiled ``agentic_ai`` graph end-to-end and persists the Query row.

Both resolve the dataset file path + profile from the DB (written by the ingest
slice at upload), persist a ``queries`` row progressively, and record the full
privacy audit (``llm_payloads_json``).

Streamed event dicts (shaped for spec/api.md):

    {"event": "step",   "data": {"stage": "planning"}}
    {"event": "step",   "data": {"stage": "running"}}
    {"event": "code",   "data": {"code": "result = df..."}}
    {"event": "token",  "data": {"text": "Total revenue "}}
    {"event": "result", "data": {"kind": "scalar", "payload": {...}}}   # optional
    {"event": "done",   "data": {"run_id": "...", "status": "completed",
                                  "tokens": {"prompt": 0, "completion": 0},
                                  "cost_usd": 0.0}}
    {"event": "error",  "data": {"message": "..."}}
"""

from __future__ import annotations

import asyncio
import json
import time
from typing import AsyncIterator

from analysis import stream_answer
from db.models import Dataset, DatasetProfile, Query, Session as SessionRow
from db.session import create_db_session, init_db
from graph.agent import agentic_ai
from graph.nodes import execute_locally, generate_code, plan
from graph.edges import route_after_exec
from observability.events import get_logger

logger = get_logger("graph.runner")


# --------------------------------------------------------------------------- #
# DB helpers
# --------------------------------------------------------------------------- #

class DatasetNotFoundError(Exception):
    """Raised pre-stream so the API can return 404."""


def _resolve_session_id(session_id: str) -> str:
    """Return an existing session id, or create one when ``session_id == 'new'``."""
    if session_id and session_id != "new":
        return session_id
    with create_db_session() as db:
        row = SessionRow()
        db.add(row)
        db.flush()
        return row.id


def _load_dataset_context(dataset_id: str) -> tuple[str, dict, dict]:
    """Return (dataset_path, schema, profile) for a dataset, or raise 404."""
    with create_db_session() as db:
        ds = db.get(Dataset, dataset_id)
        if ds is None:
            raise DatasetNotFoundError(f"unknown dataset: {dataset_id}")
        prof = (
            db.query(DatasetProfile)
            .filter(DatasetProfile.dataset_id == dataset_id)
            .order_by(DatasetProfile.created_at.asc())
            .first()
        )
        schema = json.loads(prof.schema_json) if prof and prof.schema_json else {}
        profile = json.loads(prof.profile_json) if prof and prof.profile_json else {}
        return ds.storage_path, schema, profile


def _create_query(session_id: str, dataset_id: str, question: str) -> str:
    with create_db_session() as db:
        q = Query(
            session_id=session_id,
            dataset_id=dataset_id,
            question=question,
            status="running",
        )
        db.add(q)
        db.flush()
        return q.id


def _persist(query_id: str, **fields) -> None:
    with create_db_session() as db:
        q = db.get(Query, query_id)
        if q is None:
            return
        for key, value in fields.items():
            setattr(q, key, value)


def _estimate_cost(prompt_tokens: int, completion_tokens: int) -> float:
    # gemini-2.0-flash pricing (USD per 1M tokens): input ~0.10, output ~0.40.
    return round(prompt_tokens / 1_000_000 * 0.10
                 + completion_tokens / 1_000_000 * 0.40, 6)


# --------------------------------------------------------------------------- #
# Streaming runner (API)
# --------------------------------------------------------------------------- #

async def stream_query(
    session_id: str, dataset_id: str, question: str
) -> AsyncIterator[dict]:
    """Drive the pipeline and yield SSE-shaped event dicts (see module docstring).

    ``session_id`` may be ``"new"``. Raises :class:`DatasetNotFoundError` BEFORE
    yielding any event when the dataset is unknown (so the API can return 404).
    """
    init_db()
    sid = _resolve_session_id(session_id)
    dataset_path, schema, profile = _load_dataset_context(dataset_id)  # may raise 404

    query_id = _create_query(sid, dataset_id, question)
    started = time.monotonic()
    logger.info("run.start", run_id=query_id, session_id=sid, dataset_id=dataset_id)

    state: dict = {
        "run_id": query_id,
        "session_id": sid,
        "dataset_id": dataset_id,
        "question": question,
        "schema": schema,
        "profile": profile,
        "dataset_path": dataset_path,
        "llm_payloads": [],
        "error": None,
    }

    try:
        # ---- plan -------------------------------------------------------- #
        yield {"event": "step", "data": {"stage": "planning"}}
        state = await asyncio.to_thread(plan, state)
        if state.get("error"):
            async for ev in _fail(query_id, state, started):
                yield ev
            return
        _persist(query_id, plan=state.get("plan"),
                 llm_payloads_json=json.dumps(state.get("llm_payloads") or []))

        # ---- generate_code + execute_locally (with one repair) ----------- #
        async for ev in _codegen_execute(query_id, state, started):
            if ev.get("event") == "_state":
                state = ev["data"]
                continue
            yield ev
        if state.get("error"):
            return  # _codegen_execute already emitted error + persisted

        yield {"event": "code", "data": {"code": state.get("code", "")}}

        exec_result = state.get("exec_result") or {}
        if exec_result.get("ok"):
            yield {
                "event": "result",
                "data": {
                    "kind": exec_result.get("kind", "text"),
                    "payload": exec_result.get("result_summary"),
                },
            }

        # ---- summarize (streamed) ---------------------------------------- #
        yield {"event": "step", "data": {"stage": "running"}}
        answer_parts: list[str] = []
        usage = {"prompt_tokens": 0, "completion_tokens": 0}
        try:
            gen = stream_answer(question, state.get("result_summary") or {})
            for kind, value in _iter_in_thread(gen):
                if kind == "payload":
                    state["llm_payloads"].append(value)
                elif kind == "token":
                    answer_parts.append(value)
                    yield {"event": "token", "data": {"text": value}}
                    await asyncio.sleep(0)
                elif kind == "usage":
                    usage = value
        except Exception as exc:  # noqa: BLE001
            state["error"] = f"summarize failed: {exc}"
            async for ev in _fail(query_id, state, started):
                yield ev
            return

        answer = "".join(answer_parts).strip()
        cost = _estimate_cost(usage["prompt_tokens"], usage["completion_tokens"])
        _persist(
            query_id,
            code=state.get("code"),
            result_json=json.dumps(exec_result.get("result_summary"))
            if exec_result else None,
            answer=answer,
            status="completed",
            prompt_tokens=usage["prompt_tokens"],
            completion_tokens=usage["completion_tokens"],
            cost_usd=cost,
            llm_payloads_json=json.dumps(state.get("llm_payloads") or []),
        )
        dur = int((time.monotonic() - started) * 1000)
        logger.info("run.done", run_id=query_id, status="completed",
                    duration_ms=dur, prompt_tokens=usage["prompt_tokens"],
                    completion_tokens=usage["completion_tokens"], cost_usd=cost)
        yield {
            "event": "done",
            "data": {
                "run_id": query_id,
                "status": "completed",
                "tokens": {
                    "prompt": usage["prompt_tokens"],
                    "completion": usage["completion_tokens"],
                },
                "cost_usd": cost,
            },
        }
    except Exception as exc:  # noqa: BLE001 - last-resort guard
        state["error"] = str(exc)
        async for ev in _fail(query_id, state, started):
            yield ev


async def _codegen_execute(query_id, state, started):
    """Generate code, execute, allow one repair. Yields events + a final _state."""
    while True:
        state = await asyncio.to_thread(generate_code, state)
        if state.get("error"):
            async for ev in _fail(query_id, state, started):
                yield ev
            yield {"event": "_state", "data": state}
            return
        _persist(query_id, code=state.get("code"),
                 llm_payloads_json=json.dumps(state.get("llm_payloads") or []))

        state = await asyncio.to_thread(execute_locally, state)
        route = route_after_exec(state)
        if route == "summarize":
            yield {"event": "_state", "data": state}
            return
        if route == "generate_code":
            logger.info("run.repair", run_id=query_id)
            continue  # one repair loop
        # handle_error
        async for ev in _fail(query_id, state, started):
            yield ev
        yield {"event": "_state", "data": state}
        return


async def _fail(query_id, state, started):
    message = state.get("error") or "unknown error"
    _persist(
        query_id,
        status="failed",
        error_message=message,
        code=state.get("code"),
        plan=state.get("plan"),
        llm_payloads_json=json.dumps(state.get("llm_payloads") or []),
    )
    dur = int((time.monotonic() - started) * 1000)
    logger.warning("run.error", run_id=query_id, error=message, duration_ms=dur)
    yield {"event": "error", "data": {"message": message}}


def _iter_in_thread(gen):
    """Iterate a blocking generator without splitting it across threads.

    The stream_answer generator does blocking network I/O. For Phase 1 (single
    user, one query at a time) we drain it inline; the surrounding async loop
    still yields control via ``await asyncio.sleep(0)`` between tokens.
    """
    for item in gen:
        yield item


# --------------------------------------------------------------------------- #
# Non-streaming runner (tests / scripts)
# --------------------------------------------------------------------------- #

def run_query(session_id: str, dataset_id: str, question: str) -> dict:
    """Run the compiled graph end-to-end and persist the Query row.

    Returns the final state dict (includes status, plan, code, answer,
    exec_result, llm_payloads). Used by integration tests.
    """
    init_db()
    sid = _resolve_session_id(session_id)
    dataset_path, schema, profile = _load_dataset_context(dataset_id)
    query_id = _create_query(sid, dataset_id, question)
    started = time.monotonic()
    logger.info("run.start", run_id=query_id, session_id=sid, dataset_id=dataset_id)

    initial: dict = {
        "run_id": query_id,
        "session_id": sid,
        "dataset_id": dataset_id,
        "question": question,
        "schema": schema,
        "profile": profile,
        "dataset_path": dataset_path,
        "llm_payloads": [],
        "error": None,
    }
    final = agentic_ai.invoke(initial)

    status = final.get("status", "failed")
    exec_result = final.get("exec_result") or {}
    prompt_tokens = int(final.get("prompt_tokens", 0) or 0)
    completion_tokens = int(final.get("completion_tokens", 0) or 0)
    cost = _estimate_cost(prompt_tokens, completion_tokens)
    _persist(
        query_id,
        plan=final.get("plan"),
        code=final.get("code"),
        result_json=json.dumps(exec_result.get("result_summary"))
        if exec_result else None,
        answer=final.get("answer"),
        status=status,
        error_message=final.get("error") if status == "failed" else None,
        prompt_tokens=prompt_tokens,
        completion_tokens=completion_tokens,
        cost_usd=cost,
        llm_payloads_json=json.dumps(final.get("llm_payloads") or []),
    )
    dur = int((time.monotonic() - started) * 1000)
    logger.info("run.done", run_id=query_id, status=status, duration_ms=dur)
    final["run_id"] = query_id
    return final
