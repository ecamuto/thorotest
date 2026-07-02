# Production Readiness Roadmap

Outcome of full-codebase commercial review (2026-07-02). Verdict: strong beta,
not yet sellable production. Items ordered by priority — work top to bottom.

## Status

| # | Item | Severity | Status |
|---|------|----------|--------|
| 1 | Kill/gate fake run simulation | Critical | ✅ Done — gated behind `DEMO_MODE` (default off) |
| 2 | Frontend production build + vendor assets | Critical | ✅ Done — esbuild build to `frontend/dist`, no CDN/external requests |
| 3 | Pagination on list endpoints + trim `/api/initial-data` | High | ⬜ Todo |
| 4 | `/health` endpoint, structured logging, app healthcheck in compose | Medium | ⬜ Todo |
| 5 | Password reset flow + SMTP send | Medium | ⬜ Todo |
| 6 | Alembic migration baseline (replace homegrown `_run_migrations`) | High | ⬜ Todo |
| 7 | Backup/restore docs + uploads volume in docker-compose | Medium | ⬜ Todo |

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

### 3. No pagination (HIGH — dies at scale)
46 unpaginated `.all()` calls across routers (only audit log paginates).
`/api/initial-data` serializes the entire DB on every app load. Insights
endpoint has an N+1 loop (query per flaky test). TestRail migrators bring
50k+ cases — product will stop responding.
Fix: limit/offset (or cursor) on list endpoints, cap initial-data payload,
rewrite flaky-test loop as a join. Estimate 3–5 days.

### 4. Zero observability (MEDIUM — enterprise checklist)
No `/health` endpoint, no logging config, no metrics. Docker healthcheck
exists for Postgres only, not the app.
Fix: `/health` (DB ping), uvicorn/structlog logging config, healthcheck in
docker-compose for app service. Estimate 1 day.

### 5. No password reset (MEDIUM — first support ticket)
SMTP columns exist on `NotificationConfig` model but there is no
forgot-password endpoint and no email sending anywhere.
Fix: reset-token flow + SMTP send using existing config. Estimate 2 days.

### 6. Homegrown migrations (HIGH — upgrade cycles)
`main.py:_run_migrations()` is a hand-rolled ALTER TABLE list, every column
VARCHAR(255). Unmaintainable across paid-customer upgrades.
Fix: Alembic baseline now, before customers hold data. Estimate 2 days.

### 7. Data durability (MEDIUM)
Attachments on local disk (`./uploads`), no volume in docker-compose →
lost on container rebuild. No backup/restore docs.
Fix: uploads volume + backup docs (pg_dump / sqlite copy + uploads dir).
Estimate 1 day. S3 storage backend can be v1.1.

## Lower-priority notes (not blocking v1)

- WS notifications JWT passed as query param (`main.py`) — lands in access
  logs. Consider ticket-based WS auth.
- Single-process state: login rate limiter + WS managers are in-memory —
  one uvicorn worker only. Document the limit; Redis backing is v1.1.
- No multi-tenancy — fine for self-host per-instance licensing; blocks SaaS.
- License is MIT + Commons Clause = **source-available**, not open source,
  but `frontend/index.html` title says "Open-source". Fix branding.
  Commons Clause does not block third-party SaaS hosting — decide if that
  matters.
- SSO/SAML/SCIM: v1.1 pricing tier.

## Strengths (keep selling these)

- Manual + automated runs in one timeline (differentiator vs TestRail/Zephyr).
- Import pipeline: TestRail XML, JUnit, CSV, YAML, JSON + auto-detect.
- REST + GraphQL + API tokens + HMAC webhooks.
- Auth stack: argon2id, token revocation, TOTP 2FA, OAuth (GitHub/Google),
  RBAC, audit log, login rate limiting, prod boot-refusal on default secret.
- 332 pytest + ~200 Playwright tests, CI-gated.
- i18n (en/it/de/es/fr), BYOK AI assistant, SQLite/Postgres/MySQL support.
