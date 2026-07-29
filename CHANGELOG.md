# Changelog

All notable changes to ThoroTest are documented here. The format follows
[Keep a Changelog](https://keepachangelog.com/en/1.1.0/); versions follow
[Semantic Versioning](https://semver.org/).

This file is the single source of truth for the in-app About page
(`GET /api/about` parses it), so keep the structure: one `## [x.y.z] - YYYY-MM-DD`
heading per release, `### <Group>` subsections, `-` bullets.

## [1.13.0] - 2026-07-29

### Added
- Keyboard and assistive-technology support for dialogs and dropdowns. All 15
  modals now expose `role="dialog"` with `aria-modal`, move focus into the
  dialog on open and back to the trigger on close, trap Tab inside, and close
  on Escape. Filter and export dropdowns close on Escape; their click-catching
  backdrops are marked `aria-hidden` and stay out of the tab order.
- `useModal()` and `useDismissable()` in `frontend/components/hooks.jsx`, so
  dialogs stop being hand-rolled per view. `useModal` also fixes a
  long-standing annoyance: selecting text inside a dialog and releasing the
  mouse over the backdrop no longer closes it.
- E2E suite `suite20-a11y` (9 tests) covering dialog semantics, focus movement
  and restoration, the focus trap, Escape dismissal, and skip-link behaviour —
  none of which is visible in a screenshot, so it is easy to regress silently.
- `SECURITY.md` (private reporting, scope, response targets, and the known
  limitations of the current design), `CONTRIBUTING.md`, `CODE_OF_CONDUCT.md`,
  issue forms, and a pull-request template.

## [1.12.0] - 2026-07-28

Pre-launch security and accessibility pass. Two changes are breaking for
existing deployments — see **Breaking** below before upgrading.

### Breaking
- `SECRET_KEY` is now required and validated in every environment (previously
  only under `ENVIRONMENT=production`). The app refuses to start when it is
  missing, under 32 characters, or still the placeholder that shipped in
  `.env.example`. Generate one with
  `python3 -c "import secrets; print(secrets.token_hex(32))"`. For a throwaway
  local run only, `ALLOW_INSECURE_SECRET_KEY=1` skips the check.
- Self-registration is off by default. `POST /api/auth/register` returns 403
  and OAuth signs in existing users without provisioning new ones. Set
  `ALLOW_OPEN_REGISTRATION=1` to restore the old behaviour; self-registered
  accounts now get the read-only `viewer` role instead of `tester`.
- `docker-compose.yml` requires `POSTGRES_PASSWORD` (the weak `thorotest`
  fallback is gone) and sets `ENVIRONMENT=production`.

### Security
- Close open self-registration, which granted anyone who could reach an
  instance a write-capable account with full read access to the workspace.
- Require a session token on `ws/runs/{run_id}`, which was unauthenticated and
  streamed live run state to anyone who guessed a run ID; also apply the
  `token_version` revocation check to `ws/notifications`, which decoded the JWT
  but skipped it. Token decoding for REST, WebSocket, and GraphQL now shares
  one implementation so the three cannot drift apart.
- Enforce API token `scope`: a `read` token is now restricted to safe HTTP
  methods instead of silently carrying its owner's full write access. Tokens
  also expire (`API_TOKEN_EXPIRE_DAYS`, 90 by default) and are revoked when
  their owner logs out everywhere or resets their password. Any role can mint
  tokens for itself, so a CI credential no longer has to be an admin token.
- Remove per-user SMTP settings, which let any authenticated user point the
  server at an arbitrary host:port and stored a relay password in plaintext
  that `GET /api/notifications/config` echoed back. Notification email now goes
  through the operator-configured relay (`SMTP_HOST`). Existing stored
  credentials are cleared by migration `b9e4d7c15a83`.
- Apply the SSRF egress guard to per-user Slack webhook URLs, which bypassed
  the check added for outbound webhooks in 1.11.0.
- Parse imported XML with `defusedxml`: a ~1 KB entity-expansion document
  inside the 10 MB upload limit could exhaust server memory. Artifact zips are
  now bounded per member and in total.
- Fix an uncaught 500 in OAuth account linking for provider-only accounts,
  which permanently blocked linking a second provider, and throttle the
  confirm-link endpoint, which accepted unlimited password guesses.
- Bound the login, AI, and 2FA rate-limit stores. Keys were pruned but never
  removed, so rotating IP or email grew them without limit.
- Run the container as a non-root user, build it from `requirements.lock`, and
  add a `.dockerignore` so `.env` and local databases stay out of the build
  context.

### Added
- Responsive layout: below 900px the sidebar becomes an off-canvas drawer with
  a toggle, multi-column dashboards stack, and wide tables scroll in their own
  container rather than the page.
- Keyboard and screen-reader support: a skip link, visible focus rings,
  `prefers-reduced-motion` handling, and button semantics (focusable,
  Enter/Space activation, `role="button"`) on interactive rows, chips, and cards.

### Fixed
- README described password hashing as `sha256_crypt`; it has been argon2id
  since 1.10.0.

## [1.11.0] - 2026-07-19

### Security
- Neutralize CSV formula injection in run and test-library exports: cells
  starting with `= + - @` (or tab/CR) are prefixed with an apostrophe so
  spreadsheets don't execute them.
- Raise the password policy to 12–128 characters with a common-password
  blocklist and rejection of passwords containing the account's own
  username or email; enforced on register, password change, password reset,
  and admin user creation. Existing passwords are unaffected.
- Fresh installs no longer seed the fixed `admin@localhost / admin`
  credential: the first-boot admin password is `ADMIN_INITIAL_PASSWORD` if
  set, the demo default only under `DEMO_MODE`, otherwise a random secret
  printed once in the server log.
- Attachment uploads are restricted to an allow-list of test-evidence file
  types (extensible via `UPLOAD_EXTRA_EXTENSIONS`); `.html`/`.svg` are
  excluded because they render as active markup. Downloads force
  `application/octet-stream` for renderable MIME types and send
  `X-Content-Type-Options: nosniff`.
- All responses now carry a same-origin Content-Security-Policy,
  `X-Content-Type-Options: nosniff`, and `Referrer-Policy: same-origin`.

### Changed
- PostgreSQL is now the documented production database; SQLite remains the
  out-of-the-box default for evaluation and small installs, with a boot-time
  warning when `ENVIRONMENT=production` runs on SQLite. docker-compose reads
  `POSTGRES_PASSWORD` from the environment instead of hardcoding it.
- Faster dashboards at scale: indexes on the hot `run_cases`, `tests`, and
  `defects` filter columns (Alembic `a7c3e9f14b02`), and the requirement
  coverage block in `/api/initial-data` now runs as a single query instead
  of one per requirement.

### Added
- `make clean-data` (remove local databases and test artifacts) and
  `make lock` (regenerate the pinned `requirements.lock`).
- Supply-chain hygiene: CI installs from `requirements.lock`, a pip-audit
  CVE scan job, and grouped monthly Dependabot updates.
- README test-count badges are derived from the tree
  (`scripts/update-badges.py`) and drift now fails CI.

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
