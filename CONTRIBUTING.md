# Contributing to ThoroTest

Thanks for taking the time. This document covers how to get the project running,
what the review bar is, and the handful of conventions that are not obvious from
reading the code.

**Security issues do not belong here.** See [SECURITY.md](SECURITY.md) and report
privately.

---

## Before you build something

- **Bug fixes:** open a PR directly. An issue is welcome but not required.
- **Anything larger than a bug fix:** open an issue first and describe the
  problem you are solving. This project has a deliberate scope, and a rejected
  PR after a weekend of work is a bad outcome for everyone.
- **Note the licence.** ThoroTest is MIT **plus the Commons Clause**, which means
  it is source-available, not OSI open source: you can self-host, modify, and
  redistribute it, but you cannot sell it or a service whose value derives
  substantially from it. Contributions are accepted under the same terms. If that
  does not work for you, better to know now than after writing the patch.

---

## Setting up

Requirements: **Python 3.12**, **Node 20+**, and `make`. CI pins both.

```bash
git clone https://github.com/ecamuto/thorotest.git
cd thorotest
bash install.sh     # venv, dependencies, frontend build, .env with a generated SECRET_KEY
make dev            # http://localhost:8000
```

`install.sh` generates a real `SECRET_KEY` for you. The app **refuses to start
without one** — that is intentional, not a bug (it signs sessions and encrypts
TOTP secrets).

Useful targets — `make help` lists them all:

| Command | What it does |
|---|---|
| `make dev` | Build the frontend, then run the API with reload |
| `make frontend-watch` | Rebuild the frontend on change; run beside `make dev` |
| `make test` | Backend unit tests |
| `make test-e2e` | Playwright suite (boots its own isolated server) |
| `make test-all` | The full CI gate, locally |
| `make demo` | Reset the database and load demo data |
| `make db-revision m="…"` | Autogenerate an Alembic migration |
| `make lock` | Regenerate `requirements.lock` after editing `requirements.txt` |

**Enable the pre-push hook** so you find failures before CI does:

```bash
make hooks-install    # `git push` then runs make test-all
```

---

## The bar for a change

Every PR must pass the same four CI jobs: backend pytest, Playwright e2e, CLI
tests, and a `pip-audit` dependency scan. Beyond green CI:

**Tests are not optional for behaviour changes.** A bug fix needs a test that
fails before it and passes after. A feature needs tests for the path a user
actually takes. If something is genuinely hard to test, say so in the PR and
explain why.

**Verify your change actually works, and say how.** "Tests pass" is not the same
as "I ran it." For UI work, that means loading it in a browser; for API work, a
`curl` against a running server. PRs that describe what was verified get reviewed
faster.

**Match the surrounding code.** This codebase has consistent conventions that are
not enforced by a linter — comment density, naming, how errors are surfaced. Read
the neighbours before introducing a new pattern.

**Comments explain constraints, not mechanics.** Do not narrate what the next
line does. Do write down the non-obvious reason something is the way it is — a
protocol quirk, an ordering requirement, a deliberate trade-off. The comments in
`backend/net_guard.py` and `backend/rate_limit.py` are the house style.

---

## Conventions worth knowing

### Database changes need a migration

Model edits alone are not enough — the schema is Alembic-managed:

```bash
make db-revision m="add widget table"
make db-upgrade                          # apply locally and confirm it works
```

Review the generated file before committing; autogenerate is a starting point,
not an oracle. Migrations must be safe to run against an existing database with
real data — prefer additive changes, and guard destructive ones.

### The frontend has no bundler or module system

Views are JSX files transpiled by esbuild into `frontend/dist/`, loaded as plain
`<script>` tags, and share state through `window.*` globals. It is unusual and
deliberate: zero build complexity, no CDN, fully airgappable.

Practical consequences:

- New shared helpers go on `window` in `frontend/components/hooks.jsx`, and a new
  file needs a `<script>` tag in `frontend/index.html`.
- **Run `npm run build` after editing anything under `frontend/`** — the server
  serves `dist/`, so an unbuilt change simply will not appear.
- Script order in `index.html` matters. Helpers must load before their consumers.

### Accessibility is tested, not aspirational

Interactive elements must be reachable and operable by keyboard. Use a real
`<button className="as-button">` where you can; where existing markup makes that
impractical, spread the `clickable()` helper, which supplies the role, the tab
stop, and Enter/Space activation.

Dialogs must use `useModal()` — it handles Escape, focus movement in and back
out, the focus trap, and `role="dialog"`. Do not hand-roll an overlay.
`e2e/suite20-a11y/` will fail if you do.

### i18n

User-facing strings go through `t("key")` and must be added to **all five**
locale files in `frontend/locales/` (en, it, de, es, fr). English-only additions
will be sent back.

### Security-sensitive code

Changes touching auth, tokens, uploads, outbound requests, or import parsing get
a closer read. Two rules that have already caused real bugs here:

- **Outbound URLs from user input go through `assert_public_http_url`** — at save
  time *and* at use time. A guard applied to one call site and not another is how
  the Slack-webhook SSRF happened.
- **Untrusted XML is parsed with `defusedxml`**, never `xml.etree` directly.

### Commits and PRs

Conventional Commits: `fix(security): …`, `feat(runs): …`, `docs: …`. Explain
*why* in the body, not just what — the diff already shows what. Keep PRs focused;
an unrelated drive-by refactor in the same branch slows review down.

---

## Reporting bugs

Open an issue with the version (`GET /api/about`), how you deployed it, what you
expected, what happened, and steps to reproduce. Server logs and browser console
output are usually the difference between a fix and a round of questions.
