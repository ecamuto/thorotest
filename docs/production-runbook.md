# Production runbook

This is the operator path for a PostgreSQL + Redis deployment. SQLite remains
appropriate for evaluation and a small, single-process install only.

## Deploy or upgrade

1. Back up the database and `uploads/` together using [BACKUP.md](../BACKUP.md).
2. Pull an immutable release tag or digest. Verify its GitHub attestation with
   `gh attestation verify oci://ghcr.io/ecamuto/thorotest:<version> -R ecamuto/thorotest`.
3. Run `python -m backend.bootstrap` once with the release image and production
   `DATABASE_URL`. This applies Alembic migrations and creates the first admin
   only when needed.
4. Start application replicas only after bootstrap succeeds. Normal workers
   verify the Alembic head and refuse to mutate an old schema.
5. Wait for `/ready` to return HTTP 200. In the reference topology it verifies
   both PostgreSQL and Redis. `/health` is the liveness check.
6. Smoke-test login, `GET /api/initial-data`, a WebSocket run view, and one
   backup restore in a disposable environment.

The Compose files implement steps 3–5 with a one-shot `bootstrap` service.
For Kubernetes, use the same image/command in a pre-deploy Job or init Job and
keep migrations out of the application Deployment.

`AUTO_BOOTSTRAP=1` is a one-release compatibility switch for direct installs.
Do not enable it with multiple workers or replicas.

## Roll back

Application rollback is image-based: redeploy the previous immutable digest.
Before any migration, keep a tested database plus uploads backup. If a release
contains a backward-incompatible migration, stop all writers and restore that
backup; do not blindly run `alembic downgrade` on production data. Record the
failed revision and migration output before restoring.

## Redis policy and failure drills

Redis carries rate-limit counters and best-effort realtime Pub/Sub events; the
database carries durable CI job state. Enable AOF or use a managed service, but
Redis backup is not part of the authoritative application backup. Losing Redis
may reset rate-limit windows and drops events emitted during the outage; clients
must refresh state after reconnect. CI jobs continue from database leases.

With `REDIS_REQUIRED=1`, Redis loss makes `/ready` return 503 and rate-limited
endpoints fail closed. Exercise quarterly:

- stop Redis; confirm readiness is 503 and liveness remains healthy;
- restore Redis; confirm readiness recovers and subscribers reconnect;
- stop a worker during a CI job; after the 90-second lease, confirm another
  worker increments `attempts` and resumes it;
- start a worker against a pre-upgrade backup; confirm it exits with the exact
  bootstrap command instead of serving traffic.

Provider APIs are not transactional. Recovery is at-least-once, so a provider
call interrupted at the network boundary can be repeated. Keep workflows and
result imports idempotent and investigate duplicate provider runs by `job_id`.

## Observability

Set `LOG_FORMAT=json` and ship stdout to the platform log collector. Preserve
`X-Request-ID` across the ingress so one request can be followed through every
replica. Scrape `/metrics` internally; do not expose it on the public ingress.

Useful dashboard queries:

- request rate: `sum by (route) (rate(thorotest_http_requests_total[5m]))`
- p95 latency: `histogram_quantile(0.95, sum by (le, route) (rate(thorotest_http_request_duration_seconds_bucket[5m])))`
- open sockets: `sum by (channel) (thorotest_websocket_connections)`
- Redis errors: `sum by (operation) (increase(thorotest_redis_failures_total[10m]))`
- CI outcomes: `sum by (provider, outcome) (increase(thorotest_ci_jobs_total[1h]))`

Import [deploy/prometheus-alerts.yml](../deploy/prometheus-alerts.yml) as a
starting rule group. Also alert on the platform's `/ready` probe and on a failed
bootstrap Job; those deployment signals are intentionally not process metrics.

## Release verification

Every version tag runs the backend suite with a real Redis service, CLI tests,
the production frontend build, dependency CVE audit, and the full Playwright
suite. Only then is a multi-architecture GHCR image built with SBOM/provenance,
attested, and keyless-signed by cosign. The image digest—not a mutable tag—is
the deployment identity.
