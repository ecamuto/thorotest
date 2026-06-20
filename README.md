# ThoroTest

Source-available test management platform. Organize, run, and track tests across manual and automated suites — one timeline for both.

---

## Stack

| Layer | Tech |
|---|---|
| Frontend | React 18 (CDN), Babel standalone (no bundler), vanilla JS |
| Backend | FastAPI, SQLAlchemy |
| Database | SQLite (default) · PostgreSQL · MySQL / MariaDB (via `DATABASE_URL`) |
| Realtime | WebSocket (native FastAPI) |
| API | REST + GraphQL (Strawberry) |
| Auth | JWT (python-jose), passlib (sha256_crypt) |
| AI | Anthropic SDK (BYOK — optional) |
| Export | PDF (fpdf2), CSV |
| Tests | pytest, httpx, Playwright |
| Deploy | Docker + docker-compose |

No npm build step for the app. Open `http://localhost:8000` and it works.

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
| `make dev` | Start backend dev server on `http://localhost:8000` (hot-reload) |
| `make db-reset` | Delete `testhub.db` — re-seeded on next `make dev` |
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
| `ANTHROPIC_API_KEY` | _(unset)_ | Enables AI assistant (BYOK). No-op if absent |
| `GITHUB_CLIENT_ID` / `GITHUB_CLIENT_SECRET` | _(unset)_ | GitHub OAuth login (optional) |
| `GOOGLE_CLIENT_ID` / `GOOGLE_CLIENT_SECRET` | _(unset)_ | Google OAuth login (optional) |

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

---

## Tests as Code (GitHub sync)

Keep automated tests defined as YAML in a Git repo and mirror them into ThoroTest, read-only (Git is the source of truth). The test-detail page then shows the real file path, synced commit, raw YAML, and a **View on GitHub** link that points to the exact file at the synced commit.

### Setup

1. **Settings → Integrations → Add → GitHub**
2. Fill in:
   - **Repository URL** — `https://github.com/acme/web`
   - **Branch** — e.g. `main`
   - **Path** — folder holding the YAML tests, e.g. `tests/`
   - **Personal access token** — only needed for private repos (`contents: read` scope). Stored in the integration config; never returned to clients (the API reports only `token_set: true`).
3. Click **Sync** on the integration row. ThoroTest reads every `*.yml` / `*.yaml` under the path at the latest commit, then creates/updates the matching tests and caches the file contents + commit sha.

Re-syncing is idempotent: tests are matched by their YAML `id` (or, when absent, by repo + file path), so a second sync updates in place instead of duplicating.

### YAML test format

```yaml
id: TC-2301                       # stable id, reused as the test's primary key (optional)
title: "Stripe card charge succeeds on test card"
type: automated                   # automated | manual  (aliases: e2e/auto/unit → automated)
runner: playwright
status: pending                   # pass/passed → pass, etc.
priority: high                    # low | med | high | critical  (aliases: P0–P3)
owner: anna@example.com
tags: [smoke, payment]
folder: Checkout/Payment          # "/"-separated folder hierarchy, auto-created
```

Only `title` is required. Malformed files are skipped and reported in the sync result (`warnings`), not fatal.

### Endpoint

