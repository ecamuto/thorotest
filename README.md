# ThoroTest

Source-available test management platform. Organize, run, and track tests across manual and automated suites — one timeline for both. Trace features, stories, and epics to the tests that cover them, and see coverage at a glance.

---

## Stack

| Layer | Tech |
|---|---|
| Frontend | React 18 (vendored production UMD), JSX transpiled + minified by esbuild at build time |
| Backend | FastAPI, SQLAlchemy |
| Database | SQLite (default) · PostgreSQL · MySQL / MariaDB (via `DATABASE_URL`) |
| Realtime | WebSocket (native FastAPI) |
| API | REST + GraphQL (Strawberry) |
| Auth | JWT (python-jose), passlib (sha256_crypt) |
| AI | Anthropic SDK (BYOK — optional) |
| Export | PDF (fpdf2), CSV |
| Tests | pytest, httpx, Playwright |
| Deploy | Docker + docker-compose |

Fully self-contained: React, fonts, and all assets are served locally — no CDN or external requests, works airgapped. `npm run build` produces `frontend/dist/` (run automatically by `make dev`, `install.sh`, and the Docker build).

---

## Quickstart

### Local (SQLite, no Docker)

```bash
bash install.sh  # create venv, install deps, copy .env.example → .env
make dev         # start server → http://localhost:8000
make open        # open app in browser
```

### Docker + PostgreSQL

```bash
cp .env.example .env   # edit SECRET_KEY before production
make docker-up         # build image + start app and Postgres
make open
```

### Docker + SQLite

```bash
cp .env.example .env
make docker-up-sqlite
```

Database is created automatically on first run. Seed data: 19 test cases across 12 folders, 11 runs, 6 pipelines, 9 defects.

---

## Make commands

| Command | Description |
|---|---|
| `make setup` | Full setup: venv + deps + Playwright |
| `make install` | Re-install deps into existing venv |
| `make dev` | Build frontend + start backend dev server on `http://localhost:8000` (hot-reload) |
| `make frontend-build` | Build frontend to `frontend/dist/` (transpile + minify + vendor assets) |
| `make frontend-watch` | Rebuild frontend on change (run beside `make dev` when editing UI) |
| `make db-reset` | Delete `testhub.db` — re-seeded on next `make dev` |
| `make db-revision m="…"` | Create Alembic migration from model changes (autogenerate) |
| `make db-upgrade` | Apply pending Alembic migrations |
| `make db-seed` | Populate DB with demo data |
| `make demo` | Alias for `make db-seed` |
| `make test` | Run backend unit tests (pytest) |
| `make test-e2e` | Run all Playwright e2e tests (requires `make dev` running) |
| `make test-e2e-auth` | Run auth e2e suite only |
| `make test-report` | Open last Playwright HTML report |
| `make open` | Open `http://localhost:8000` in default browser |
| `make docker-up` | Build image + start app and Postgres |
| `make docker-up-sqlite` | Build image + start app with SQLite |
| `make docker-down` | Stop and remove Docker containers |
| `make docker-logs` | Tail Docker container logs |
| `make clean` | Remove venv, node_modules, DB, test artifacts |

---

## Configuration

Copy `.env.example` to `.env`:

```bash
cp .env.example .env
```

