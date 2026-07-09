#!/usr/bin/env bash
# Provision the local GitLab CE for the ThoroTest demo:
#   1. wait for the API to come up
#   2. mint a root PAT (scope: api)
#   3. create the demo project and push repo/ (YAML tests + .gitlab-ci.yml)
#   4. create an instance runner + register the docker-executor runner
#
# Run AFTER `docker compose up -d`, from this directory:
#   ./setup.sh
#
# Networking note: browser/ThoroTest reach GitLab at http://localhost:8929,
# but the runner and its job containers reach it as http://gitlab:8929 (compose
# DNS). We register the runner with --clone-url http://gitlab:8929 so job git
# clones don't try to hit localhost inside the container.
set -euo pipefail
cd "$(dirname "$0")"

WEB="http://localhost:8929"
API="$WEB/api/v4"
INTERNAL_URL="http://gitlab:8929"
NETWORK="thorotest-gitlab-demo_default"
ROOT_PW="thorotest-demo-1234"
PROJECT="thorotest-demo"

dc() { docker compose "$@"; }

echo "==> waiting for GitLab API (first boot can take 3-5 min)…"
for i in $(seq 1 60); do
  code=$(curl -s -o /dev/null -w "%{http_code}" "$API/version" || true)
  # 401 = up but unauthenticated (expected before we have a token)
  if [ "$code" = "401" ] || [ "$code" = "200" ]; then echo "    GitLab is up."; break; fi
  printf '.'; sleep 10
  if [ "$i" = "60" ]; then echo "GitLab did not come up in time"; exit 1; fi
done

echo "==> minting a root PAT (scope: api) via gitlab-rails…"
TOKEN=$(dc exec -T gitlab gitlab-rails runner "
  u = User.find_by_username('root')
  u.personal_access_tokens.where(name: 'thorotest-demo').destroy_all
  t = u.personal_access_tokens.create!(scopes: ['api'], name: 'thorotest-demo', expires_at: 365.days.from_now)
  puts t.token
" | tr -d '\r' | tail -n1)
echo "    token: ${TOKEN:0:12}…"

echo "==> creating project '$PROJECT' (idempotent)…"
curl -s --header "PRIVATE-TOKEN: $TOKEN" -X POST "$API/projects" \
  --data "name=$PROJECT&visibility=public&initialize_with_readme=false" >/dev/null || true
NS_PATH=$(curl -s --header "PRIVATE-TOKEN: $TOKEN" "$API/projects?search=$PROJECT" \
  | python3 -c 'import sys,json; d=json.load(sys.stdin); print(d[0]["path_with_namespace"]) if d else print("")')
echo "    project: $NS_PATH"

echo "==> pushing repo/ (YAML tests + .gitlab-ci.yml)…"
PUSH_DIR=$(mktemp -d)
cp -R repo/. "$PUSH_DIR/"
(
  cd "$PUSH_DIR"
  git init -q -b main
  git config user.email demo@thorotest.local
  git config user.name "ThoroTest Demo"
  git add -A && git commit -qm "demo: tests-as-code + gitlab-ci pipeline"
  git remote add origin "http://root:$TOKEN@localhost:8929/$NS_PATH.git"
  git push -qf origin main
)
rm -rf "$PUSH_DIR"
echo "    pushed to $NS_PATH @ main"

echo "==> creating an instance runner + registering it (docker executor)…"
RUNNER_TOKEN=$(curl -s --header "PRIVATE-TOKEN: $TOKEN" -X POST "$API/user/runners" \
  --data "runner_type=instance_type&description=thorotest-demo&run_untagged=true&locked=false" \
  | python3 -c 'import sys,json; print(json.load(sys.stdin).get("token",""))')
if [ -z "$RUNNER_TOKEN" ]; then echo "failed to create runner token"; exit 1; fi

dc exec -T runner gitlab-runner register --non-interactive \
  --url "$INTERNAL_URL" \
  --token "$RUNNER_TOKEN" \
  --executor docker \
  --docker-image "python:3.12-slim" \
  --docker-network-mode "$NETWORK" \
  --docker-volumes /var/run/docker.sock:/var/run/docker.sock \
  --clone-url "$INTERNAL_URL"
echo "    runner registered."

cat <<EOF

────────────────────────────────────────────────────────────
GitLab demo ready.

  Web UI : $WEB   (login: root / $ROOT_PW)
  Project: $WEB/$NS_PATH

Configure the ThoroTest integration with:
  provider  : gitlab
  repo_url  : $WEB/$NS_PATH
  api_base  : $API
  branch    : main
  path      : tests/
  token     : $TOKEN
────────────────────────────────────────────────────────────
EOF
