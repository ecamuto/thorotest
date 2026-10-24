# ThoroTest — Master Improvement Roadmap

**Audit date:** 2026-07-16 · **Version:** 1.9.0
**Last reconciled:** 2026-08-28 · **Current target:** v1.14

Horizon: 12 months. Priorities are P0 (blocker) → P3 (nice-to-have). Effort in engineer-days is rough. "ROI" weighs business+technical impact against effort.

This roadmap is derived from the findings in `AUDIT_REPORT.md`, `SECURITY_AUDIT.md`, `PERFORMANCE_REPORT.md`, `TECHNICAL_DEBT.md`, and `COMPETITOR_ANALYSIS.md`.

## Current status

The detailed tables below are the original v1.9 plan. This reconciliation is
the current source of truth for status; completed rows remain below for audit
traceability.

| Scope | Status | Evidence / remaining work |
|---|---|---|
| I-1… I-6 | ✅ Done | Security P0 remediation merged in PR #22. |
| Q-1… Q-3 | ✅ Done | Indexes, `/initial-data` N+1, and CSV injection merged in PR #24. |
| Q-4… Q-8 | ✅ Done | Password/admin bootstrap, hygiene, dependency lock/audit, and badge checks merged in PR #25. |
| v1.13 audit addendum | ✅ Done | JWT scope enforcement, WebSocket tickets, RBAC, PyJWT migration, blocking CVE audit, and deterministic webhook tests merged in PR #47. |
| S-3 | ✅ Done | PostgreSQL is the documented production default; SQLite remains supported for evaluation and small installs. |
| S-5 | 🟡 Partial | CSP, forced attachment downloads, and unsafe renderable-MIME neutralization exist; a strict upload allow-list and object-level access policy remain. |
| S-8 | 🟡 Partial | The shared URL guard covers webhooks, notifications, integrations, GitLab, and Jira; configurable AI and any remaining outbound clients still need one explicit policy. |
| v1.14 / S-1, S-4, S-6, S-7 | ✅ Done | Shared runtime, explicit bootstrap, observability, durable CI orchestration, release automation, PostgreSQL scale/failure drills, and backup upgrade are verified. |
| Other S-*, M-*, L-* | ⏳ Open | Prioritize the remaining S-2 provider-sync scope, enterprise, and long-term work. |

## v1.14 execution plan — shared runtime and observability

### Outcome and scope

v1.14 establishes a safe multi-worker foundation without changing product
behaviour: shared rate limits, cross-worker realtime delivery, durable CI jobs,
explicit database bootstrap, structured logs, and Prometheus metrics. It
implements S-1, S-4, S-6, and S-7, and moves CI orchestration off the request
path as a substantial part of S-2.

Durable provider execution was pulled forward from v1.15: database-backed jobs
use renewable leases and are recovered by another worker after interruption.
This is intentionally stronger than the originally planned Redis-only status.

### Architecture decisions

- Use one async Redis client owned by the FastAPI lifespan. `REDIS_URL` enables
  the shared backend; single-process development may continue with the bounded
  in-memory implementation when it is absent.
- Add a production guard (`REDIS_REQUIRED=1`) that fails readiness rather than
  silently weakening security when Redis is unavailable. Rate-limited endpoints
  return 503 in this mode; they must not fail open.
- Keep WebSocket objects in per-process memory. Publish logical events to Redis
  channels and let every worker deliver matching events to its local sockets.
- Store CI job status and execution leases in the relational database. Redis
  restarts therefore cannot lose provider work; terminal rows have bounded
  retention.
- Run schema migration and first-admin bootstrap as an explicit one-shot command.
  Application workers validate schema compatibility but do not execute DDL.
- Keep metric labels low-cardinality: route templates, methods, status classes,
  and job/provider types only; never user, project, run, or token identifiers.

### Milestones

#### V14-0 — Runtime contract and Redis infrastructure (1–2 days) — ✅ Done

Implementation:

- Add the pinned Redis client dependency and a central runtime-state module.
- Add `REDIS_URL`, `REDIS_REQUIRED`, key-prefix, socket timeout, and job-TTL
  configuration with safe documented defaults.
- Add Redis to the production Compose stack with persistence policy, healthcheck,
  and app readiness dependency; keep the SQLite development stack Redis-optional.
- Extend `/health` or add `/ready` so liveness does not restart a healthy process
  merely because Redis is temporarily unavailable, while readiness removes it
  from traffic when shared state is required.
- Add a Redis service to CI for integration tests; unit tests continue to run
  without external services through a small backend protocol/fake.

Acceptance:

- The app boots unchanged without `REDIS_URL` in single-worker development.
- Production with `REDIS_REQUIRED=1` is not ready until DB and Redis respond.
- Redis secrets and connection URLs never appear in logs or health responses.