| Variable | Default | Description |
|---|---|---|
| `DATABASE_URL` | `sqlite:///./testhub.db` | Database connection string |
| `SECRET_KEY` | `thorotest-dev-secret-...` | JWT signing key — **change in production** |
| `TESTHUB_BASE_URL` | `http://localhost:8000` | Public base URL (OAuth callbacks, default CORS origin) |
| `ALLOWED_ORIGINS` | = `TESTHUB_BASE_URL` | CORS origins — comma-separated list, or `*` for any (dev only) |
| `LOG_LEVEL` | `INFO` | Application log level (`DEBUG`, `INFO`, `WARNING`, …) |
| `SMTP_HOST` / `SMTP_PORT` / `SMTP_USER` / `SMTP_PASS` / `SMTP_FROM` | _(unset)_ | Outbound email for password resets. No-op if `SMTP_HOST` absent |
| `UPLOAD_DIR` / `MAX_UPLOAD_MB` | `./uploads` / `50` | Attachment storage directory and per-file size limit |
| `DEMO_MODE` | _(unset)_ | Live-run demo simulation with fabricated results (demos only — **never in production**) |
| `ANTHROPIC_API_KEY` | _(unset)_ | Enables AI assistant (BYOK). No-op if absent |
| `AI_PROVIDER` | `anthropic` | AI backend: `anthropic` or `openai` (any OpenAI-compatible API, incl. local LLMs) |
| `AI_MODEL` | `claude-sonnet-4-6` | Model ID. Required when `AI_PROVIDER=openai` |
| `AI_BASE_URL` | `https://api.openai.com/v1` | OpenAI-compatible endpoint (e.g. `http://localhost:11434/v1` for Ollama). Setting it implies `AI_PROVIDER=openai` |
| `AI_API_KEY` | _(unset)_ | API key for the OpenAI-compatible endpoint (any value for local servers) |
| `GITHUB_CLIENT_ID` / `GITHUB_CLIENT_SECRET` | _(unset)_ | GitHub OAuth login (optional) |
| `GOOGLE_CLIENT_ID` / `GOOGLE_CLIENT_SECRET` | _(unset)_ | Google OAuth login (optional) |
| `JIRA_AUTOSYNC_MINUTES` | `0` | Auto-sync all Jira integrations every N minutes (`0` = disabled). Requires outbound reachability to Jira Cloud |

Database URLs:

```bash
# SQLite (default)
DATABASE_URL=sqlite:///./testhub.db

# PostgreSQL
DATABASE_URL=postgresql://user:pass@localhost:5432/thorotest

# MySQL / MariaDB
DATABASE_URL=mysql+pymysql://user:pass@localhost:3306/thorotest
```

Generate a secure `SECRET_KEY`:

```bash
python3 -c "import secrets; print(secrets.token_hex(32))"
```

**Backups:** all state lives in the database plus the `uploads/` directory —
see [BACKUP.md](BACKUP.md) for backup/restore procedures per database and for
Docker deployments.

---

## Tests as Code (GitHub + GitLab sync)

Keep tests defined as YAML in a Git repo and mirror them into ThoroTest. Works with **GitHub** (`github.com`) and **GitLab** (`gitlab.com` or self-hosted). The test-detail page shows the real file path, synced commit, raw YAML, and a link to the exact file at that commit.

Sync is **two-way**:

- **Pull** (Git → ThoroTest): reads the YAML schede and creates/updates tests.
- **Push** (ThoroTest → Git): the test-detail YAML card has a **Push to git** button that commits the test's current state back to its source file. A conflict guard returns **409** if the file changed on Git since the last sync — re-sync first so you don't overwrite a change made on Git.

### Setup

1. **Settings → Integrations → Add → GitHub** (or **GitLab**)
2. Fill in:
   - **Repository URL** — `https://github.com/acme/web` or `https://gitlab.com/acme/web`
   - **Provider** — `github` / `gitlab`. Inferred from the host for the public clouds; **required** for self-hosted GitLab (any other host).
   - **API base** _(GitLab only, optional)_ — e.g. `http://gitlab.internal/api/v4`; derived from the repo URL when omitted.
   - **Branch** — e.g. `main`
   - **Path** — folder holding the YAML tests, e.g. `tests/`
   - **Personal access token** — needed for private repos and for **Push to git** (GitHub `contents: write`, GitLab `api`). Stored in the integration config; never returned to clients (the API reports only `token_set: true`).
3. Click **Sync** on the integration row. ThoroTest reads every `*.yml` / `*.yaml` under the path at the latest commit, then creates/updates the matching tests and caches the file contents + commit sha.

Re-syncing is idempotent: tests are matched by their YAML `id` (or, when absent, by repo + file path), so a second sync updates in place instead of duplicating.

### YAML test format

```yaml
id: TC-2301                       # stable id, reused as the test's primary key (optional)
title: "Stripe card charge succeeds on test card"
type: automated                   # automated | manual  (aliases: e2e/auto/unit → automated)
runner: playwright
priority: high                    # low | med | high | critical  (aliases: P0–P3)
owner: anna@example.com
tags: [smoke, payment]
folder: Checkout/Payment          # "/"-separated folder hierarchy, auto-created
```

Only `title` is required. Malformed files are skipped and reported in the sync result (`warnings`), not fatal.

