# ThoroTest — Performance & Scalability Report

> **v1.14 Phase 1 measured addendum — 2026-10-24.** The original v1.9
> assessment below is retained as historical evidence. The single-process
> state findings P-4 are now remediated by Redis-backed quotas/Pub/Sub and
> durable database jobs. A local Docker Desktop arm64 benchmark used the
> production Python 3.12 image, PostgreSQL 16, Redis 7, the standard demo
> dataset (19 test cases, 11 runs, 9 defects), and five-second levels from
> `scripts/loadtest.py`. Every request completed successfully.
>
> | Mix / concurrency | 1 worker (rps / p95) | 2 workers (rps / p95) | Throughput change |
> |---|---:|---:|---:|
> | `/tests`, 4 | 248 / 18.4 ms | 444 / 10.7 ms | +79% |
> | `/tests`, 16 | 234 / 105.1 ms | 417 / 52.9 ms | +78% |
> | mixed reads, 4 | 432 / 18.9 ms | 740 / 10.0 ms | +71% |
> | mixed reads, 16 | 420 / 74.4 ms | 667 / 46.4 ms | +59% |
> | `/initial-data`, 4 | 230 / 24.7 ms | 397 / 11.4 ms | +73% |
> | `/initial-data`, 16 | 198 / 113.1 ms | 385 / 60.9 ms | +94% |
>
> At mixed-read concurrency 32 the second worker was already near local-host
> saturation (421 vs 403 rps, p95 225.9 vs 157.8 ms), so these figures are a
> regression baseline rather than a capacity promise. A Redis failure drill
> kept `/health` at 200, changed `/ready` to 503 with no database failure, and
> recovered `/ready` to 200 with the Pub/Sub subscriber active after restart.

**Audit date:** 2026-07-16 · **Version:** 1.9.0

Scope: algorithmic hotspots, DB access patterns, concurrency model, frontend delivery, and horizontal-scaling readiness. No load test was executed as part of this review (a `scripts/loadtest.py` exists in-repo and should be run to confirm the estimates below).

---

## Executive read

ThoroTest is a **single-process, mostly-synchronous FastAPI app** that will comfortably serve a single team (tens of concurrent users, low-thousands of tests). It has been thoughtfully written to *aggregate in SQL* on the hot dashboard paths, which avoids the most common naive mistakes. The ceiling is **architectural, not algorithmic**: several correctness-critical features keep state in process memory (WebSocket connections, login throttle, AI rate limit, CI dispatch job registry), so the app **cannot be safely scaled to multiple workers/replicas as-is**. SQLite is the default and is single-writer.

---

## Strengths (verified in source)

- **Dashboard aggregates in SQL, not Python.** `GET /api/insights` and `/api/insights/test-health` use `func.count`, `GROUP BY`, and `IN (...)` batches rather than loading whole tables (`main.py:308-431`). The comment "this endpoint must not load whole tables into memory" reflects real discipline.
- **Blocking work is offloaded.** The `/health` DB ping and Jira auto-sync run via `asyncio.to_thread` / `run_in_background` so a slow DB or Jira call doesn't stall the event loop (`main.py:255-262`, `:186`).
- **AI N+1 avoided.** `suggest-edge-cases` and `analyze-flaky` use `joinedload` to pull steps/step-results in one query (`ai.py:246`, `:275`).
- **Payload caps.** `/api/initial-data` caps each collection (`INITIAL_DATA_CAPS`, `main.py:438`) and returns real `totals` so the UI knows when it's seeing a capped slice.
- **SQLite tuned.** WAL journal + 5s busy timeout pragmas on connect (`main.py:29-35`); `pool_pre_ping` on server DBs (`db.py:12`).
- **Pagination is guarded.** `_pagination.py` clamps limit/offset (a prior commit fixed negative-limit bypass), and list endpoints emit `X-Total-Count`.

---

## Bottlenecks & risks

### P-1 — `/api/initial-data` is a fan-out mega-endpoint (Medium)
`main.py:442-552` issues ~15 queries and serializes up to 1000 tests + 500 runs + 500 defects + 500 requirements on **every app load**. For the requirements block it also computes coverage in Python by walking `r.tests` per requirement (`main.py:513-527`) — an **N+1** (one lazy-load per requirement, up to 500). At the documented seed scale it's fine; at thousands of requirements this becomes the slowest authenticated call in the app.
**Fix:** compute requirement coverage with a single `GROUP BY` join (as `/insights` already does for folders); consider splitting initial-data into lazily-loaded per-view fetches. **Est. improvement:** 5–20× on that endpoint at scale.

### P-2 — `/api/insights/test-health` loads all runs in the window (Low/Medium)
`main.py:403-407` pulls full `Run` rows for the last N days then buckets in Python. Runs are low-cardinality so this is cheap now, but it scales with run history. Aggregate the daily buckets in SQL.