`POST /api/integrations/{id}/sync` (admin/manager) → `{ created, updated, skipped, commit, files, warnings, last_sync }`. Sync is restricted to `github.com` repos.

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
│   ├── app.jsx                 # Root App component + boot + hash routing
│   │
│   ├── components/
│   │   ├── app-shell.jsx       # Sidebar, topbar, nav structure
│   │   ├── hooks.jsx           # Shared React hooks (useInitialData)
│   │   ├── icons.jsx           # SVG icon components
│   │   ├── i18n-context.jsx    # React context for active language
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
│       ├── view-settings.jsx       # Profile, password, tokens, webhooks, integrations
│       ├── view-admin.jsx          # User and role management (admin only)
│       ├── view-import.jsx         # Bulk test import (CSV / YAML)
│       ├── view-my-work.jsx        # Personal work queue and assignments
│       ├── view-docs.jsx           # Documentation viewer
│       ├── view-config.jsx         # Config-as-code view
│       └── view-misc.jsx           # Pipelines, Insights, AI assistant
│
├── backend/
│   ├── main.py             # FastAPI app, lifespan, /api/initial-data, WebSocket
│   ├── db.py               # SQLAlchemy engine, session, Base
│   ├── models.py           # ORM models
│   ├── schemas.py          # Pydantic schemas
│   ├── seed.py             # Demo seed data (runs on first boot if DB empty)
│   ├── auth_utils.py       # JWT creation/validation, password hashing (passlib)
│   ├── ws_manager.py       # WebSocket connection manager + run simulation
│   ├── gql_schema.py       # Strawberry GraphQL schema
│   ├── github_sync.py      # Tests-as-Code: read YAML tests from a GitHub repo
│   └── routers/
│       ├── auth.py         # /auth/register, /auth/login, /me, /users
│       ├── tests.py        # CRUD /api/tests + bulk + history + comments + defects
│       ├── runs.py         # /api/runs + run detail + defects
│       ├── folders.py      # GET /api/folders (nested tree)
│       ├── defects.py      # CRUD /api/defects (filters: status, severity, test, run)
│       ├── projects.py     # CRUD /api/projects
│       ├── categories.py   # CRUD /api/categories
│       ├── integrations.py # CRUD /api/integrations + GitHub YAML sync
│       ├── tokens.py       # GET/POST/DELETE /api/tokens
│       ├── webhooks.py     # CRUD /api/webhooks + test endpoint
│       ├── attachments.py  # Upload/download file attachments per test or run
│       ├── ai.py           # AI assistant endpoint (BYOK — Anthropic)
│       ├── admin.py        # User management, role assignment (admin only)
│       ├── favorites.py    # Favorite tests per user
│       ├── import_.py      # Bulk import: CSV / YAML
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
│   └── suite-p15-totp-2fa/         # TOTP two-factor auth
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
| Import | `/api/import` |
| Notifications | `/api/notifications`, `/api/notifications/config` |
| Audit log | `/api/audit-log` |
| OAuth | `/api/auth/oauth/{github,google}` |
| TOTP 2FA | `/api/totp` |
| Aggregated | `/api/initial-data`, `/api/insights` |
| GraphQL | `/graphql` |

WebSocket:

- `ws://localhost:8000/ws/runs/{run_id}` — emits `state`, `step`, `complete` events during a live run.
- `ws://localhost:8000/ws/notifications?token=<jwt>` — per-user notification push channel.

---

## Tests

### Backend unit tests (329 tests)

```bash
source venv/bin/activate
python -m pytest backend/tests/ -v
```

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
├── test_steps.py             # Structured test steps CRUD
├── test_step_execution.py    # Step execution and result recording
├── test_attachments.py       # File upload/download per test and run
├── test_ai.py                # AI assistant endpoint
├── test_admin.py             # User management, role assignment
├── test_roles.py             # RBAC — access control by role
├── test_retest.py            # Retest workflow
├── test_assignment.py        # Test assignment to users
├── test_export.py            # CSV / PDF export
└── test_github_sync.py       # Tests-as-Code: YAML parse, repo sync upsert, token redaction
```

### E2E tests (Playwright)

```bash
make test-e2e           # all suites (requires make dev running)
make test-e2e-auth      # auth suite only
make test-report        # open HTML report
```

27 suites covering all major user flows, feature phases, and regression scenarios.

---

## Development notes

**Adding a new view:**

1. Create `frontend/views/view-myview.jsx`, register component on `window`
2. Add `<script type="text/babel" src="views/view-myview.jsx"></script>` to `frontend/index.html`
3. Add a case in `frontend/app.jsx`'s hash router switch
4. Add nav item to the `NAV` array in `frontend/components/app-shell.jsx` if needed

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
Requires an Anthropic API key. Set `ANTHROPIC_API_KEY` in `.env`. The endpoint is a no-op if the key is absent — no errors, no external calls.

**Theming:**
The tweaks panel (bottom-right gear icon) switches between dark/light and compact/comfortable density. Persists in `localStorage`.

## License

**ThoroTest** is source-available under the **MIT License + [Commons Clause](https://commonsclause.com/)**. See [LICENSE](LICENSE).

- **Allowed:** private and commercial use, modification, redistribution, internal/company use.
- **Not allowed:** selling the software as a product or service — including cloud/SaaS hosting or consulting/support businesses whose value derives substantially from ThoroTest.

Note: Commons Clause makes this *source-available*, not OSI open source.