**Status is not a YAML field.** A test's status is owned by real CI run results, not a hand-written value, so sync never reads a `status:` from the file and push never writes one back. See **[CI status link](#linking-schede-to-ci-results)** below for how run results flow onto the scheda.

### Endpoints

- `POST /api/integrations/{id}/sync` (admin/manager) → `{ created, updated, skipped, commit, files, warnings, last_sync }`. Routes to GitHub or GitLab by the integration's provider.
- `POST /api/tests/{id}/push-to-git` (admin/manager) → `{ ok, committed, commit, path, branch }`. **409** when the file diverged on Git; **400** when the test has no Git source or no integration matches its repo.

---

## Jira integration

Two-way link with Jira Cloud, sharing one `jira` integration
(**Settings → Integrations → Add → Jira**). Config: `base_url`, `email`,
`api_token`, `project_key`, and the bug issue type.

- **Pull** (inbound): **Sync** runs a JQL query (`project = KEY AND issuetype in
  (Story, Epic)`) and upserts matching issues as requirements — matched by
  `external_key`, with Jira status/issuetype mapped to requirement status/type. Local
  test links are preserved across re-syncs.
- **Push** (outbound): on the Defects view, **Push to Jira** creates a bug from a defect
  (`POST /api/defects/{id}/push`, admin/manager) and stores the issue key + URL on the
  defect. Re-pushing a linked defect is rejected (409).

Both reuse the `external_provider` / `external_key` / `external_url` fields shipped in
v1.1 on Requirement and Defect — no schema change.

**Auto-sync (optional):** set `JIRA_AUTOSYNC_MINUTES` > 0 to have the backend pull every
Jira integration on that interval — no manual Sync needed. Per-integration failures are
logged and skipped, so one misconfigured integration can't stall the others. Off by
default (`0`); needs outbound reachability to Jira Cloud (works self-hosted, no public
endpoint required, unlike an inbound webhook).

**Security:** `api_token` is stored in the integration config and **never returned to
clients** — the API reports only `api_token_set: true`, and a blank value on edit keeps
the stored secret (same handling as the GitHub PAT). `base_url` must be `https`. The push
endpoint publishes the defect title/description to Jira and is admin/manager only.

---

## Requirements & coverage

Track features, stories, and epics as **requirements**, and link each to the tests that
verify it. The Requirements view shows a coverage bar per requirement (passed / failed /
untested) and the Overview surfaces a workspace-wide coverage summary — including
**uncovered** requirements and those **at risk** (with a failing linked test). Each test's
detail page lists the requirements it covers.

Requirements carry `external_provider` / `external_key` / `external_url` fields so they can
later be linked to an external tracker (e.g. Jira) — the same fields exist on defects.

### Bulk import

`POST /api/requirements/import` accepts a YAML, JSON, or CSV file and upserts requirements
(matched by `id`, else by `title`). Linked tests are matched by id; unknown ids are
reported as `warnings` rather than failing the import.

```yaml
- id: REQ-103                 # optional stable id (generated if absent)
  title: "Checkout — card payments"
  type: feature               # feature | story | epic
  status: active              # draft | active | done | deprecated
  priority: high              # low | med | high | critical
  owner: luca@example.com
  tests: [TC-2301, TC-2302]   # linked test ids (CSV: space/comma separated)
```

---

## Test import

Bring existing test cases — and, where the source has them, run results — in from other
test-management tools. Upload a file (the format is **auto-detected**), **preview** the
parsed counts and a sample before anything is written, then run the import and choose how
duplicates are handled.

| Source | Format | Notes |
|---|---|---|
| TestRail | XML · CSV | Native export; nested sections → folders |
| TestLink | XML | Nested `<testsuite>` → folders; importance/execution_type mapped |
| Zephyr Scale (TM4J) | JSON | Test cases + executions → runs (per cycle) |
| Xray (for Jira) | JSON | Test definitions **and** execution results (results link by issue key) |
| qTest | JSON | `properties` array flattened; `pid` as identity |
| JUnit | XML | Automated results → a run with pass/fail/skip |
| Allure | JSON | Results array → a run |
| Excel | `.xlsx` | First worksheet, via column mapping |
| Azure Test Plans / generic | CSV · XLSX | Column mapping (auto-detected aliases, overridable in the UI) |

