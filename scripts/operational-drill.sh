#!/usr/bin/env bash
# Production-image release drill: preflight, v1.13 schema upgrade, black-box
# security smoke, PostgreSQL backup/restore, and uploads-volume restore.
set -euo pipefail

ROOT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)"
cd "$ROOT_DIR"

IMAGE="${THOROTEST_DRILL_IMAGE:-thorotest:v1.16-rc}"
SKIP_BUILD="${THOROTEST_DRILL_SKIP_BUILD:-0}"
VERSION="$(python3 -c 'import json; print(json.load(open("package.json"))["version"])')"
PREFIX="thorotest-drill-$$"
NETWORK="${PREFIX}-net"
DB="${PREFIX}-db"
RESTORE_DB="${PREFIX}-restore-db"
REDIS="${PREFIX}-redis"
APP="${PREFIX}-app"
RESTORE_APP="${PREFIX}-restore-app"
PG_VOLUME="${PREFIX}-pg"
RESTORE_PG_VOLUME="${PREFIX}-restore-pg"
UPLOAD_VOLUME="${PREFIX}-uploads"
RESTORE_UPLOAD_VOLUME="${PREFIX}-restore-uploads"
DUMP_FILE="$(mktemp "${TMPDIR:-/tmp}/thorotest-v1.16-drill.XXXXXX.dump")"
DB_PASSWORD="release-drill-database-password"
ADMIN_PASSWORD="ReleaseDrillAdminPassword-2026"
SECRET_KEY="release-drill-signing-key-000000000000000000000000000000"
V113_REVISION="c1f6b2a34d70"

cleanup() {
  status=$?
  if [ "$status" -ne 0 ]; then
    for container in "$APP" "$RESTORE_APP" "$DB" "$RESTORE_DB" "$REDIS"; do
      docker logs "$container" 2>/dev/null || true
    done
  fi
  docker rm -f "$APP" "$RESTORE_APP" "$DB" "$RESTORE_DB" "$REDIS" >/dev/null 2>&1 || true
  docker volume rm "$PG_VOLUME" "$RESTORE_PG_VOLUME" "$UPLOAD_VOLUME" "$RESTORE_UPLOAD_VOLUME" >/dev/null 2>&1 || true
  docker network rm "$NETWORK" >/dev/null 2>&1 || true
  rm -f "$DUMP_FILE"
}
trap cleanup EXIT

wait_postgres() {
  container="$1"
  for _ in $(seq 1 45); do
    if docker exec "$container" pg_isready -U thorotest -d thorotest >/dev/null 2>&1; then
      return 0
    fi
    sleep 2
  done
  echo "PostgreSQL did not become ready: $container" >&2
  return 1
}

common_env() {
  printf '%s\n' \
    -e "DATABASE_URL=postgresql://thorotest:${DB_PASSWORD}@$1:5432/thorotest" \
    -e "REDIS_URL=redis://redis:6379/0" \
    -e "REDIS_REQUIRED=1" \
    -e "SECRET_KEY=${SECRET_KEY}" \
    -e "ADMIN_INITIAL_PASSWORD=${ADMIN_PASSWORD}" \
    -e "ENVIRONMENT=production" \
    -e "TESTHUB_BASE_URL=https://thorotest.example.test" \
    -e "ALLOWED_ORIGINS=https://thorotest.example.test" \
    -e "LOG_FORMAT=json" \
    -e "LOG_LEVEL=WARNING" \
    -e "METRICS_ENABLED=1" \
    -e "SMTP_HOST=smtp.example.test" \
    -e "CI_WORKER_ENABLED=1"
}

run_image() {
  database_host="$1"
  shift
  env_args=()
  while IFS= read -r item; do
    env_args+=("$item")
  done < <(common_env "$database_host")
  docker run --rm --network "$NETWORK" "${env_args[@]}" "$IMAGE" "$@"
}

start_app() {
  name="$1"
  alias="$2"
  database_host="$3"
  uploads_volume="$4"
  env_args=()
  while IFS= read -r item; do
    env_args+=("$item")
  done < <(common_env "$database_host")
  docker run -d \
    --name "$name" \
    --network "$NETWORK" \
    --network-alias "$alias" \
    "${env_args[@]}" \
    -v "${uploads_volume}:/app/uploads" \
    "$IMAGE" >/dev/null
}

