PORT     := 8001
GOAL     := "How many paid vacation days do full-time employees get per year?"
FOLLOWUP := "How far in advance must I request time off?"
DATA_FILE := scripts/fixtures/handbook.txt

.PHONY: setup dev gate demo-gate analyze

setup:
	uv sync --extra dev
	uv run playwright install chromium

dev:
	uv run python -m agent

analyze:
	uv run python -m agent.analyze

gate: demo-gate

demo-gate:
	GOAL=$(GOAL) FOLLOWUP=$(FOLLOWUP) DATA_FILE=$(DATA_FILE) bash scripts/demo_gate.sh