**Matching & de-duplication.** Imported tests store `external_provider` / `external_key`
(the source tool and its case id). A re-import matches on that identity — updating or
skipping rather than duplicating — so re-running the same export is idempotent, and
same-titled cases in **different folders** stay distinct. Runs de-dupe on the source
cycle/execution id; defects on `(external_provider, external_key)`. For sources without a
stable id, matching falls back to `(title, folder)`.

**Endpoints** (`admin` / `manager` / `tester`; 10 MB max):

- `POST /api/import/detect` — detected format (+ column headers for spreadsheets)
- `POST /api/import/preview` — parsed counts and a sample, **no writes**
- `POST /api/import/execute` — persist; `conflict` = `skip` | `overwrite` | `rename`

---

## CI: run pipelines and import results

Trigger a project's pipeline from ThoroTest and import its results automatically
when the run finishes (Configure ▸ Integrations ▸ **Run CI**). Both providers are
supported:

- **GitHub Actions** — dispatch a `workflow_dispatch` workflow, then download and
  import its JUnit artifact. See **[docs/github-actions-ci.md](docs/github-actions-ci.md)**
  for workflow requirements, token setup, and API usage.
- **GitLab CI** — create a pipeline, poll it, and import its `test_report`
  (jobs just need `artifacts: reports: junit:`). A local, dockerised demo lives
  in **[demo/gitlab/](demo/gitlab/)**.

Each dispatch also appears on the **Pipelines** page (running → pass/fail, with
commit, branch, and duration) — not only as an imported Run.

### Linking schede to CI results

A CI run's results are attached to the **same** test row the YAML scheda created
(no duplicate), and the scheda's status is advanced to the real run result. The
link is a correlation id: put the scheda's `id` in the automated test's name (or
class), e.g. a Playwright title `login with valid credentials [TC-GL-100]` or a
trailing `..._TC_GL_100`. On import, ThoroTest extracts that `TC-…` token and
matches it to the scheda. Tests without a token still import as their own
automated tests, so tagging is opt-in.

So the full loop is: **Sync** creates schede (status `pending`) → **Run CI** runs
the real pipeline → results link back and flip the schede to `pass`/`fail`. Status
lives in one place (the run), never in the YAML.

---

## Project structure