#### V14-1 — Shared rate limiting (2–3 days) — ✅ Done

Implementation:

- Extract a rate-limiter protocol from `backend/rate_limit.py` and retain the
  current bounded in-memory implementation as one backend.
- Implement an atomic Redis sliding window (Lua or transaction) with TTL and
  deterministic `Retry-After` calculation.
- Migrate login, TOTP/2FA, and AI quotas to dependency-provided namespaced
  limiters; preserve their current limits and public error contracts.
- Define outage behaviour explicitly: required Redis returns 503, optional Redis
  uses the in-memory backend only when no Redis configuration was supplied.

Acceptance:

- Two app workers enforce one combined quota, including concurrent attempts.
- Expired keys are removed automatically and storage remains bounded.
- Existing rate-limit unit tests pass against memory and Redis contract suites.
- Redis outage and recovery tests prove there is no silent fail-open path.

#### V14-2 — Cross-worker realtime and durable CI jobs (4–6 days) — ✅ Done

Implementation:

- Refactor `RunWSManager` and `NotificationManager` into local connection
  registries plus a shared event bus interface.
- Publish run and notification events to namespaced Redis Pub/Sub channels;
  create one reconnecting subscriber task per worker during lifespan startup.
- Prevent duplicate local delivery by attaching an event ID/origin and define
  best-effort Pub/Sub semantics explicitly.
- Replace `routers/ci.py::_JOBS` with durable database jobs, atomic claims,
  renewable leases, crash recovery, and bounded terminal retention.
- Ensure shutdown cancels subscribers and closes Redis without leaking tasks.

Acceptance:

- An event produced on worker A reaches a WebSocket connected to worker B.
- Notifications are delivered once per local socket and dead sockets are pruned.
- A CI job created on one worker can be polled from another worker.
- Terminal job records expire, stale leases recover safely, and a Redis
  reconnect does not require restarting the application.

#### V14-3 — Explicit database bootstrap (2–3 days) — ✅ Done

Implementation:

- Add a single command (for example `python -m backend.bootstrap`) that runs
  Alembic, bridges legacy pre-Alembic databases, and creates the initial admin.
- Remove `_ensure_schema()` and `init_db()` writes from normal app lifespan.
- Add a one-shot Compose `bootstrap`/`migrate` service; app workers depend on its
  successful completion. Document the equivalent Kubernetes init-job pattern.
- Provide a one-release compatibility switch for direct non-Compose installs,
  with a warning and a documented removal target.
- Make worker startup detect an outdated schema and exit with an actionable
  message instead of serving traffic against it.

Acceptance:

- Starting two or more workers never races schema DDL or admin creation.
- Fresh, Alembic-managed, and pre-Alembic databases retain regression coverage.
- A failed migration prevents deployment but leaves diagnostic output and a
  documented database-backup/rollback path.
- Existing installations have an explicit, tested upgrade procedure.

#### V14-4 — Structured logs, request IDs, and metrics (3–4 days) — ✅ Done

Implementation:

- Add request-ID middleware: accept a valid incoming `X-Request-ID` or generate
  one, return it in the response, and propagate it through a `contextvars`
  logging filter.
- Support `LOG_FORMAT=json` while retaining readable development logs. Include
  timestamp, level, logger, request ID, method, route template, status, and
  duration; redact authorization, cookies, secrets, query tokens, and URLs.
- Add a configurable `/metrics` endpoint with HTTP count/latency/in-flight,
  active WebSockets, Redis failures/reconnects, and CI-job outcome metrics.
- Add dashboards/alert examples for elevated 5xx, readiness failure, Redis
  errors, migration failure, and CI-job failure rate.

Acceptance:

- Every HTTP response and corresponding application log shares a request ID.
- JSON logs parse line-by-line and contain no credentials or raw JWT/tickets.
- Metrics expose no high-cardinality or customer-content labels.
- Observability middleware covers REST and GraphQL without changing API bodies.

#### V14-5 — Release and scale gate (1–2 days) — ✅ Done

Required verification:

- ✅ Full backend, CLI, frontend build, and Playwright suites.
- ✅ Real Redis integration contracts plus a two-worker PostgreSQL load run.
- ✅ Failure coverage: Redis unavailable at boot, Redis lost/recovered at
  runtime, subscriber reconnect, stale schema, expired CI jobs, and an injected
  failed migration that leaves the Alembic revision unchanged.
- ✅ Repeated `scripts/loadtest.py` against PostgreSQL with one and two workers;
  throughput, p95, zero error rate, and dataset size are in
  `PERFORMANCE_REPORT.md`.
- ✅ PostgreSQL custom-format dump/restore from the v1.13 schema, followed by
  upgrade to `e2a7c4d91f30`, preserved the probe user and created `ci_jobs`.

