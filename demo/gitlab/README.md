# Local GitLab demo for the ThoroTest GitLab integration

Spins up a real, self-hosted **GitLab CE** + a **docker-executor runner** so you
can demo ThoroTest's GitLab integration end-to-end against a live instance:

- **Tests-as-Code sync** — pull YAML test definitions from the repo.
- **Run CI** — trigger a pipeline, wait for it, and import its `test_report`
  (pytest + Playwright jobs) as a ThoroTest run.

## Prerequisites

- Docker Desktop (allow it ~4 GB RAM; the GitLab CE image is amd64 and runs
  under emulation on Apple Silicon — first boot takes a few minutes).

## Bring it up

```bash
cd demo/gitlab
docker compose up -d      # GitLab CE + runner
./setup.sh                # waits for the API, then provisions everything
```

`setup.sh` is idempotent-ish and:

1. mints a root PAT (scope `api`),
2. creates the `thorotest-demo` project and pushes [`repo/`](repo/)
   (YAML tests under `tests/` + a `.gitlab-ci.yml` with `pytest` and
   `playwright` jobs),
3. creates an instance runner and registers it (docker executor).

It prints the values to paste into a ThoroTest GitLab integration:

```
provider : gitlab
repo_url : http://localhost:8929/root/thorotest-demo
api_base : http://localhost:8929/api/v4
branch   : main
path     : tests/
token    : glpat-…
```

- GitLab web UI: <http://localhost:8929>  (login `root` / `thorotest-demo-1234`)

## The demo pipeline

[`repo/.gitlab-ci.yml`](repo/.gitlab-ci.yml) runs two jobs, each publishing a
JUnit report (`artifacts: reports: junit:`, `when: always`):

- **pytest** — [`repo/ci_tests/`](repo/ci_tests/), all green.
- **playwright** — [`repo/e2e/`](repo/e2e/), one intentional failure.

So the pipeline goes **red** (playwright fails), yet ThoroTest still imports the
full breakdown — **5 pass / 1 fail** — because the reports publish even on
failure. Change the assertions to make it all green, or move the failure between
jobs, to reshape the demo.

## Networking note

The browser and ThoroTest reach GitLab at `http://localhost:8929`, but the
runner (and its job containers) reach it as `http://gitlab:8929` over the
compose network. `setup.sh` registers the runner with
`--clone-url http://gitlab:8929` so job git-clones resolve correctly without any
host `/etc/hosts` edits.

## Tear down

```bash
docker compose down -v    # removes containers AND volumes (full reset)
```