```
thorotest/
├── frontend/
│   ├── index.html              # Entry point — loads all scripts
│   ├── styles.css              # All styles (CSS variables, components)
│   ├── data.js                 # Static fallback data (TH_DATA)
│   ├── api.js                  # HTTP + WebSocket client helpers (TH_API)
│   ├── i18n.js                 # i18n string lookup (T(key, lang))
│   ├── react-globals.js        # Exposes React hooks as globals for the views
│   ├── fonts.css / fonts/      # Vendored webfonts (Geist, JetBrains Mono)
│   ├── dist/                   # Build output (npm run build) — served by the app
│   ├── app.jsx                 # Root App component + boot + hash routing
│   │
│   ├── components/
│   │   ├── app-shell.jsx       # Sidebar, topbar, nav structure
│   │   ├── hooks.jsx           # Shared React hooks (useInitialData)
│   │   ├── icons.jsx           # SVG icon components
│   │   ├── i18n-context.jsx    # React context for active language
│   │   ├── notification-bell.jsx # Notification bell + dropdown (WebSocket push)
│   │   └── tweaks-panel.jsx    # Developer panel (theme, density)
│   │
│   ├── locales/                # i18n string files (en, it, …)
│   │
│   └── views/
│       ├── view-login.jsx          # Login page (public)
│       ├── view-overview.jsx       # Dashboard — metrics, runs, activity
│       ├── view-library.jsx        # Test library — folder tree + list/grid
│       ├── view-test-detail.jsx    # Test case — steps, history, defects, comments
│       ├── view-runs.jsx           # Runs list + live run detail (WebSocket)
│       ├── view-defects.jsx        # Defect management
│       ├── view-requirements.jsx   # Requirements + test coverage
│       ├── view-settings.jsx       # Profile, password, tokens, webhooks, integrations
│       ├── view-admin.jsx          # User and role management (admin only)
│       ├── view-import.jsx         # Test import (CSV/XLSX/XML/JSON, auto-detect + mapping)
│       ├── view-my-work.jsx        # Personal work queue and assignments
│       ├── view-docs.jsx           # Documentation viewer
│       ├── view-config.jsx         # Config-as-code view
│       └── view-misc.jsx           # Pipelines, Insights, AI assistant
│
├── scripts/
│   └── build-frontend.mjs  # esbuild production build (npm run build)
├── migrations/             # Alembic migrations (baseline + future revisions)
├── alembic.ini             # Alembic config (DATABASE_URL-driven)
├── BACKUP.md               # Backup & restore procedures
├── backend/
│   ├── main.py             # FastAPI app, lifespan, /api/initial-data, WebSocket
│   ├── db.py               # SQLAlchemy engine, session, Base
│   ├── models.py           # ORM models
│   ├── schemas.py          # Pydantic schemas
│   ├── seed.py             # Demo seed data (runs on first boot if DB empty)
│   ├── auth_utils.py       # JWT creation/validation, password hashing (passlib)
│   ├── ws_manager.py       # WebSocket connection manager + demo run simulation (DEMO_MODE)
│   ├── emailer.py          # Outbound system email (password resets) via env SMTP
│   ├── gql_schema.py       # Strawberry GraphQL schema
│   ├── github_sync.py      # Tests-as-Code: read YAML tests from a GitHub repo
│   ├── jira_sync.py        # Jira Cloud: pull stories→requirements, push defects→bugs
│   └── routers/
│       ├── _pagination.py  # Shared limit/offset + X-Total-Count helper
│       ├── auth.py         # /auth/register, /auth/login, /me, /users, password reset
│       ├── tests.py        # CRUD /api/tests + bulk + history + comments + defects
│       ├── runs.py         # /api/runs + run detail + defects
│       ├── folders.py      # GET /api/folders (nested tree)
│       ├── defects.py      # CRUD /api/defects (filters: status, severity, test, run)
│       ├── requirements.py # CRUD /api/requirements + coverage + link tests + import
│       ├── projects.py     # CRUD /api/projects
│       ├── categories.py   # CRUD /api/categories
│       ├── integrations.py # CRUD /api/integrations + GitHub YAML sync
│       ├── tokens.py       # GET/POST/DELETE /api/tokens
│       ├── webhooks.py     # CRUD /api/webhooks + test endpoint
│       ├── attachments.py  # Upload/download file attachments per test or run
│       ├── ai.py           # AI assistant endpoint (BYOK — Anthropic)
│       ├── admin.py        # User management, role assignment (admin only)
│       ├── favorites.py    # Favorite tests per user
│       ├── import_.py      # Test import API (detect/preview/execute) — parsers in ../importers/
│       ├── pipelines.py    # GET /api/pipelines
│       ├── activity.py     # GET /api/activity, GET /api/defects
│       ├── notifications.py # Notifications list/read + per-user config
│       ├── audit_log.py    # Audit log query (admin)
│       ├── oauth.py        # GitHub / Google OAuth login + account linking
│       └── totp.py         # TOTP two-factor auth enable/verify
│
├── e2e/
│   ├── fixtures/                   # Shared Playwright fixtures
│   ├── suite1-auth/                # Login, register, session persistence
│   ├── suite2-navigation/          # Hash routing, back/forward, nav links
│   ├── suite3-library/             # Folder tree, filters, multi-select
│   ├── suite4-test-detail/         # Test detail tabs (definition, history, defects, comments)
│   ├── suite5-runs/                # Run list, run detail, WebSocket live updates
│   ├── suite6-overview/            # Dashboard metrics
│   ├── suite7-pipelines/           # Pipeline cards
│   ├── suite8-tweaks/              # Theme and density panel
│   ├── suite9-security/            # Auth guards, protected routes
│   ├── suite10-settings/           # Profile, password, tokens, webhooks
│   ├── suite11-defects-view/       # Defects list and management
│   ├── suite12-integrations/       # Integrations CRUD
│   ├── suite13-docs/               # Documentation viewer
│   ├── suite14-extra/              # Miscellaneous edge cases
│   ├── suite15-favorites/          # Folder favorites (UI + API)
│   ├── suite16-notifications/      # Notification bell + config API
│   ├── suite17-import/             # Test import — CSV/XLSX/JUnit/Allure/JSON/TestRail/TestLink/Zephyr/Xray/qTest
│   ├── suite18-requirements/       # Requirements + coverage
│   ├── suite-p1-steps/             # Structured test steps execution
│   ├── suite-p2-rbac/              # Role-based access control
│   ├── suite-p3-retest/            # Retest workflow
│   ├── suite-p4-ai-assistant/      # AI assistant panel
│   ├── suite-p6-phase06-fixes/     # Phase 6 regression suite
│   ├── suite-p7-tech-debt/         # Tech debt cleanup regression suite
│   ├── suite-p9-bug-fixes/         # Phase 9 bug fix regression suite
│   ├── suite-p10-auth-header-fix/  # Auth header regression suite
│   ├── suite-p12-audit-log/        # Audit log
│   ├── suite-p14-oauth-login/      # OAuth login (GitHub / Google)
│   ├── suite-p15-totp-2fa/         # TOTP two-factor auth
│   └── suite-p16-github-sync/      # Tests-as-Code GitHub sync (config, token redaction, sync)
│
├── .env.example
├── requirements.txt
├── Dockerfile
├── docker-compose.yml
├── docker-compose.sqlite.yml
├── Makefile
├── playwright.config.ts
└── testhub.db              # SQLite database (auto-created, gitignored)
```

