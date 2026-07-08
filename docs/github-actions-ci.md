# Running tests in GitHub Actions

ThoroTest can drive a project's **GitHub Actions** CI end to end: it triggers a
workflow, waits for it to finish, downloads the run's JUnit artifact, and imports
the results as a run — real pass/fail, no simulation.

This is a **pull** model: ThoroTest reaches out to GitHub. (If you'd rather have
CI push results in, see [Alternative: push from CI](#alternative-push-from-ci).)

```
Run CI  ──dispatch──▶  GitHub Actions workflow
   ▲                        │ runs your tests, uploads junit artifact
   │                        ▼
ThoroTest  ◀──poll──────  workflow run  ──completed──▶  download artifact
   │
   └─ parse JUnit → import as a run (Runs & plans ▸ History)
```

## Prerequisites

- A GitHub repository whose workflow:
  1. is triggerable on demand (`workflow_dispatch`), **and**
  2. uploads a JUnit XML artifact.
- A GitHub **personal access token (PAT)** with Actions access (see
  [Step 2](#step-2-create-a-github-token)).
- A GitHub integration configured in ThoroTest with that repo + token.

## Step 1 — Prepare the workflow

The workflow must declare `workflow_dispatch` and upload a JUnit artifact.

> **GitHub quirk:** `workflow_dispatch` only works once the workflow file (with
> that trigger) exists on the repository's **default branch**. Merge it to
> `main` first, or the dispatch returns 404.

### Python / pytest

```yaml
name: CI
on:
  workflow_dispatch:        # required — lets ThoroTest trigger it via the API
  push:

jobs:
  test:
    runs-on: ubuntu-latest
    steps:
      - uses: actions/checkout@v4
      - uses: actions/setup-python@v5
        with:
          python-version: '3.12'
      - run: pip install -r requirements.txt pytest
      - name: Run tests → JUnit XML
        run: pytest --junitxml=junit.xml
        continue-on-error: true          # still upload results when tests fail
      - name: Upload JUnit artifact
        if: ${{ !cancelled() }}
        uses: actions/upload-artifact@v4
        with:
          name: junit                     # must match the integration's artifact name
          path: junit.xml
```

### Node / Playwright

```yaml
      - name: Run Playwright → JUnit XML
        run: npx playwright test --reporter=junit
        env:
          PLAYWRIGHT_JUNIT_OUTPUT_NAME: junit.xml
        continue-on-error: true
      - name: Upload JUnit artifact
        if: ${{ !cancelled() }}
        uses: actions/upload-artifact@v4
        with:
          name: junit
          path: junit.xml
```

Any tool that emits JUnit XML works (Jest `jest-junit`, Go `gotestsum --junitfile`,
etc.). If the artifact contains multiple `*.xml` files, ThoroTest merges them.

## Step 2 — Create a GitHub token

GitHub ▸ **Settings ▸ Developer settings ▸ Personal access tokens**:

- **Classic token** — scope **`repo`** (this grants Actions read/write for that
  repo). Simplest option.
- **Fine-grained token** — on the target repo grant **Actions: Read and write**
  and **Contents: Read**.

Copy the token (`ghp_…` or `github_pat_…`); you'll paste it into ThoroTest.

## Step 3 — Configure the integration

In ThoroTest: **Configure ▸ Integrations ▸ Add ▸ GitHub** (or edit an existing
GitHub integration):

| Field | Value |
|---|---|
| Repository URL | `https://github.com/your-org/your-repo` |
| Branch | the ref to dispatch, e.g. `main` |
| Personal access token | the PAT from Step 2 |
| Workflow | the workflow file name, e.g. `ci.yml` |
| JUnit artifact | the artifact name from `upload-artifact`, e.g. `junit` |

Save. The token is stored server-side and never returned to the browser.

## Step 4 — Run it

On the integration's row, click **Run CI**. The status updates inline:

```
dispatching…  →  finding run…  →  running…  →  collecting…  →  imported 42 tests · 1 run
```

Behind the scenes ThoroTest dispatches the workflow, finds the run it created,
polls every 15 s until it completes, downloads the JUnit artifact, and imports it.

## Step 5 — See the results

- **Runs & plans ▸ History** — a new run with the real pass/fail results.
- **Library** — folders built from each test's `classname`.

Re-running is idempotent for test definitions: tests are matched by identity and
updated in place rather than duplicated.

## Using the API (no UI)

The same flow is available over HTTP, e.g. from your own automation. Authenticate
with an [API token](#) (`Authorization: Bearer th_…`) or a session JWT.

```bash
# Trigger
JOB=$(curl -sf -X POST "$THOROTEST/api/integrations/$INTEGRATION_ID/ci/run" \
  -H "Authorization: Bearer $TOKEN" -H 'Content-Type: application/json' \
  -d '{"workflow":"ci.yml","ref":"main","run_name":"CI #42"}' | jq -r .job_id)

# Poll
curl -sf "$THOROTEST/api/integrations/$INTEGRATION_ID/ci/jobs/$JOB" \
  -H "Authorization: Bearer $TOKEN"
# → {"status":"running", ...} → {"status":"done","imported":{"tests":42,"runs":1}}
```

`workflow`, `ref`, `artifact`, and `run_name` are optional overrides; without
them the integration's configured values are used.

## Troubleshooting

| Message | Likely cause |
|---|---|
| `Dispatch failed (404)` | workflow not on the default branch, wrong workflow file name, or token can't see the repo |
| `Dispatch failed (401/403)` | PAT missing or lacks Actions permission |
| `dispatched run not found` | wrong `ref`/branch, or the workflow didn't start |
| `run did not complete within timeout` | the run took longer than 30 min |
| `run produced no artifacts` | the workflow didn't upload an artifact, or the name doesn't match |

## Limitations

- Job tracking is in-memory: restarting the server mid-run loses the tracking
  (the GitHub run itself continues).
- The collector imports the JUnit artifact once the run completes; per-test live
  streaming is not (yet) supported.
- `workflow_dispatch` requires the workflow to exist on the default branch.

## Alternative: push from CI

If you'd rather not give ThoroTest a token, have your CI **push** results in at
the end of its job:

```yaml
      - name: Publish results to ThoroTest
        if: ${{ !cancelled() }}
        run: |
          curl -sf -X POST "$THOROTEST_URL/api/import/execute" \
            -H "Authorization: Bearer $THOROTEST_TOKEN" \
            -F "file=@junit.xml" -F "format=junit_xml"
        env:
          THOROTEST_URL: ${{ secrets.THOROTEST_URL }}
          THOROTEST_TOKEN: ${{ secrets.THOROTEST_TOKEN }}   # a ThoroTest API token
```

This needs a ThoroTest [API token](#) and a reachable ThoroTest instance, but no
GitHub PAT and no `workflow_dispatch`.
