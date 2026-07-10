# API & tests

## API overview

Base URL: `http://localhost:8000`

All endpoints except `/auth/register`, `/auth/login`, and public pages require
`Authorization: Bearer <token>`.

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

List endpoints (`/api/tests`, `/api/runs`, `/api/defects`, `/api/pipelines`, `/api/activity`)
accept `limit` and `offset` query params (max 1000 rows per page) and return the total filtered
row count in the `X-Total-Count` response header.

### WebSocket

- `ws://localhost:8000/ws/runs/{run_id}` — emits `state`, `step`, `complete` events during a live run.
- `ws://localhost:8000/ws/notifications?token=<jwt>` — per-user notification push channel.

## Tests

### Backend unit tests (576 tests)

```bash
source venv/bin/activate
python -m pytest backend/tests/ -v
```

One live integration test (`test_gitlab_e2e_integration.py`) drives the real sync ↔ CI ↔ push
loop against a running GitLab CE. It **skips** unless a GitLab is reachable and
`GITLAB_E2E_TOKEN` is set (mint one via `demo/gitlab/setup.sh`), so the default run is unaffected.

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
