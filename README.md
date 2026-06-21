# SDD Agent Harness

A spec-driven development harness for building AI agents with Claude Code.

Describe what you want to build. The harness takes it from brief to working, tested,
deployed agent — spec first, no shortcuts.

---

## How it works

```
brief → spec (FR) → phases → code → tests → deploy → reconcile ↺
```

1. **Researcher** elicits requirements and writes a Feature Request
2. **Planner** slices the work into value-ordered phases with gate tests
3. **Executor** implements each phase in `src/` — exactly what the spec says
4. **Reviewer** guards the goal — nothing ships without sign-off
5. **Deployer** ships it — local demo first, cloud on request
6. **Analyser** closes the loop — detects drift, routes corrections

The loop runs autonomously after one human-touch approval gate.

## Quick start

```bash
git clone https://github.com/smallTechOrg/sdd-agent-harness
cd sdd-agent-harness
# Open in Claude Code and run /build
```

## Structure

```
harness/    the method — rules, process, patterns (read this first)
spec/       the contract — FR/CR files, stack rules, patterns
src/        the code — written by the executor, conforms to spec
logs/       the evidence — sessions, runtime, analysis (gitignored)
.claude/    Claude Code adapter — agents, skills, hooks
```

Full documentation: [harness/README.md](harness/README.md)

---

## Data Analyst Agent (built on this harness)

A conversational data analyst — upload CSV/Excel/JSON/Parquet files, ask questions in plain
English, get tables and charts back. Powered by Gemini 2.5 Flash.

### Prerequisites

- Python 3.12+ and [uv](https://docs.astral.sh/uv/getting-started/installation/)
- Node.js 18+ and npm
- A Google Gemini API key ([get one free](https://aistudio.google.com/apikey))

### 1. Install backend dependencies

Run this once from the repo root:

```bash
uv sync
```

### 2. Set up your environment

Copy the example env file and add your Gemini key:

```bash
cp .env.example .env
```

Then open `.env` in any text editor and replace `your-key-here` with your actual Gemini API key:

```
ANALYST_LLM_PROVIDER=gemini
GEMINI_API_KEY=your-key-here        ← replace this line
ANALYST_DB_PATH=data/analyst.duckdb
ANALYST_LLM_MODEL=gemini-2.5-flash
```

### 3. Start the backend

```bash
uv run python -m src
```

You should see:
```
INFO:     Uvicorn running on http://0.0.0.0:8001
```

### 4. Start the frontend (new terminal tab)

```bash
cd frontend
npm install
npm run dev
```

You should see:
```
▲ Next.js — ready on http://localhost:3000
```

### 5. Open the app

Go to **http://localhost:3000** in your browser.

- Upload a CSV or Excel file using the **Load dataset** form
- Ask a question like **"show top 10 rows"** or **"plot revenue over product"**

### Run tests (no API key needed)

```bash
ANALYST_LLM_PROVIDER=stub uv run --extra dev pytest tests/unit/ -v
```

All 40 tests should pass in stub mode.
