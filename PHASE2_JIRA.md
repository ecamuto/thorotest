# Phase 2 — Jira integration (v1.2.0)

Branch: `feat/jira-integration`
Goal: two-way link between ThoroTest and Jira Cloud, reusing the `external_*` fields
shipped in v1.1 on both Requirement and Defect. No schema change needed.

Two flows, one `jira` integration config:
1. **Pull** Jira stories/epics → requirements (inbound; Jira is source of truth for these)
2. **Push** ThoroTest defects → Jira bugs (outbound; ThoroTest creates, Jira tracks)

## 1. Integration config (`type = "jira"`)

`config = { base_url, email, api_token, project_key, issue_type_bug, issue_type_story }`

- Auth: HTTP Basic `email:api_token` (Jira Cloud REST v3).
- `api_token` redaction reuses the existing merge-safe path in `integrations.py`
  (`token_set` pattern) — rename-agnostic; store under `api_token`, never return it.

## 2. `backend/jira_sync.py` (templated on `github_sync.py`)

`JiraClient(base_url, email, api_token)`:
- `_request()` wrapper with clear RuntimeError messages per status (401/403/404/rate-limit)
- `create_issue(project_key, issue_type, summary, description) -> {key, url}`
  (`POST /rest/api/3/issue`; description as ADF or plain text)
- `get_issue(key) -> {status, summary, type}` (`GET /rest/api/3/issue/{key}`)
- `search_issues(jql) -> [issues]` (`GET /rest/api/3/search`, paginated)

`sync_jira_requirements(db, integration) -> stats`:
- JQL: `project = {key} AND issuetype in (Story, Epic)`
- Upsert requirements matched by `external_key`; map Jira status → requirement status,
  issuetype → type (epic/story/feature). Preserve local test links.

`push_defect_to_jira(db, integration, defect) -> defect`:
- Create bug issue from defect (title→summary, description, severity→priority map)
- Store `external_provider="jira"`, `external_key`, `external_url` on the defect.

## 3. Router wiring

- `integrations.py` sync endpoint: branch on `integration.type` — `github` →
  `github_sync.sync_integration`, `jira` → `jira_sync.sync_jira_requirements`.
- `defects.py`: `POST /api/defects/{id}/push` (admin/manager) — pick the jira
  integration, call `push_defect_to_jira`, return updated defect. 409 if already pushed.

## 4. Schemas

- `DefectOut` gains `external_provider/key/url` (already columns; add to schema + initial-data).
- Requirement already exposes external fields.

## 5. Frontend

- **Settings → Integrations**: Jira add/edit form (base_url, email, api_token,
  project_key, issue types). Sync button already generic.
- **Defects view + test-detail Defects tab**: "Push to Jira" action per defect; show
  `external_key` as a link once pushed.
- **Requirements view**: already renders `external_key` link — verify Jira-sourced ones.
- api.js: `pushDefectToJira(id)`.

## 6. Tests

- pytest `test_jira_sync.py`: mock httpx — client request/error mapping, requirement
  upsert by external_key + status mapping, defect push stores external fields + 409 on
  re-push, config validation. No real network.
- e2e: Jira integration form renders + validation (no live Jira; API mocked or skipped).

## 7. Docs + version

- README Jira section (setup, JQL, field mapping, security note on api_token storage).
- In-app docs integrations note.
- PRODUCTION_ROADMAP: mark 1.2 done.
- Bump `package.json` 1.1.0 → 1.2.0.

## Commit sequence

1. jira_sync.py + DefectOut external fields + initial-data
2. router wiring (sync branch + defect push) + schemas
3. frontend (integration form + push action + api.js)
4. pytest + e2e
5. docs + version bump

## Security notes

- `api_token` is a secret — stored in integration config, never returned to clients
  (only `token_set: true`), same as the GitHub PAT.
- Outbound push publishes defect title/description to Jira — confirm the target
  integration before first push; the push endpoint is admin/manager only.
- Restrict `base_url` to https; validate it's a well-formed Atlassian host.
