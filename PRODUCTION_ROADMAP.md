# Production Readiness Roadmap

Outcome of full-codebase commercial review (2026-07-02). Verdict: strong beta,
not yet sellable production. Items ordered by priority — work top to bottom.

## Status

| # | Item | Severity | Status |
|---|------|----------|--------|
| 1 | Kill/gate fake run simulation | Critical | ✅ Done — gated behind `DEMO_MODE` (default off) |
| 2 | Frontend production build + vendor assets | Critical | ✅ Done — esbuild build to `frontend/dist`, no CDN/external requests |
| 3 | Pagination on list endpoints + trim `/api/initial-data` | High | ✅ Done — limit/offset + X-Total-Count, capped initial-data, N+1s fixed |
| 4 | `/health` endpoint, logging, app healthcheck in compose | Medium | ✅ Done |
| 5 | Password reset flow + SMTP send | Medium | ✅ Done |
| 6 | Alembic migration baseline (replace homegrown `_run_migrations`) | High | ✅ Done |
| 7 | Backup/restore docs + uploads volume in docker-compose | Medium | ✅ Done |

## Post-v1 features

| Version | Feature | Status |
|---|---|---|
| 1.1 | Requirements & test coverage (features/stories/epics ↔ tests, coverage metrics, YAML/JSON/CSV import, GraphQL) | ✅ Done — `feat/requirements-coverage` |
| 1.2 | Jira integration (pull stories → requirements, push defects → bugs) — reuses `external_*` fields shipped in 1.1 | ✅ Done — `feat/jira-integration` |
| 1.3 | External importers (TestRail/TestLink XML, qTest/Xray/Zephyr JSON, real .xlsx) + external-identity matching/dedup | ✅ Done — `feat/external-importers` |
| 1.4 | Test Plans, real-time run execution over WebSocket, API-token auth, pipeline ingest, GitHub Actions CI (trigger + collect), UI-honesty cleanup | ✅ Done — `feat/test-plans` |

## Item detail

### 1. Fake run simulation (CRITICAL — product integrity) — DONE
`backend/ws_manager.py` `_simulate()` assigned **random** outcomes
(80/15/5 pass/fail/blocked) to any run with status `running` as soon as a
WebSocket client connected (`main.py` run_ws handler). Real customer runs got
invented results. Fixed: simulation now runs only when `DEMO_MODE=1` is set;
default is off. Real result paths (manual case PATCH, step results, JUnit
import) unaffected.

### 2. Frontend not production-grade (CRITICAL — perf + self-host promise) — DONE
Was: React **development** builds + Babel standalone from unpkg CDN, ~17 jsx
files transpiled in-browser per page load, Google Fonts external.
Now: `npm run build` (scripts/build-frontend.mjs, esbuild) transpiles +
minifies to `frontend/dist/`; React production UMD vendored from
node_modules; Geist + JetBrains Mono woff2 vendored in `frontend/fonts/`.
Zero external requests — works airgapped. Backend serves dist (falls back to
source dir with a warning so API-only boots still work). Docker is now a
multi-stage build (node builds frontend → python runtime). Cache busting via
`?v=<hash>` stamped on asset URLs.
Scoping note: the old Babel-standalone runtime effectively made every
top-level declaration a global. The build wraps each .jsx in an IIFE;
`frontend/react-globals.js` exposes React hooks globally (files use them
bare), and cross-file components must be exported with `window.X = X`
(Metric and Detail were fixed during migration). Full e2e suite: 202/202.

### 3. No pagination (HIGH — dies at scale) — DONE
Was: 46 unpaginated `.all()` calls, `/api/initial-data` serialized the whole
DB per app load, insights had query-per-test and query-per-folder loops.
Now: `/api/tests|runs|defects|pipelines|activity` accept `limit`/`offset`
(hard cap 1000, activity default 200) and return the filtered total in the
`X-Total-Count` header — responses stay plain arrays, fully backward
compatible (`backend/routers/_pagination.py`). `/api/initial-data` caps each
collection (tests 1000 / runs 500 / defects 500 / pipelines 200 /
activity 100) and reports real counts in a new `totals` key. Insights (REST
and GraphQL) rewritten as SQL aggregates/GROUP BYs; GraphQL `tests`/`runs`/
`defects` resolvers take limit/offset too.
Follow-up for v1.1: UI page controls + "showing N of M" indicator using
X-Total-Count / totals (today the UI just shows the capped slice), and
server-side sorting params.

### 4. Zero observability (MEDIUM — enterprise checklist) — DONE
`/health` added: unauthenticated, pings the DB (`SELECT 1`), returns 200
ok / 503 degraded plus uptime — safe for load balancers and monitors (no
version/config leakage). App logging configured via `logging.basicConfig`
with `LOG_LEVEL` env override. Docker: `HEALTHCHECK` in the image and app
healthchecks in both compose files (urllib against /health).
Still open for v1.1: metrics endpoint (Prometheus) if customers ask.

### 5. No password reset (MEDIUM — first support ticket) — DONE
`POST /api/auth/forgot-password` (always 202, no user enumeration, reuses
the login rate-limit window) emails a single-use link valid 1 hour;
`POST /api/auth/reset-password` validates the hashed token, sets the new
password and bumps `token_version` (revokes all existing sessions). Both
audit-logged. Email goes through new `backend/emailer.py` using env SMTP
(`SMTP_HOST/PORT/USER/PASS/FROM`) — env, not the per-user NotificationConfig
SMTP columns, because system mail must work before any user is configured.
Unset SMTP_HOST = emails skipped, API responds normally. Login UI gained
forgot/reset screens (`#/reset-password/<token>` route).
Known e2e flake (pre-existing): suite11 login `waitForURL` timeout, seen
twice under parallel workers, always passes on rerun — worth a look someday.