probe_app() {
  alias="$1"
  docker run --rm \
    --network "$NETWORK" \
    -e "THOROTEST_PROBE_EMAIL=admin@localhost" \
    -e "THOROTEST_PROBE_PASSWORD=${ADMIN_PASSWORD}" \
    "$IMAGE" \
    python -m backend.release_probe \
      --base-url "http://${alias}:8000" \
      --expected-version "$VERSION" \
      --wait-seconds 90
}

if [ "$SKIP_BUILD" != "1" ]; then
  docker build --tag "$IMAGE" .
fi

docker image inspect "$IMAGE" >/dev/null
docker run --rm "$IMAGE" python -c 'import os; assert os.geteuid() != 0, "runtime image must be non-root"'

docker network create "$NETWORK" >/dev/null
docker volume create "$PG_VOLUME" >/dev/null
docker volume create "$RESTORE_PG_VOLUME" >/dev/null
docker volume create "$UPLOAD_VOLUME" >/dev/null
docker volume create "$RESTORE_UPLOAD_VOLUME" >/dev/null

docker run -d \
  --name "$DB" \
  --network "$NETWORK" \
  --network-alias db \
  -e POSTGRES_DB=thorotest \
  -e POSTGRES_USER=thorotest \
  -e "POSTGRES_PASSWORD=${DB_PASSWORD}" \
  -v "${PG_VOLUME}:/var/lib/postgresql/data" \
  postgres:16-alpine >/dev/null

docker run -d \
  --name "$REDIS" \
  --network "$NETWORK" \
  --network-alias redis \
  redis:7-alpine redis-server --appendonly yes >/dev/null

wait_postgres "$DB"

# Static gate runs inside the exact image that will be deployed.
run_image db python -m backend.preflight --strict --json
run_image db python -m backend.release_checks --tag "v${VERSION}"

# Recreate the last released schema, seed its operator, and preserve an upload.
run_image db alembic upgrade "$V113_REVISION"
run_image db python -c 'from backend.seed import init_db; init_db()'
docker run --rm --user 0 -v "${UPLOAD_VOLUME}:/data" "$IMAGE" \
  python -c 'from pathlib import Path; Path("/data/release-drill.txt").write_text("thorotest-v1.16-restore-sentinel\n", encoding="utf-8")'

docker exec "$DB" pg_dump -Fc -U thorotest -d thorotest > "$DUMP_FILE"

# Upgrade from v1.13 to the current Alembic head, then probe the running image.
run_image db python -m backend.bootstrap
start_app "$APP" app db "$UPLOAD_VOLUME"
probe_app app

# Take a quiesced current backup of both authoritative state stores.
docker stop "$APP" >/dev/null
docker exec "$DB" pg_dump -Fc -U thorotest -d thorotest > "$DUMP_FILE"
docker run --rm --user 0 \
  -v "${UPLOAD_VOLUME}:/source:ro" \
  -v "${RESTORE_UPLOAD_VOLUME}:/target" \
  "$IMAGE" \
  python -c 'import shutil; shutil.copytree("/source", "/target", dirs_exist_ok=True)'

docker run -d \
  --name "$RESTORE_DB" \
  --network "$NETWORK" \
  --network-alias restore-db \
  -e POSTGRES_DB=thorotest \
  -e POSTGRES_USER=thorotest \
  -e "POSTGRES_PASSWORD=${DB_PASSWORD}" \
  -v "${RESTORE_PG_VOLUME}:/var/lib/postgresql/data" \
  postgres:16-alpine >/dev/null
wait_postgres "$RESTORE_DB"
docker exec -i "$RESTORE_DB" pg_restore -U thorotest -d thorotest < "$DUMP_FILE"

start_app "$RESTORE_APP" restored-app restore-db "$RESTORE_UPLOAD_VOLUME"
probe_app restored-app
docker run --rm -v "${RESTORE_UPLOAD_VOLUME}:/data:ro" "$IMAGE" \
  python -c 'from pathlib import Path; assert Path("/data/release-drill.txt").read_text(encoding="utf-8") == "thorotest-v1.16-restore-sentinel\n"'

DIGEST="$(docker image inspect --format '{{.Id}}' "$IMAGE")"
printf 'Operational drill READY\nversion=%s\nimage=%s\ndigest=%s\nupgrade_from=%s\n' \
  "$VERSION" "$IMAGE" "$DIGEST" "$V113_REVISION"
