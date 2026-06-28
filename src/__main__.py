import sys
from pathlib import Path

import uvicorn

sys.path.insert(0, str(Path(__file__).resolve().parent))  # src/ on path so bare imports resolve

if __name__ == "__main__":
    uvicorn.run("api:app", host="0.0.0.0", port=8001, reload=False)
