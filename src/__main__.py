import sys
from pathlib import Path

# Make this directory importable as top-level packages (config, api, db, ...)
# when invoked as `uv run python -m src`, mirroring alembic/env.py.
sys.path.insert(0, str(Path(__file__).resolve().parent))

import uvicorn

if __name__ == "__main__":
    uvicorn.run("api:app", host="0.0.0.0", port=8001, reload=False)
