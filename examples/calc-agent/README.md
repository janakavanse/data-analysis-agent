# calc-agent

A tiny Gemini ReAct agent: ask a math question in English, it calls a safe `calculator` tool and returns
the number. A hand-rolled tool loop, no agent framework — the lean baseline the harness produces.

## Run
```bash
python -m venv .venv && . .venv/bin/activate
pip install -r requirements.txt
echo "GEMINI_API_KEY=your-key" > .env          # gitignored
python agent.py "what is 17 * 23 plus 5?"      # -> 396
```

## Test
```bash
pytest          # tool tests run keyless; the acceptance test needs GEMINI_API_KEY in .env
```

Proves: the `calculator` tool is correct and refuses unsafe input, and the real agent answers
`17 * 23 + 5` with **396**.