---

## API overview

Base URL: `http://localhost:8000`

All endpoints except `/auth/register`, `/auth/login`, and public pages require `Authorization: Bearer <token>`.

| Area | Base path |
|---|---|
| Auth | `/api/auth/`, `/api/me`, `/api/users` |
| Tests | `/api/tests` |
| Runs | `/api/runs` |
| Folders | `/api/folders` |
| Defects | `/api/defects` |
| Projects / Categories | `/api/projects`, `/api/categories` |
| Integrations | `/api/integrations` |
| Tokens | `/api/tokens` |
| Webhooks | `/api/webhooks` |
| Attachments | `/api/attachments` |
| AI assistant | `/api/ai` |
| Admin | `/api/admin` |
| Favorites | `/api/favorites` |
| Import | `/api/import/{detect,preview,execute}` |
| Notifications | `/api/notifications`, `/api/notifications/config` |
| Audit log | `/api/audit-log` |
| OAuth | `/api/auth/oauth/{github,google}` |
| TOTP 2FA | `/api/totp` |
| Aggregated | `/api/initial-data`, `/api/insights` |
| GraphQL | `/graphql` |
| Health | `/health` — unauthenticated liveness/readiness probe (checks DB; 200 ok / 503 degraded) |

List endpoints (`/api/tests`, `/api/runs`, `/api/defects`, `/api/pipelines`, `/api/activity`) accept `limit` and `offset` query params (max 1000 rows per page) and return the total filtered row count in the `X-Total-Count` response header.

WebSocket:

- `ws://localhost:8000/ws/runs/{run_id}` — emits `state`, `step`, `complete` events during a live run.
- `ws://localhost:8000/ws/notifications?token=<jwt>` — per-user notification push channel.

---

## Tests

### Backend unit tests (576 tests)

```bash
source venv/bin/activate
python -m pytest backend/tests/ -v
```

One live integration test (`test_gitlab_e2e_integration.py`) drives the real
sync ↔ CI ↔ push loop against a running GitLab CE. It **skips** unless a GitLab is
reachable and `GITLAB_E2E_TOKEN` is set (mint one via `demo/gitlab/setup.sh`), so
the default run is unaffected.