Release criteria:

- No regression in single-worker/Redis-free development.
- Multi-worker rate limits, WebSocket routing, and CI status tests are green.
- Runbook documents deploy, rollback, Redis backup policy, job recovery
  semantics, metrics, alerts, and provider at-least-once limitations.

### Proposed PR sequence

Each PR must keep CI green and be independently reviewable:

1. `chore(runtime): add Redis infrastructure`
2. `refactor(rate-limit): add shared backend`
3. `feat(realtime): distribute WebSocket events`
4. `refactor(ci): persist job status in Redis`
5. `ops(db): separate bootstrap from app startup`
6. `feat(obs): add structured request logging`
7. `feat(metrics): expose Prometheus metrics`
8. `test(scale): add multi-worker release gate`

### Dependencies and follow-on

- V14-0 gates V14-1 and V14-2. V14-3 and V14-4 can proceed after the runtime
  configuration contract is stable.
- S-1 gates horizontal replicas and L-4. The v1.14 job repository also provides
  the status contract that S-2 can reuse when execution moves to a durable queue.
- After the V14-5 drills, finish the remaining provider-sync scope in S-2 and
  S-5/S-8 before beginning M-1 tenancy.
- M-1 must precede a hosted multi-customer offering and should be designed before
  M-2 SSO/SCIM so tenant identity and provisioning boundaries are explicit.

---

## 0. Immediate fixes (this week — ship-blockers)

| ID | Task | Priority | Impact | Effort | Risk | ROI |
|---|---|---|---|---|---|---|
| I-1 | Add `require_role`/`get_current_user` to **all** Webhooks endpoints (SECURITY C-1) | **P0** | Closes unauth CRUD + secret theft | 0.25d | Low | ★★★★★ |
| I-2 | Add `WRITE_ROLES` to Integrations create/update/delete (SECURITY C-2) | **P0** | Closes unauth config/token retarget | 0.25d | Low | ★★★★★ |
| I-3 | SSRF guard on webhook target + auth on `/webhooks/{id}/test` (SECURITY C-3) | **P0** | Kills blind SSRF | 1d | Low | ★★★★★ |
| I-4 | Validate/realpath attachment paths; reject `..`/separators (SECURITY H-1) | **P0** | Kills arbitrary file write → RCE | 0.5d | Low | ★★★★★ |
| I-5 | Rotate the live Anthropic key; remove real secrets from working-tree `.env` (SECURITY H-3) | **P0** | Stops secret leak | 0.25d | Low | ★★★★★ |
| I-6 | Add negative-authz regression tests for every mutating route (assert 401/403 when anonymous) | **P0** | Prevents recurrence of C-1/C-2 | 1d | Low | ★★★★★ |

**Gate:** do not expose any instance to untrusted networks until I-1…I-5 are merged. I-6 is how you guarantee the class of bug never ships again.

---

## 1. Quick wins (weeks 1–3)

| ID | Task | Pri | Impact | Effort | ROI |
|---|---|---|---|---|---|
| Q-1 | Add indexes on `run_cases(run_id)`, `run_cases(test_id)`, `tests(folder_id, status)`, `defects(status, severity)` (PERF P-7) | P1 | Query latency at scale | 0.5d | ★★★★★ |
| Q-2 | Fix requirement-coverage N+1 in `/api/initial-data` (PERF P-1) | P1 | Fastest-degrading endpoint | 0.5d | ★★★★☆ |
| Q-3 | CSV/formula-injection neutralization in exports (SECURITY M-3) | P1 | Client-side exec risk | 0.5d | ★★★★☆ |
| Q-4 | Raise password policy to ≥12 + HIBP/zxcvbn (SECURITY M-5) | P2 | Account safety | 0.5d | ★★★☆☆ |
| Q-5 | Force admin password change on first login / random seed pw (SECURITY L-2) | P2 | Removes default cred | 0.5d | ★★★★☆ |
| Q-6 | Repo hygiene: `make clean`, stop shipping `.db`/backup files (DEBT D-7) | P2 | Leak/bloat | 0.25d | ★★★☆☆ |
| Q-7 | Pin Python deps with a hashed lock + enable pip-audit/Dependabot (DEBT D-8) | P2 | Supply chain | 0.5d | ★★★★☆ |
| Q-8 | Derive README badge counts (tests/e2e) in CI; fix drift (DEBT D-9) | P3 | Credibility | 0.25d | ★★☆☆☆ |

---

## 2. Short-term (month 1–2)

