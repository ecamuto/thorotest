# Architecture & development

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
├── e2e/                    # Playwright suites (see docs/api.md#tests)
├── .env.example
├── requirements.txt
├── Dockerfile
├── docker-compose.yml
├── docker-compose.sqlite.yml
├── Makefile
├── playwright.config.ts
└── testhub.db              # SQLite database (auto-created, gitignored)
```

## Development notes

**Adding a new view:**

1. Create `frontend/views/view-myview.jsx`, register component on `window`
2. Add `<script src="views/view-myview.js"></script>` to `frontend/index.html` (note `.js` — the build transpiles `.jsx` → `.js` into `frontend/dist/`)
3. Add a case in `frontend/app.jsx`'s hash router switch
4. Add nav item to the `NAV` array in `frontend/components/app-shell.jsx` if needed
5. Rebuild with `npm run build`, or keep `make frontend-watch` running while you edit

**Database migrations (Alembic):**

Schema is Alembic-managed. On boot the app upgrades the DB to the latest revision automatically
(pre-Alembic databases are detected and stamped at the baseline). When you change
`backend/models.py`:

```bash
make db-revision m="add foo column to tests"   # autogenerate from model diff
# review the file in migrations/versions/, then:
make db-upgrade                                # or just restart the app
```

Never edit applied revisions; add a new one. `create_all` is no longer the source of schema
truth for existing installs — revisions are.

**Adding a new API endpoint:**

1. Add route to the relevant router in `backend/routers/` (or create a new file)
2. Register the router in `backend/main.py`
3. Add Pydantic schema to `backend/schemas.py` if needed
4. Add tests in `backend/tests/`

**Database reset:**

```bash
make db-reset   # deletes testhub.db — re-seeded automatically on next make dev
```
