# Running tests in GitLab CI

ThoroTest can drive a project's **GitLab CI** end to end: it creates a pipeline,
waits for it to finish, reads the pipeline's **test report**, and imports the
results as a run — real pass/fail, no simulation. Works with **gitlab.com** and
**self-hosted** GitLab.

This is a **pull** model: ThoroTest reaches out to GitLab. (If you'd rather have
CI push results in, see [Alternative: push from CI](#alternative-push-from-ci).)

```
Run CI  ──create pipeline──▶  GitLab CI pipeline
   ▲                              │ runs your jobs (junit reports)
   │                              ▼
ThoroTest  ◀──poll──────────  pipeline  ──finished──▶  GET test_report
   │
   └─ parse report → import as a run (Runs & plans ▸ History)
```

Simpler than the GitHub Actions flow: creating a pipeline returns its id
immediately (no "find the dispatched run" step), and results come from the
structured `test_report` endpoint, so there's no artifact to name or download —
your jobs just have to publish JUnit reports.

## Prerequisites

- A GitLab repository whose `.gitlab-ci.yml` jobs publish JUnit reports
  (`artifacts: reports: junit:`).
- A GitLab **personal access token (PAT)** with the **`api`** scope (needed to
  create a pipeline; `read_api` is enough for read-only *sync* but not to run CI).
- A GitLab integration configured in ThoroTest with that repo + token.
- A registered **runner** for the project (gitlab.com shared runners, or your own).

## Step 1 — Prepare `.gitlab-ci.yml`

Each job that produces tests must publish a JUnit report. Use `when: always` so
results are published even when a job fails.

```yaml
stages: [test]

pytest:
  stage: test
  image: python:3.12-slim
  script:
    - pip install -r requirements.txt pytest
    - pytest --junitxml=report.xml
  artifacts:
    when: always
    reports:
      junit: report.xml

playwright:
  stage: test
  image: mcr.microsoft.com/playwright:v1.48.0-jammy
  script:
    - npm ci
    - npx playwright test --reporter=junit
  artifacts:
    when: always
    reports:
      junit: results.xml
```

Any tool that emits JUnit XML works. ThoroTest aggregates every job's report into
one run.

> **Link results to your test schede.** If you keep tests as YAML (see the main
> README's *Tests as Code*), put each scheda's `id` in the automated test's name,
> e.g. a Playwright title `login with valid credentials [TC-GL-100]`. On import,
> ThoroTest matches the `TC-…` token to the scheda — attaching the run to the same
> test row (no duplicate) and updating its status to the real result.

## Step 2 — Create a GitLab token

GitLab ▸ **User settings ▸ Access tokens** (or a project/group token):

- Scope **`api`** — required to create a pipeline (Run CI). For read-only *sync*
  of YAML tests, `read_api` suffices.

Copy the token (`glpat-…`); you'll paste it into ThoroTest.

## Step 3 — Configure the integration

In ThoroTest: **Configure ▸ Integrations ▸ Add ▸ GitLab** (or edit an existing
GitLab integration):

| Field | Value |
|---|---|
| Provider | `gitlab` — **required** for self-hosted hosts (can't be inferred) |
| Repository URL | `https://gitlab.com/your-group/your-repo` |
| API base | _(self-hosted, optional)_ e.g. `https://gitlab.internal/api/v4`; derived from the repo URL when omitted |
| Branch | the ref to run, e.g. `main` |
| Personal access token | the PAT from Step 2 |

Save. The token is stored server-side and never returned to the browser.

## Step 4 — Run it

On the integration's row, click **Run CI**. The status updates inline:

```
dispatching…  →  running…  →  collecting…  →  imported 6 tests · 1 run
```

Behind the scenes ThoroTest creates the pipeline, polls every 15 s until it
reaches a terminal state, reads its `test_report`, and imports it. The dispatch
also appears on the **Pipelines** page (running → pass/fail, with commit, branch,
and duration).

## Step 5 — See the results

- **Runs & plans ▸ History** — a new run with the real pass/fail results.
- **Library** — folders built from each test's `classname`.
- **Pipelines** — the pipeline run alongside your other CI history.
- If you tagged tests with `[TC-…]` ids, their **schede flip from `pending` to the
  real status**.

Re-running is idempotent for test definitions: tests are matched by identity and
updated in place rather than duplicated.

## Using the API (no UI)

```bash
# Trigger (provider is read from the integration config)
JOB=$(curl -sf -X POST "$THOROTEST/api/integrations/$INTEGRATION_ID/ci/run" \
  -H "Authorization: Bearer $TOKEN" -H 'Content-Type: application/json' \
  -d '{"ref":"main","run_name":"CI #42"}' | jq -r .job_id)

# Poll
curl -sf "$THOROTEST/api/integrations/$INTEGRATION_ID/ci/jobs/$JOB" \
  -H "Authorization: Bearer $TOKEN"
# → {"status":"running", ...} → {"status":"done","imported":{"tests":6,"runs":1}}
```

`ref` and `run_name` are optional overrides; without them the integration's
configured values are used.

## Troubleshooting

| Message | Likely cause |
|---|---|
| `Dispatch failed (400/404)` | no `.gitlab-ci.yml`, wrong ref, or the project can't create a pipeline |
| `gitlab auth error (401/403)` | PAT missing, expired, or lacks the `api` scope |
| `pipeline did not complete within timeout` | the pipeline took longer than 30 min (e.g. no runner available) |
| empty / partial results | a job didn't declare `artifacts: reports: junit:`, or failed before publishing (use `when: always`) |
| `cannot determine VCS provider` | self-hosted host with no explicit `provider` — set it to `gitlab` |

## Limitations

- Job tracking is in-memory: restarting the server mid-run loses the tracking
  (the GitLab pipeline itself continues).
- Results are imported once the pipeline finishes; per-test live streaming is not
  (yet) supported.

## Try it locally

A fully dockerised demo — GitLab CE + a runner + a seeded repo with YAML schede
and a `.gitlab-ci.yml` — lives in **[demo/gitlab/](../demo/gitlab/)**. Bring it up,
run `setup.sh`, and it prints the exact integration config (including a minted
token) to paste into ThoroTest.

## Alternative: push from CI

If you'd rather not give ThoroTest a token, have your CI **push** results in at
the end of its job:

```yaml
publish:
  stage: .post
  script:
    - |
      curl -sf -X POST "$THOROTEST_URL/api/import/execute" \
        -H "Authorization: Bearer $THOROTEST_TOKEN" \
        -F "file=@report.xml" -F "format=junit_xml"
```

This needs a ThoroTest API token and a reachable ThoroTest instance, but no
GitLab PAT.
