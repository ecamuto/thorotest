#!/usr/bin/env bash
# Populate a self-contained presentation DB with ThoroTest's OWN test suites
# (dogfood) instead of the synthetic `make demo` data.
#
#   1. run backend pytest + Playwright e2e, exporting JUnit XML
#   2. normalise the XML into a readable folder tree
#   3. boot a throwaway server on a dedicated DB and import both suites
#
# Result: presentation.db — real tests, real folders, two runs with real
# pass/fail results. At the talk, launch with:
#
#   DATABASE_URL=sqlite:///./presentation.db make dev
#
# Re-runnable: wipes presentation.db each time. Login admin@localhost / admin.
set -uo pipefail
cd "$(dirname "$0")/.."
ROOT="$(pwd)"

DB="presentation.db"
PORT=8123                       # off the default 8000 so a live `make dev` can coexist
OUT="$ROOT/scratch-junit"
DATE="$(date +%Y-%m-%d)"
mkdir -p "$OUT"

# Skip the (slow) suite runs and reuse existing XML: SKIP_TESTS=1 scripts/seed-presentation.sh
if [ "${SKIP_TESTS:-0}" != "1" ]; then
  echo "==> [1/5] backend pytest -> JUnit XML"
  venv/bin/pytest backend/tests/ --junitxml="$OUT/pytest.xml" -q || true

  echo "==> [2/5] Playwright e2e -> JUnit XML (boots its own e2e.db server)"
  PLAYWRIGHT_JUNIT_OUTPUT_NAME="$OUT/e2e.xml" npx playwright test --reporter=junit || true
fi

# The JUnit importer derives a nested folder tree from each testcase's
# classname, so the raw pytest/Playwright XML imports cleanly — no normalise
# step needed.

echo "==> [3/5] fresh presentation DB + throwaway server on :$PORT"
rm -f "$DB" "$DB-shm" "$DB-wal"
DATABASE_URL="sqlite:///./$DB" ADMIN_INITIAL_PASSWORD=admin \
  venv/bin/python -m backend.bootstrap
DATABASE_URL="sqlite:///./$DB" ADMIN_INITIAL_PASSWORD=admin venv/bin/uvicorn backend.main:app --port "$PORT" >"$OUT/server.log" 2>&1 &
SRV=$!
trap 'kill $SRV 2>/dev/null' EXIT
for _ in $(seq 1 40); do
  curl -sf "localhost:$PORT/health" >/dev/null 2>&1 && break
  sleep 0.5
done

echo "==> [4/5] login"
TOKEN="$(curl -sf -X POST "localhost:$PORT/api/auth/login" \
  -H 'Content-Type: application/json' \
  -d '{"email":"admin@localhost","password":"admin"}' \
  | venv/bin/python -c 'import sys,json; print(json.load(sys.stdin)["access_token"])')"
[ -n "$TOKEN" ] || { echo "login failed — see $OUT/server.log"; exit 1; }

echo "==> [5/5] import suites"
for f in "$OUT/pytest.xml" "$OUT/e2e.xml"; do
  [ -f "$f" ] || { echo "  skip missing $f"; continue; }
  echo "  importing $(basename "$f")"
  curl -sf -X POST "localhost:$PORT/api/import/execute" \
    -H "Authorization: Bearer $TOKEN" \
    -F "file=@$f" -F "format=junit_xml" -F "conflict=skip" \
    | venv/bin/python -m json.tool || echo "  import failed for $f"
done

echo
echo "Done. presentation.db ready. Launch the talk with:"
echo "  DATABASE_URL=sqlite:///./$DB make dev"