```
backend/tests/
├── conftest.py               # Fixtures: in-memory SQLite, client, seeded state
├── test_insights.py          # /api/insights calculations
├── test_initial_data.py      # Response shape, field normalization, folder tree
├── test_run_detail.py        # Enriched run cases, 404, orphan fallback
├── test_runs_management.py   # Create run, pause/abort, status transitions
├── test_tests_crud.py        # Full CRUD, bulk actions, filters
├── test_test_detail_tabs.py  # History, defects, comments endpoints
├── test_defects.py           # Defects CRUD, filters, severity/status logic
├── test_requirements.py      # Requirements CRUD, coverage, linking, import, roles
├── test_jira_sync.py         # Jira sync, defect push, config secret redaction
├── test_steps.py             # Structured test steps CRUD
├── test_step_execution.py    # Step execution and result recording
├── test_attachments.py       # File upload/download per test and run
├── test_ai.py                # AI assistant endpoint
├── test_admin.py             # User management, role assignment
├── test_roles.py             # RBAC — access control by role
├── test_retest.py            # Retest workflow
├── test_assignment.py        # Test assignment to users
├── test_export.py            # CSV / PDF export
├── test_github_sync.py       # Tests-as-Code: YAML parse, repo sync upsert, token redaction
├── test_import_execute.py    # Import execute: external-identity matching, dedup, run linking
├── test_zephyr_import.py     # Zephyr Scale JSON parser + detection
├── test_xray_import.py       # Xray JSON parser (definitions + results) + detection
├── test_qtest_import.py      # qTest JSON parser (properties array) + detection
├── test_testlink_import.py   # TestLink XML parser + detection precedence
├── test_xlsx_import.py       # .xlsx parser (openpyxl) + detection
├── test_audit_log.py         # Audit log query, filters, admin gating
├── test_notifications.py     # Notifications list/read + per-user config
├── test_oauth.py             # OAuth login + account linking (GitHub)
├── test_oauth_google.py      # OAuth login (Google)
├── test_totp.py              # TOTP two-factor enable/verify/disable
└── test_webhooks_hmac.py     # Webhook delivery + HMAC signature
```

### E2E tests (Playwright)

```bash
make test-e2e           # all suites (requires make dev running)
make test-e2e-auth      # auth suite only
make test-report        # open HTML report
```

31 suites covering all major user flows, feature phases, and regression scenarios — including
`suite17-import` (27 tests across every supported import format).

---

## Development notes

**Adding a new view:**

1. Create `frontend/views/view-myview.jsx`, register component on `window`
2. Add `<script src="views/view-myview.js"></script>` to `frontend/index.html` (note `.js` — the build transpiles `.jsx` → `.js` into `frontend/dist/`)
3. Add a case in `frontend/app.jsx`'s hash router switch
4. Add nav item to the `NAV` array in `frontend/components/app-shell.jsx` if needed
5. Rebuild with `npm run build`, or keep `make frontend-watch` running while you edit

**Database migrations (Alembic):**

Schema is Alembic-managed. On boot the app upgrades the DB to the latest
revision automatically (pre-Alembic databases are detected and stamped at the
baseline). When you change `backend/models.py`:

```bash
make db-revision m="add foo column to tests"   # autogenerate from model diff
# review the file in migrations/versions/, then:
make db-upgrade                                # or just restart the app
```

Never edit applied revisions; add a new one. `create_all` is no longer the
source of schema truth for existing installs — revisions are.

**Adding a new API endpoint:**

1. Add route to the relevant router in `backend/routers/` (or create a new file)
2. Register the router in `backend/main.py`
3. Add Pydantic schema to `backend/schemas.py` if needed
4. Add tests in `backend/tests/`

**Database reset:**

```bash
make db-reset   # deletes testhub.db — re-seeded automatically on next make dev
```

**AI assistant:**
Defaults to Claude — set `ANTHROPIC_API_KEY` in `.env`. The endpoint is a no-op if the key is absent — no errors, no external calls.

Any OpenAI-compatible provider also works (OpenAI, Mistral, Groq, OpenRouter, or a local LLM via Ollama / LM Studio / vLLM):

```bash
# Hosted example (OpenAI)
AI_PROVIDER=openai
AI_MODEL=gpt-4o
AI_API_KEY=sk-...

# Local example (Ollama)
AI_BASE_URL=http://localhost:11434/v1
AI_MODEL=llama3.1
```

Setting `AI_BASE_URL` alone selects the OpenAI-compatible provider. Small local models (<8B) sometimes return malformed JSON — the API responds 500 in that case; prefer instruction-tuned 8B+ models.

**Theming:**
The tweaks panel (bottom-right gear icon) switches between dark/light and compact/comfortable density. Persists in `localStorage`.

## License

**ThoroTest** is source-available under the **MIT License + [Commons Clause](https://commonsclause.com/)**. See [LICENSE](LICENSE).

- **Allowed:** private and commercial use, modification, redistribution, internal/company use.
- **Not allowed:** selling the software as a product or service — including cloud/SaaS hosting or consulting/support businesses whose value derives substantially from ThoroTest.

Note: Commons Clause makes this *source-available*, not OSI open source.
