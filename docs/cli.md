# ThoroTest CLI

`thorotest` is the command-line client for ThoroTest. It talks to the same REST
API as the web UI, authenticated with an API token, and is built for two jobs:

1. **CI pipelines on any provider** — push test definitions and inspect state
   from Jenkins, CircleCI, Azure DevOps, Buildkite, or a plain shell script,
   without the native GitHub Actions / GitLab CI integrations.
2. **Tests-as-code without a Git server** — sync local YAML test files straight
   from a working tree, including fully airgapped installs where the
   GitHub/GitLab repo sync can't reach anything.

**Status: beta (v0.1).** Shipped commands: `status`, `lint`, `sync`,
`token create`. Planned: `run` (trigger a run and wait for the result),
`new test` / `new run` wizards, `--filter`.

- Zero runtime dependencies. Requires **Node 18+** (uses the built-in `fetch`).
- Server requirement: ThoroTest **v1.9+** (the `POST /api/sync/yaml` endpoint).

---

## Contents

[Install](#install) · [Configuration](#configuration) · [Exit codes](#exit-codes) ·
[`status`](#thorotest-status) · [`lint`](#thorotest-lint) · [`sync`](#thorotest-sync) ·
[`token create`](#thorotest-token-create) · [YAML schema](#yaml-test-file-schema) ·
[Sync semantics](#sync-semantics) · [CI recipes](#ci-recipes) ·
[Troubleshooting](#troubleshooting) · [Limitations](#limitations)

---

## Install

The CLI lives in [`cli/`](../cli/) in the main repository and is not yet
published to npm.

```bash
# from a checkout of the thorotest repo
cd cli
npm link          # installs `thorotest` on your PATH

# or run it without installing
node cli/bin/thorotest.js --help

# in CI, straight from a checkout
alias thorotest="node $CHECKOUT/cli/bin/thorotest.js"
```

Verify:

```bash
thorotest --version   # 0.1.0
```

---

## Configuration

Every command needs the **server URL**; all except `lint` also need an **API
token**. Four sources are checked, highest priority first:

| Priority | Source | URL | Token |
|---|---|---|---|
| 1 | command-line flags | `--url https://tt.example.com` | `--token tt_…` |
| 2 | environment | `THOROTEST_URL` | `THOROTEST_TOKEN` |
| 3 | project file `./.thorotest.json` (searched upward to the git root) | `"url"` | `"token"` |
| 4 | user file `~/.config/thorotest/config.json` (respects `XDG_CONFIG_HOME`) | `"url"` | `"token"` |

Config files are plain JSON:

```json
{ "url": "https://thorotest.internal.example.com", "token": "tt_…" }
```

Recommended split: put **`url` in the project file** (commit it — it's not a
secret) and **`token` in the environment or the user file**. Never commit a
token; in CI, inject `THOROTEST_TOKEN` as a masked secret.

Getting a token: web UI → *Settings → API tokens*, or
[`thorotest token create`](#thorotest-token-create) if you already have one.
Tokens are minted by **admins** only.

---

## Exit codes

Consistent across all commands, so pipelines can branch on failure class:

| Code | Meaning |
|---|---|
| `0` | success |
| `1` | validation failure — lint errors, or the server skipped ≥1 file during sync |
| `2` | usage error — unknown command, missing argument, missing URL/token config |
| `3` | server or network error — host unreachable, HTTP 5xx, unexpected 4xx |
| `4` | authentication/authorization error — HTTP 401 (bad/expired token) or 403 (role too low) |

Global flags: `--url`, `--token`, `--json` (machine-readable output on stdout),
`-h/--help`, `-v/--version`. Human-readable diagnostics go to **stderr**;
`--json` payloads and primary results go to **stdout**. Colors are
automatically disabled when stdout is not a TTY (or with `NO_COLOR=1`).

---

## `thorotest status`

Server health, who you are, and a snapshot of tests and runs.

```
$ thorotest status
Server   https://tt.example.com  ● ok
User     enzo (admin)
Tests    412
Runs     37 total, 2 open
Last run Nightly regression [R-2091] — active, 118 passed / 3 failed of 140
```

- **open runs** = any run whose status is not `completed`.
- **last run** = most recent by `started` (falling back to `created_at`).

`--json` shape:

```json
{
  "server": { "url": "https://tt.example.com", "health": "ok" },
  "user":   { "username": "enzo", "role": "admin" },
  "tests":  { "total": 412 },
  "runs": {
    "total": 37,
    "open": 2,
    "last": { "id": "R-2091", "name": "Nightly regression", "status": "active",
              "passed": 118, "failed": 3, "blocked": 0, "total": 140,
              "started": "2026-07-15T02:00:00Z" }
  }
}
```

Gate a pipeline on the last run:

```bash
thorotest status --json | jq -e '.runs.last.failed == 0'
```

Endpoints used: `GET /health`, `GET /api/me`, `GET /api/tests?limit=1`
(count from the `X-Total-Count` header), `GET /api/runs`.

---

## `thorotest lint`

Validate YAML test files **locally — no server, no token, works offline**.
Ideal as a pre-commit hook.

```
thorotest lint <file|dir> [...] [--json]
```

Directories are walked recursively for `*.yml` / `*.yaml`
(`node_modules`, `.git`, `dist`, `venv`, `__pycache__` and dot-directories are
skipped). Exit `0` when there are no errors (warnings alone don't fail), `1`
otherwise.

```
$ thorotest lint tests/
error   tests/checkout.yaml:3: nested mappings are not supported (flat schema expected)
warning tests/login.yaml: unknown priority 'urgent' — server will import it as 'med' (valid: low, p3, med, medium, p2, normal, high, p1, critical, crit, p0, blocker)
✗ 14 files, 1 error, 1 warning
```

### Rules

The rules mirror the server-side normalizer
([`backend/importers/yaml_importer.py`](../backend/importers/yaml_importer.py))
exactly: anything the server would **reject** is an *error*; anything it would
**silently coerce to a default** is a *warning*, so typos surface before sync.

| Level | Finding |
|---|---|
| error | file is not valid YAML (within the [supported subset](#limitations)) |
| error | document is not a flat `key: value` mapping |
| error | missing or empty `title` |
| error | duplicate `id` across the linted file set (the later file would overwrite the earlier test) |
| warning | unknown `type` / `priority` / `status` value — names the default the server will use |
| warning | `status:` present at all — sync ignores it (run results own status) |
| warning | unknown key — the server ignores it |
| warning | `tags` is neither a list nor a comma-separated string |
| warning | no `id` — the server generates one, but a stable id keeps re-syncs idempotent if the file moves |

`--json` shape:

```json
{
  "files": 14,
  "errors":   [{ "path": "tests/checkout.yaml", "line": 3, "message": "nested mappings are not supported (flat schema expected)" }],
  "warnings": [{ "path": "tests/login.yaml", "line": null, "message": "unknown priority 'urgent' — …" }],
  "ok": false
}
```

Pre-commit hook (`.git/hooks/pre-commit`):

```bash
#!/bin/sh
exec thorotest lint tests/
```

---

## `thorotest sync`

Push local YAML test definitions to the server. The CLI equivalent of the
GitHub/GitLab repo sync — same parser, same upsert rules, same guarantees.

```
thorotest sync <file|dir> [...] [--dry-run] [--ref <label>] [--source <cli://...>] [--force] [--json]
```

```
$ thorotest sync tests/ --ref "$(git rev-parse --short HEAD)"
synced  14 files: 2 created, 12 updated, 0 skipped
```

| Flag | Effect |
|---|---|
| `--dry-run` | full server-side validation and matching, reports what *would* change, persists nothing |
| `--ref <label>` | recorded as each test's `source_ref` (pass a git SHA or tag for traceability); default `cli` |
| `--source <src>` | source identity recorded as `repo_url`; must start with `cli://`; default `cli://local` — see [Sync semantics](#sync-semantics) |
| `--force` | push even when local lint finds errors; the server skips invalid files and reports them as warnings |

Behaviour:

1. Collect `*.yml`/`*.yaml` under the given paths. File paths are sent
   **relative to the current directory** (posix-style) and become each test's
   `source_path` — run sync from the same directory every time (repo root in
   CI) so paths stay stable.
2. Lint locally first. Any error aborts before contacting the server
   (exit `1`) unless `--force`.
3. `POST /api/sync/yaml` with all files in one request.
   Server limits: ≤500 files per push, ≤256 KB per file.
4. Print the server's stats. Exit `1` if the server skipped any file, else `0`.

`--json` emits the server response verbatim:

```json
{ "created": 2, "updated": 12, "skipped": 0, "commit": "9f3ab12",
  "files": 14, "warnings": [], "dry_run": false }
```

Requires role **tester, manager, or admin** (viewers get exit 4).

---

## `thorotest token create`

Mint a long-lived API token — for handing to CI or rotating credentials.
**Admin only** (same rule as the web UI).

```
$ thorotest token create --name ci-nightly [--scope <scope>]
✓ token 'ci-nightly' created (id 7)
tt_3f9a1c…
This token is shown once — store it now (e.g. as a CI secret).
```

The token value is printed to **stdout** (pipe-friendly); the reminder goes to
stderr. `--json` returns `{ "id": 7, "name": "ci-nightly", "scope": "", "token": "tt_…" }`.

Bootstrap note: creating a token requires an existing credential. Mint the
first one in the web UI (*Settings → API tokens*); use the CLI for rotation
and automation after that. Revoke tokens in the web UI.

---

## YAML test file schema

One test per file. Flat mapping; only `title` is required.

```yaml
id: TC-2301                       # stable id; becomes the Test primary key
title: "Stripe card charge succeeds on test card"
type: automated                   # automated | manual
runner: playwright
priority: high                    # low | med | high | critical
owner: anna.ricci@example.com
tags: [smoke, payment]            # or a comma-separated string, or a block list
folder: Checkout/Payment          # "/"-separated folder hierarchy, created on sync
```

### Fields and accepted aliases

| Key | Required | Canonical values | Accepted aliases (case-insensitive) | Default when missing/unknown |
|---|---|---|---|---|
| `title` | **yes** | any non-empty string | — | *(error)* |
| `id` | no | any string | — | server generates `TC-XXXXXX` |
| `type` | no | `automated`, `manual` | `auto`, `e2e`, `integration`, `unit` → `automated` | `manual` |
| `runner` | no | any string (e.g. `playwright`, `pytest`) | — | empty |
| `priority` | no | `low`, `med`, `high`, `critical` | `p3`→low · `medium`, `p2`, `normal`→med · `p1`→high · `crit`, `p0`, `blocker`→critical | `med` |
| `owner` | no | any string | — | empty (existing owner kept on update) |
| `tags` | no | list of strings | comma-separated string is split | `[]` |
| `folder` | no | `/`-separated path | — | root |
| `status` | — | **ignored by sync** | `passed`/`ok`/`green`→pass etc. — parsed but never applied | — |

`status` is deliberately never taken from the file: a test's status is owned by
real run results, so a hand-written `status:` can't lie about it. Lint warns
whenever the key is present.

---

## Sync semantics

Sync is an **idempotent upsert**, identical to the Git repo sync
(`backend/github_sync.py::sync_repo`):

1. **Match by `id`** — if a test with the YAML `id` exists, it's updated.
2. **Else match by `(source, path)`** — the pair (`--source` value, file path)
   identifies the test. Re-pushing the same tree updates rather than duplicates,
   even for files without an `id`.
3. **Else create**, with the YAML `id` or a generated one.

Consequences worth knowing:

- **Renaming a file without an `id` creates a new test** (the old row keeps the
  old path). Give tests stable `id`s to survive file moves.
- **`--source` namespaces path-matching.** Two different suites pushed from
  different repos should use distinct sources (e.g. `cli://payments-repo`,
  `cli://web-repo`) so files that happen to share paths don't collide.
- **Sync overwrites a test's source pointer.** If a test with the same `id` is
  also synced from GitHub/GitLab, the last sync (Git or CLI) wins ownership of
  `repo_url`/`source_path`. Pick one channel per test suite.
- **Deletions don't propagate.** Removing a local file never deletes the server
  test. Delete tests in the UI (or via the REST API).
- `--dry-run` runs the exact same code path inside a transaction that is rolled
  back — its `created`/`updated`/`skipped` counts are what a real push would do.

---

## CI recipes

The point of the CLI: ThoroTest sync from **any** CI provider. Set two secrets
(`THOROTEST_URL`, `THOROTEST_TOKEN`) and add one step.

### Jenkins (declarative)

```groovy
stage('Sync tests to ThoroTest') {
  environment {
    THOROTEST_URL   = credentials('thorotest-url')
    THOROTEST_TOKEN = credentials('thorotest-token')
  }
  steps {
    sh 'node cli/bin/thorotest.js lint tests/'
    sh 'node cli/bin/thorotest.js sync tests/ --ref "$GIT_COMMIT"'
  }
}
```

### CircleCI

```yaml
- run:
    name: Sync tests to ThoroTest
    command: |
      node cli/bin/thorotest.js lint tests/
      node cli/bin/thorotest.js sync tests/ --ref "$CIRCLE_SHA1"
```

### Azure DevOps

```yaml
- script: |
    node cli/bin/thorotest.js lint tests/
    node cli/bin/thorotest.js sync tests/ --ref "$(Build.SourceVersion)"
  env:
    THOROTEST_URL: $(ThorotestUrl)
    THOROTEST_TOKEN: $(ThorotestToken)
  displayName: Sync tests to ThoroTest
```

### Plain shell / cron (airgapped)

```bash
#!/usr/bin/env bash
set -euo pipefail
export THOROTEST_URL=http://thorotest.lan:8000
export THOROTEST_TOKEN="$(cat /etc/thorotest/token)"

thorotest sync /srv/test-definitions --ref "manual-$(date +%F)"
thorotest status --json | jq -e '.runs.last.failed == 0'   # non-zero exit fails the job
```

Validate PRs without touching the server — `--dry-run` still catches duplicate
ids, bad enum values, and shows what would change:

```bash
thorotest sync tests/ --dry-run
```

On GitHub Actions / GitLab CI you can use either the CLI or the built-in
integrations ([github-actions-ci.md](github-actions-ci.md),
[gitlab-ci.md](gitlab-ci.md)); the integrations additionally support pipeline
dispatch and JUnit result import, which the CLI will gain with `thorotest run`.

---

## Troubleshooting

| Symptom | Cause / fix |
|---|---|
| `no server URL configured` (exit 2) | Set `--url`, `THOROTEST_URL`, or a config file. See [Configuration](#configuration). |
| `no API token configured` (exit 2) | Set `--token` / `THOROTEST_TOKEN`. `lint` is the only command that works without one. |
| `Not authenticated` (exit 4) | Token revoked, expired, or mistyped. Mint a new one. |
| `Your role does not allow this operation` (exit 4) | `sync` needs tester+; `token create` needs admin. |
| `cannot reach …` (exit 3) | Wrong URL/port, server down, or a proxy in the way. `curl $THOROTEST_URL/health` to isolate. |
| `404` on sync (exit 3) | Server older than v1.9 — `POST /api/sync/yaml` doesn't exist yet. Upgrade the server. |
| Sync created duplicates | Files were renamed and have no `id`, or `--source` changed between pushes. Add stable `id`s. |
| `block scalars (| / >) are not supported by local lint` | The file uses YAML the local linter doesn't parse — validate it server-side with `thorotest sync --dry-run`, or simplify the file. |
| Colored output garbling logs | Colors auto-disable off-TTY; force with `NO_COLOR=1`. |

---

## Limitations

- **Local YAML subset.** `lint` parses the documented flat schema: scalars,
  quoted strings, comments, inline `[a, b]` and block `- item` lists. It
  rejects nested mappings, block scalars (`|`/`>`), anchors/aliases, and
  multi-document files — *deliberately*, since none are meaningful in a test
  definition. The server (PyYAML) accepts full YAML; `sync --dry-run` is the
  authoritative validator. Stricter-than-server is safe: lint can false-fail an
  exotic-but-valid file, never false-pass a broken one — except duplicate keys,
  which PyYAML silently resolves last-wins while lint correctly flags them.
- **No local execution.** `thorotest run` (trigger + wait) is the next planned
  command; today, runs are driven from the UI or the REST/GraphQL API.
- **No pagination in `status`.** Run stats read up to the server's page cap
  (1000 runs); totals come from `X-Total-Count` and stay exact.
- **Not yet on npm.** Install from the repo (`npm link`); publishing is planned
  once `run` lands.

## Testing

- CLI: `cd cli && npm test` (node:test, no dependencies — includes a mock
  ThoroTest server exercising every command and exit code).
- Server endpoint: `pytest backend/tests/test_cli_sync.py`.
