import time
import uuid
from contextlib import asynccontextmanager
from .db import get_sessionmaker, Span


@asynccontextmanager
async def span(run_id: str, name: str, kind: str = "INTERNAL", **attrs):
    """Time a block, capture exceptions, persist one OTel-GenAI-shaped Span row.

    Yields the mutable attrs dict so callers can enrich it in-flight.
    """
    start = time.time()
    try:
        yield attrs
    except Exception as exc:
        attrs["error"] = f"{type(exc).__name__}: {exc}"
        raise
    finally:
        end = time.time()
        async with get_sessionmaker()() as s:
            s.add(Span(
                id=str(uuid.uuid4()), run_id=run_id, name=name, kind=kind,
                attributes=attrs,
                start_ms=int(start * 1000), end_ms=int(end * 1000),
                duration_ms=int((end - start) * 1000),
            ))
            await s.commit()
