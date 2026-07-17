# Changelog

All notable changes to ThoroTest are documented here. The format follows
[Keep a Changelog](https://keepachangelog.com/en/1.1.0/); versions follow
[Semantic Versioning](https://semver.org/).

This file is the single source of truth for the in-app About page
(`GET /api/about` parses it), so keep the structure: one `## [x.y.z] - YYYY-MM-DD`
heading per release, `### <Group>` subsections, `-` bullets.

## [1.10.0] - 2026-07-17

### Security
- Require authentication on the Webhooks API (list/create/update/delete,
  regenerate-secret, test) — every route was previously unauthenticated,
  allowing anonymous callers to enumerate delivery URLs, obtain the HMAC
  signing secret, and trigger server-side requests. Now admin/manager only.
- Require authentication on Integrations create/update/delete — previously
  unauthenticated, exposing the stored git/Jira tokens to anonymous
  modification and retargeting. Now admin/manager only.
- Add an SSRF egress guard for webhook targets (`backend/net_guard.py`):
  refuse URLs that resolve to private, loopback, link-local, reserved, or
  cloud-metadata addresses; enforced at create/update, on test, and at
  delivery. Escape hatch `WEBHOOK_ALLOW_PRIVATE_HOSTS=1` for local dev/e2e.
- Harden attachment upload against path traversal: whitelist `entity_type`,
  reject traversal in `entity_id`, store only the client filename's basename,
  and assert the resolved path stays within `UPLOAD_DIR` (upload and download).

### Added
- "Demo" corner ribbon overlay when the instance runs with `DEMO_MODE=1` —
  always visible (login included), purely visual, never intercepts clicks.
  Backed by the new public `GET /api/config` bootstrap-flags endpoint.
- Demo-account logins on the login screen under `DEMO_MODE`: a "Demo accounts"
  balloon lists the seeded throwaway logins (email, password, role); clicking a
  row fills the form. `GET /api/config` returns `demo_accounts` only under
  `DEMO_MODE` (which is refused when `ENVIRONMENT=production`).

## [1.9.0] - 2026-07-16

### Added
- Custom fields on tests, defects, and requirements: admins define extra
  fields (text, number, select, date, checkbox — optionally required) from
  Admin → Custom Fields; they appear on every create/edit form, on the test
  detail page, and as chips in the defect table. Values are validated
  server-side and tracked in each record's change history.
- Defect edit dialog: title, description, severity, status, and custom
  fields — defects were previously only editable via the inline status
  dropdown.
- `thorotest` CLI v0.1 (beta, in-repo under `cli/`): `status`, `lint`, `sync`,
  `token create` — tests-as-code sync from any CI provider or fully airgapped
  installs, no Git server needed. Zero-dependency Node 18+, full reference in
  `docs/cli.md`.
- `POST /api/sync/yaml` — CLI-facing sync endpoint reusing the Git sync
  pipeline (same id/path matching, dry-run support).
- CI job running the CLI test suite (node:test).

### Fixed
- Crash ("setTest is not defined") when pushing a git-synced test back to
  its source repo from the test detail page.

## [1.8.0] - 2026-07-15

### Added
- Per-record change history: who changed what, when, on tests, runs, and defects.
- Email + in-app notifications on @mention and assignment.
- Expandable CI pipeline rows with self-healing reconcile polling.
- Free-form "Ask AI" prompt in the AI assistant.
- Select-all checkbox in the new plan/run test pickers.
- Activity feed entries link to their target entity.

### Fixed
- Pagination clamps `limit`/`offset` so a negative limit can't bypass the row cap.
- Test health insights include imported CI runs.
- Folder sync dedup is case-insensitive with stable ordering on deep trees.
- `/health` DB ping runs in a threadpool (no event-loop stall under load).
- Flaky e2e specs (webhook target, PATCH read-back race).

## [1.7.0] - 2026-07-10

### Added
- Tag filter in the test library; AI-generated drafts are tagged `ai-draft`.
- Structured AI edge-case suggestions with selectable drafts and a folder picker.
- AI edge-case assistant can be launched from the test list.
- Flaky analysis shown on any test with ≥2 runs.

### Fixed
- AI provider handling of thinking blocks and upstream API errors.
- Library toolbar wrapping; robust text-block extraction.

## [1.6.0] - 2026-07-09

### Added
- Reverse "tests as code" sync: push tests back to the repo as YAML; CI runs
  link to the originating test (schede).
- Live "Run CI" dispatches on the pipelines page with live refresh.
- Run rows open the real CI run; runs can be deleted from the list.
- Real theme toggle in the top bar.

### Changed
- Seed data no longer creates fake demo pipelines — the page shows only real runs.

## [1.5.0] - 2026-07-09

### Added
- GitLab integration: YAML test sync + CI pipeline dispatch/import, for
  gitlab.com and self-hosted.
- Local GitLab CE demo infrastructure for integration testing.

## [1.4.1] - 2026-07-08

### Fixed
- AI edge-case picker shows folder names instead of internal `F-` ids.

## [1.4.0] - 2026-07-08

### Added
- Real Test Plans: create, run, delete.
- Real manual run execution over WebSocket (live case status).
- API tokens authenticate against the REST API (CI push).
- CI ingest endpoint for pipeline runs; JUnit importer builds a folder tree
  from `classname`.
- GitHub Actions integration: trigger workflows and collect JUnit results
  ("Run CI" button + workflow/artifact config).

### Changed
- UI honesty pass: removed hardcoded fake identities, dead buttons, and
  simulated data from Insights, CI pipelines, and test detail.

## [1.3.0] - 2026-07-08

### Added
- External importers with identity-based matching and dedup: Zephyr Scale,
  Xray, qTest, TestLink, TestRail XML, Allure, real `.xlsx` spreadsheets.
- External identity columns on tests (provider + key) powering re-import dedup.

### Fixed
- Import view resets when the Import nav item is re-clicked.

## [1.2.0] - 2026-07-07

### Added
- Jira two-way integration: pull stories as requirements, push defects as
  bugs, optional periodic auto-sync, secret redaction in the UI.

## [1.1.0] - 2026-07-06

### Added
- Requirements & coverage: requirement model with epic/story hierarchy,
  test linkage, per-requirement and workspace coverage metrics, file import
  (YAML/JSON/CSV), GraphQL query.
- OpenAI-compatible provider support for the AI assistant (BYOK, any local LLM).
- Activity feed logging and test health insights endpoint.

## [1.0.0] - 2026-07-03

First production release. Highlights of the hardening pass:

### Added
- `/health` endpoint, structured logging, Docker healthchecks.
- Password reset flow with env-configured SMTP.
- Alembic migrations baseline (all schema changes via revisions).
- Uploads volume + backup/restore documentation.
- Full auth stack: JWT, RBAC, TOTP 2FA, GitHub/Google OAuth, audit log.
- Tests-as-code GitHub sync; test import; notifications.

### Changed
- Demo run simulation gated behind `DEMO_MODE` (off in production).
- Frontend built with esbuild — vendored React and fonts, zero external
  requests, airgap-ready.
- All list endpoints paginated (`limit`/`offset` + `X-Total-Count`).
