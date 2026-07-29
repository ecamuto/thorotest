<!--
Security fixes: please do not open a public PR for an unreported vulnerability.
See SECURITY.md and report privately first.
-->

## What this changes

<!-- The problem being solved, and the approach. The diff shows what; explain why. -->

Closes #

## How it was verified

<!--
"Tests pass" and "I ran it" are different claims — please make the second one.
Say what you actually exercised: which page, which endpoint, which command.
-->

- [ ] `make test` (backend)
- [ ] `make test-e2e` (Playwright)
- [ ] Loaded the affected screen in a browser / called the endpoint directly
- [ ] Checked it on a narrow viewport (UI changes)

## Checklist

- [ ] Behaviour changes come with tests that fail without the fix
- [ ] Schema changes ship an Alembic migration, applied against a database with data
- [ ] `npm run build` was run for any change under `frontend/`
- [ ] New user-facing strings added to **all five** locale files
- [ ] New interactive elements are keyboard-operable; dialogs use `useModal()`
- [ ] Outbound URLs built from user input pass through `assert_public_http_url`
- [ ] Docs updated (`README.md`, `docs/`, `.env.example`) if behaviour or config changed
- [ ] `CHANGELOG.md` updated for anything user-visible

## Breaking changes

<!-- Delete if none. Otherwise: what breaks, and what an operator must do on upgrade. -->

None.