### 6. Homegrown migrations (HIGH — upgrade cycles) — DONE
Schema is now Alembic-managed (`alembic.ini` + `migrations/`, baseline
revision `e8e566ab263b` autogenerated and verified to reproduce the
`create_all` schema exactly — 27 tables). On boot `_ensure_schema()`:
fresh DB → `upgrade head`; pre-Alembic DB → one-time legacy ALTERs then
`stamp head`; managed DB → `upgrade head`. Legacy `_run_migrations()` kept
only for the stamping path. Workflow: `make db-revision m="…"` +
`make db-upgrade` (documented in README). Docker image ships alembic.ini +
migrations/. `python -m backend.seed` uses the same bootstrap.
Rule going forward: every `models.py` change ships an Alembic revision.
Known e2e flake (suite11 login, pre-existing) seen 3rd time; rerun green.

### 7. Data durability (MEDIUM) — DONE
Uploads now persist: named volume `uploads_data:/app/uploads` in the
Postgres compose file, `./uploads` bind mount in the SQLite compose file.
`BACKUP.md` documents backup/restore for SQLite (`.backup` snapshot),
PostgreSQL (`pg_dump`/`pg_restore`), MySQL, and the Docker variants, plus a
cron example — always DB + uploads/ together, backup before upgrades.
S3 attachment storage remains a v1.1 item.

## Lower-priority notes (not blocking v1)

- WS notifications JWT passed as query param (`main.py`) — lands in access
  logs. Consider ticket-based WS auth.
- Single-process state: login rate limiter + WS managers are in-memory —
  one uvicorn worker only. Document the limit; Redis backing is v1.1.
- No multi-tenancy — fine for self-host per-instance licensing; blocks SaaS.
- License is MIT + Commons Clause = **source-available**, not open source.
  Branding fixed: UI title is "ThoroTest — Test management", README/TERMS
  say "source-available" — no stale "Open-source" claim remains.
  Commons Clause does not block third-party SaaS hosting — decide if that
  matters.
- SSO/SAML/SCIM: v1.1 pricing tier.

## Scaling baseline (measured 2026-07-10)

Single uvicorn worker, SQLite (default), read load, localhost (no network
RTT), presentation dataset (818 tests / 17 runs). Async httpx driver,
5s per level. Machine: 10-core (worker uses ~1 core — the app is
core-bound). Reproduce: `python scripts/loadtest.py` against a running server.

| Endpoint | conc 1 | conc 4 | conc 8 | conc 16 | conc 32 |
|---|---|---|---|---|---|
| light `/api/tests?limit=50` — rps | 172 | 167 | 111 | 88 | 91 |
| &nbsp;&nbsp;p95 ms | 6.7 | 30 | 89 | 222 | 493 |
| mixed reads (tests/runs/defects/activity) — rps | 405 | 434 | 287 | 221 | 215 |
| &nbsp;&nbsp;p95 ms | 5.7 | 16 | 60 | 163 | 252 |
| heavy `/api/initial-data` — rps | 30 | 30 | 31 | 30 | — |
| &nbsp;&nbsp;p95 ms | 72 | 188 | 372 | 687 | — |

**Reading it:** throughput is flat-to-declining with concurrency — one
core (GIL) + `QueuePool` size 5 serialize the work; extra concurrency buys
latency, not throughput. `/api/initial-data` is pinned at ~30 rps (it
serializes the whole workspace). Latency stays healthy (p95 < 250 ms)
through ~conc 16–32 for list reads.

**Concurrent interactive users (Little's law, ~1 action / 3–5 s):**
~300–500 before p95 degrades, gated by `/api/initial-data` on app-open
bursts (~800–1200 if the SPA is already loaded and only hits list reads).

**Caveats:** reads only (SQLite writes take a global writer lock — a
write-heavy mix is lower); localhost adds no RTT; WS and login paths not
loaded. A 1–2 vCPU prod VM lands similar per-core (core-bound).

**Levers, ranked:**

1. Cache/trim `/api/initial-data` (the 30 rps ceiling) — biggest win, no new infra.
2. Bump `QueuePool` size (esp. Postgres, one line) — helps once not one-core-bound.
3. Multi-worker = real throughput multiplier (+1 core each), but **needs the
   Redis item above first** (in-memory rate limiter + WS state break across
   workers). This is what gates horizontal scale.
4. ~~Latent wart: `/health` runs a **sync** `engine.connect()` inside an
   `async def` — blocks the event loop per call; move to the threadpool.~~
   Fixed: the DB ping now runs via `asyncio.to_thread`.

## Strengths (keep selling these)

- Manual + automated runs in one timeline (differentiator vs TestRail/Zephyr).
- Import pipeline: TestRail (XML/CSV), TestLink XML, Zephyr Scale, Xray, qTest,
  JUnit, Allure, CSV/XLSX + auto-detect, external-identity matching & re-import dedup.
- REST + GraphQL + API tokens + HMAC webhooks.
- Auth stack: argon2id, token revocation, TOTP 2FA, OAuth (GitHub/Google),
  RBAC, audit log, login rate limiting, prod boot-refusal on default secret.
- 332 pytest + ~200 Playwright tests, CI-gated.
- i18n (en/it/de/es/fr), BYOK AI assistant, SQLite/Postgres/MySQL support.