### P-3 — Single-writer SQLite default (High for growth)
Default `DATABASE_URL=sqlite:///./testhub.db`. WAL allows concurrent reads but **one writer at a time**; live runs, imports, and sync all write. Under concurrent writes you'll see `busy_timeout` waits then 5s failures. Postgres is supported and is the correct production default — the docs should make Postgres the recommended path, not an alternative.

### P-4 — In-memory state blocks horizontal scaling (High)
State that must be shared across workers currently lives in a single process:
- WebSocket connection registries (`ws_manager.py`, `notifications.py`).
- Login failure counters (`auth.py:37`).
- AI per-user rate limiter (`ai.py:23`).
- CI dispatch job registry `_JOBS` (`ci.py:38`, explicitly "per-process; lost on restart").

Run two uvicorn workers and: a WS client connected to worker A won't get an event broadcast from worker B; rate/throttle limits multiply per worker; a CI dispatch polled by worker A is invisible to worker B after a restart. **The app is effectively pinned to one worker.** The README already lists "Redis-backed rate limiter / WS state (multi-worker)" as planned — this is the single biggest scaling item.

### P-5 — Synchronous integration/CI calls hold a worker (Medium)
GitHub/GitLab/Jira sync use the **synchronous** `httpx.Client` inside request handlers (`github_sync.py:44`, sync path). A slow provider ties up a worker thread for up to the 15s timeout. CI dispatch uses background polling loops (good) but sync-on-demand is inline. Move blocking provider I/O to `asyncio.to_thread` or an async client + task queue.

### P-6 — No caching layer (Low)
No Redis/response caching; every dashboard hit recomputes aggregates. Fine at current scale; add short-TTL caching for `/insights` and `/initial-data` when concurrency grows.

### P-7 — Missing composite indexes for hot filters (Medium)
Indexed today: `api_tokens.token_hash`, `tests(external_provider, external_key)`, `record_history(entity_type, entity_id)`. **Not** indexed: `run_cases.run_id`, `run_cases.test_id` (joined/aggregated constantly in `/insights` and run views), `defects.status/severity`, `tests.folder_id`, `tests.status`, all the foreign keys used in list filters. On SQLite/Postgres these table scans are cheap under seed data and expensive at scale. Add indexes on the columns that back `GROUP BY`/`WHERE` on `run_cases`, `tests`, and `defects`.

---

## Frontend performance

- **Delivery model:** React 18 UMD vendored locally, JSX transpiled+minified by esbuild at build (`scripts/build-frontend.mjs`). Airgap-friendly and no CDN round-trips — good.
- **No route-level code splitting.** Views are large (`view-test-detail.jsx` 1099 lines, `view-settings.jsx` 1032; ~9.4k JSX total) and appear to ship as one bundle behind hash routing. First-load cost grows with the app. Introduce lazy-loaded view chunks.
- **`/api/initial-data` couples FE load to BE fan-out** (see P-1): the SPA blocks on one large call. Move to per-view fetching with the existing paginated endpoints.
- Fonts are self-hosted woff2 (good). No evidence of image/asset optimization pipeline beyond that.

---

## Scalability assessment (readiness by user count)

| Users | Verdict | Limiting factor |
|---|---|---|
| **10** | ✅ Works as-is | None |
| **1,000** | ⚠️ Works with Postgres + 1 worker | P-3 (switch off SQLite), P-1 latency |
| **10,000** | ⚠️ Needs Redis-backed shared state + read replicas + FE code-split | P-4, P-1, P-7 |
| **100,000** | ❌ Requires re-architecture | P-4 (externalize WS/state), task queue for sync/CI, caching, index pass |
| **1,000,000** | ❌ Not a design goal | Multi-service, sharding/tenancy, event bus |

**Breaking points, in order:** (1) SQLite write contention, (2) single-worker in-memory state, (3) `/initial-data` + requirement coverage N+1, (4) missing indexes on `run_cases`/`tests`.

---

## Recommended actions (ranked by ROI)

1. **Add the missing indexes** (P-7) — hours, immediate query wins, zero risk. *High ROI.*
2. **Fix requirement-coverage N+1 in `/initial-data`** (P-1) — half a day. *High ROI.*
3. **Make Postgres the documented production default** (P-3) — docs + compose already exist. *High ROI.*
4. **Externalize shared state to Redis** (P-4) — the unlock for multi-worker; 1–2 weeks. *High ROI, higher effort.*
5. **Move provider sync I/O off the request path** (P-5) — task queue (Celery/RQ/arq); 1 week.
6. **Frontend route code-splitting + per-view fetch** (FE) — days.
7. **Run `scripts/loadtest.py` and publish a baseline** — establish real numbers before committing to the above ordering.
</content>
