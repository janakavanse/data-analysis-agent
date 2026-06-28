import os

import uvicorn

if __name__ == "__main__":
    # `python -m src` puts the repo root on sys.path, not src/. The app is a flat
    # package set (bare imports, pythonpath=["src"]), so point uvicorn at src/ via
    # app_dir so `api:app` resolves on the documented run command.
    src_dir = os.path.dirname(os.path.abspath(__file__))
    port = int(os.environ.get("PORT", "8001"))
    uvicorn.run("api:app", host="0.0.0.0", port=port, reload=False, app_dir=src_dir)
