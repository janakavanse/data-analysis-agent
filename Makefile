PORT     := 8001
GOAL     := "What is the average salary?"
FOLLOWUP := "What is the maximum age in the dataset?"
DATA_FILE := scripts/fixtures/sample_data.csv

.PHONY: setup dev gate demo-gate

setup:
	uv sync --extra dev
	uv run playwright install chromium

dev:
	uv run python -m agent

gate: demo-gate

demo-gate:
	DATA_FILE=$(DATA_FILE) bash scripts/demo_gate.sh
