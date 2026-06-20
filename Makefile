PORT ?= 8001
GOAL ?= What are the top 3 rows by revenue in the uploaded dataset?
PYTHON ?= .venv/bin/python

.PHONY: demo-gate gate dev install

gate: demo-gate

demo-gate:
	$(PYTHON) -m pytest -q
	@bash harness/scripts/demo_gate.sh $(PORT) "$(GOAL)"

# UI is served directly from FastAPI at http://localhost:8001/
dev:
	$(PYTHON) -m agent

install:
	uv pip install plotly --python $(PYTHON)
