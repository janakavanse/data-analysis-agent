#!/usr/bin/env bash
# DEMO gate checks 2-6. Exit 0 = done.
set -euo pipefail
PORT="${1:-8001}"
GOAL="${2:-What are the top 3 rows by revenue in the uploaded dataset?}"
BASE="http://localhost:${PORT}"
: "${APP_LLM_API_KEY:?fund a key — export APP_LLM_API_KEY before running the gate}"

# 2 — boot the server
python -m agent & SERVER=$!
trap 'kill "$SERVER" 2>/dev/null || true' EXIT

# 3 — wait up to 30s for /health 200
for i in $(seq 1 30); do
  if curl -fsS "${BASE}/health" >/dev/null 2>&1; then break; fi
  sleep 1
  [ "$i" = 30 ] && { echo "FAIL: /health never came up"; exit 1; }
done
curl -fsS "${BASE}/health" | python3 -c "import sys,json; d=json.load(sys.stdin); assert d.get('ok'), d" \
  || { echo "FAIL: /health not ok"; exit 1; }
echo "CHECK 3: /health OK"

# Seed a CSV dataset for the gate run
CSV_PATH=$(mktemp /tmp/gate_XXXX.csv)
cat > "$CSV_PATH" <<'EOF'
product,revenue,region
Widget A,1500,North
Widget B,2300,South
Widget C,800,North
Widget D,3100,West
EOF

UPLOAD=$(curl -fsS -X POST "${BASE}/datasets/upload" \
  -F "file=@${CSV_PATH};type=text/csv" \
  -F "name=gate_dataset")
rm -f "$CSV_PATH"
DATASET_ID=$(echo "$UPLOAD" | python3 -c "import sys,json; print(json.load(sys.stdin)['data']['dataset_id'])" 2>/dev/null || true)
if [ -z "$DATASET_ID" ]; then
  echo "FAIL: dataset upload failed: $UPLOAD"; exit 1
fi
echo "CHECK: dataset uploaded, id=$DATASET_ID"

# 4 — one real run
PAYLOAD=$(python3 -c "import json,sys; print(json.dumps({'goal': sys.argv[1], 'dataset_id': sys.argv[2]}))" "$GOAL" "$DATASET_ID")
RESP=$(curl -fsS -X POST "${BASE}/runs" -H 'content-type: application/json' -d "$PAYLOAD")
echo "$RESP" | python3 -c "import sys,json; d=json.load(sys.stdin); assert d.get('ok'), d" \
  || { echo "FAIL: run failed: $RESP"; exit 1; }
RUN_ID=$(echo "$RESP" | python3 -c "import sys,json; print(json.load(sys.stdin)['data']['run_id'])")
echo "CHECK 4: run completed, run_id=$RUN_ID"

# 5 — outcome + trajectory eval
python -m agent.gate_eval --run-id "$RUN_ID" --goal "$GOAL" \
  || { echo "FAIL: eval gate (outcome score < threshold or bad trajectory)"; exit 1; }
echo "CHECK 5: outcome + trajectory eval PASS"

# 6 — traces present
curl -fsS "${BASE}/traces" | python3 -c "import sys; body=sys.stdin.read(); assert len(body) > 100, 'traces body empty'" \
  || { echo "FAIL: /traces not rendering"; exit 1; }
echo "CHECK 6: /traces renders"

echo ""
echo "DEMO GATE PASS"