| ID | Task | Pri | Impact | Effort | ROI |
|---|---|---|---|---|---|
| S-1 | Externalize shared state to Redis: login throttle, AI rate limit, WS registries, CI `_JOBS` (PERF P-4, DEBT D-3) | P1 | Unlocks multi-worker | 8–12d | ★★★★★ |
| S-2 | Move provider sync (GitHub/GitLab/Jira) off request path via task queue (PERF P-5) | P1 | Worker starvation | 5d | ★★★★☆ |
| S-3 | Make Postgres the documented production default; deprecate SQLite for prod (PERF P-3) | P1 | Write contention | 1d | ★★★★☆ |
| S-4 | Separate migration step from app boot (init container / `make migrate`) (DEBT D-2) | P2 | Safe rollouts | 2d | ★★★☆☆ |
| S-5 | Attachment MIME allow-list + `Content-Disposition: attachment` + CSP (SECURITY M-2) | P2 | Stored-XSS/IDOR | 1d | ★★★☆☆ |
| S-6 | Structured JSON logging + request IDs; audit-log coverage review | P2 | Observability | 3d | ★★★☆☆ |
| S-7 | Prometheus `/metrics` endpoint (already on README "planned") | P2 | Ops visibility | 2d | ★★★☆☆ |
| S-8 | Shared SSRF/URL-safety utility used by webhooks, CI, git, AI clients (SECURITY M-1) | P2 | Defense in depth | 2d | ★★★★☆ |

---

## 3. Medium-term (month 3–6)

| ID | Task | Pri | Impact | Effort | ROI |
|---|---|---|---|---|---|
| M-1 | **Object-level authorization / project scoping** — enforce tenancy in query builders (SECURITY H-2) | P1 | Multi-team readiness | 15–25d | ★★★★★ |
| M-2 | **SSO / SAML / OIDC + SCIM provisioning** (enterprise table stakes; competitor gap) | P1 | Mid-market unlock | 15–20d | ★★★★★ |
| M-3 | Frontend: migrate `window` globals → ESM, add route code-splitting (DEBT D-5, PERF FE) | P2 | Load time + maintainability | 10d | ★★★☆☆ |
| M-4 | JWT lifecycle: short-lived access + refresh, per-session revocation (SECURITY M-6) | P2 | Session security | 5d | ★★★☆☆ |
| M-5 | Requirements traceability matrix + baselining (Squash/Xray parity) | P2 | Regulated markets | 10d | ★★★★☆ |
| M-6 | Push-based result reporters (Playwright/Cypress/pytest) à la Kiwi | P2 | Onboarding friction | 8d | ★★★★☆ |
| M-7 | S3-compatible attachment storage (README "planned") | P3 | Scale/durability | 4d | ★★★☆☆ |
| M-8 | Response caching (short-TTL) for `/insights`, `/initial-data` (PERF P-6) | P3 | Concurrency | 3d | ★★★☆☆ |

---

## 4. Long-term (month 6–12)

| ID | Task | Pri | Impact | Effort | ROI |
|---|---|---|---|---|---|
| L-1 | Migrate ISO-string timestamps → native `DateTime` columns (DEBT D-4) | P3 | Correctness/perf | 10d | ★★★☆☆ |
| L-2 | Retire legacy `_run_migrations()` path once no pre-Alembic installs remain (DEBT D-1) | P3 | Single source of truth | 2d | ★★★☆☆ |
| L-3 | Scheduled/exportable reports + BI export (TestRail parity) | P2 | Enterprise demand | 10d | ★★★★☆ |
| L-4 | Horizontal scale-out hardening: read replicas, event bus for WS, per-tenant limits | P3 | 10k+ users | 20d+ | ★★★☆☆ |
| L-5 | Licensing decision: reconsider Commons Clause vs. true OSI (COMPETITOR) — strategic, not eng | P1 | Adoption/monetization | — | ★★★★★ |
| L-6 | CLI `run` (trigger + wait) and npm publish (README "next") | P2 | DX / CI adoption | 5d | ★★★☆☆ |

---

## Dependency notes
- **S-1 (Redis state) gates** any multi-worker/replica deployment and therefore gates L-4.
- **M-1 (tenancy) gates** a hosted multi-customer offering and interacts with M-2 (SSO/SCIM).
- **I-1…I-6 gate** any external exposure and should merge before a public demo instance.
- **S-3 (Postgres default) gates** realistic load testing (run `scripts/loadtest.py` after).

## Suggested sequencing (quarters)
- **Q1:** Immediate fixes + all Quick wins + S-1/S-2/S-3 (secure + multi-worker + Postgres).
- **Q2:** M-1 tenancy + M-2 SSO/SCIM (enterprise unlock) + M-4 JWT + observability.
- **Q3:** M-3 FE modernization + M-5 traceability + M-6 reporters + L-3 reporting.
- **Q4:** L-1/L-2 debt paydown + L-4 scale hardening + L-6 CLI; execute L-5 license decision.
</content>
