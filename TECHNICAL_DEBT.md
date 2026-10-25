# ThoroTest — Technical Debt Assessment

**Audit date:** 2026-07-16 · **Version:** 1.9.0
**Codebase:** ~9.4k LOC backend (Python/FastAPI), ~9.4k LOC frontend (React/JSX), Node CLI, 285 tracked files.

Overall debt level: **LOW–MODERATE**. This is an unusually clean codebase for its feature breadth. The debt that exists is concentrated in (a) the dual migration system, (b) horizontal-scaling assumptions baked into module-level state, and (c) frontend architecture choices (window globals, no code-splitting). None of it is the "big ball of mud" variety; most is addressable incrementally.

> **2026-10-25 update:** the production bootstrap and shared runtime parts of
> D-2/D-3 are complete. D-5 is reduced: v1.15 loads views by route and defers
> 89% of minified view code, while the remaining `window.X` → ESM migration is
> a maintainability improvement rather than a first-load blocker.

---

## Debt scorecard

| Dimension | Level | Notes |
|---|---|---|
| Code debt | Low | 0 TODO/FIXME/HACK markers; small, single-responsibility modules; consistent naming. |
| Architectural debt | Moderate | Single-process in-memory state; no tenancy layer; FE window-global coupling. |
| Maintainability debt | Low | Router-per-domain, thin handlers, docstrings explain *why*. |
| Testing debt | Low | 626 pytest functions across 55 files + 37 Playwright specs; CI-gated. Gaps in authz-negative tests. |
| Documentation debt | Low | README + 6 `docs/` guides + architecture doc; some drift (version/test counts). |
| Operational debt | Moderate | No metrics endpoint, no structured logs, no migration-runner separation, secrets in `.env` file. |
| Security debt | **High (localized)** | Two unauthenticated routers (see SECURITY_AUDIT C-1/C-2) — small code, large blast radius. |

---

## Itemized debt

### D-1 — Dual schema-migration system (Moderate)
`backend/main.py` carries **two** migration paths: a hand-rolled `_run_migrations()` (idempotent `ALTER TABLE ADD COLUMN` loop, `main.py:57-132`) *and* Alembic (`migrations/`, 11 revisions). `_ensure_schema()` (`main.py:135-166`) branches: fresh DB → `alembic upgrade head`; legacy pre-Alembic DB → `create_all()` + legacy migrate + `stamp head`. This is well-documented and works, but it's two sources of truth for schema. The legacy path adds columns as untyped `VARCHAR(255)` with Python-side backfills — it should be considered frozen and eventually deleted once no pre-Alembic installs remain.
**Cost if ignored:** confusion and drift risk on future schema changes. **Fix:** mark `_run_migrations` legacy-only, add a hard cutover date, route all new changes through Alembic exclusively. **Effort:** low.

### D-2 — Migrations run inside the app lifespan (Moderate, operational)
`_ensure_schema()` runs `alembic upgrade head` on every boot (`lifespan`, `main.py:199`). Convenient for single-node Docker, but in a multi-replica rollout every replica races to migrate, and a bad migration takes down app start. **Fix:** separate migration step in the deploy pipeline (an init container / `make migrate` gate) and have the app *verify* head rather than apply it.

### D-3 — Module-level singletons hold runtime state (Moderate, architectural)
`ws_manager.manager`, `notif_manager`, `_login_failures`, `ai._rate_store`, `ci._JOBS` are process-global. This is the root of the horizontal-scaling limit (see PERFORMANCE_REPORT P-4). Debt because the abstraction (an in-memory manager) will have to be swapped for a Redis-backed one, touching several call sites. **Fix:** introduce a small `StateBackend` interface now (even if the only impl is in-memory) so the Redis swap is localized later.

### D-4 — Timestamps stored as ISO strings, not native datetimes (Low, pervasive)
Nearly every model stores `created_at`/`updated_at`/`when` as `String(64)` ISO text (`models.py` throughout). The code relies on lexicographic comparison for date ranges (`main.py:405`, comment "lexicographic >= works"). This works only because everything is UTC ISO-8601, but it forfeits DB date functions, timezone correctness guarantees, and index-friendly range scans, and it's fragile if any writer ever deviates from the format. **Fix (large, low-urgency):** migrate to `DateTime` columns; medium effort due to breadth.

### D-5 — Frontend uses `window.X` globals instead of modules (Moderate, FE architectural)
Per project memory and `frontend/react-globals.js`, the frontend wires React and shared state through `window` globals rather than ES module imports, built by a bespoke esbuild script. v1.15 adds route-level delivery on top of this contract, so views no longer block first paint, but the globals remain non-idiomatic and still block tree-shaking. **Fix:** migrate to standard ESM + a conventional bundler entry opportunistically; medium effort.

### D-6 — Large view components (Low)
`view-test-detail.jsx` (1099 lines), `view-settings.jsx` (1032), `view-library.jsx` are big single-file views mixing data-fetching, state, and presentation. Not broken, but they'll resist change. **Fix:** extract hooks and subcomponents opportunistically.

### D-7 — Repo hygiene: databases and backups in the working tree (Low)
The working tree contains `presentation.db`, `presentation.db.bak`, `e2e.db`, `testhub.db`, WAL/SHM files, `scratch-batch.log`, and several `*.local.*` scripts. They're git-ignored, but shipping `.db` files around risks data/secret leakage and bloats the 270 MB checkout. **Fix:** `make clean` target + document that DBs never live in the tree.

### D-8 — No dependency pinning / lockfile for Python (Low–Moderate, supply chain)
`requirements.txt` uses `>=` ranges only; there's no hash-pinned lock (`pip-tools`/`uv.lock`/`poetry.lock`). A transitive update can change behavior between builds. Node side has `package-lock.json` (good) and the CLI is dependency-free (excellent). **Fix:** generate a pinned, hashed lock for Python and run a scheduled `pip-audit`/Dependabot.

### D-9 — Documentation drift (Low)
README advertises "576 unit + 31 e2e suites"; the tree has 626 `test_` functions across 55 files and 37 `.spec.ts`. `.env.example` references "Phase 14" internal phase numbers. Minor, but a diligence reviewer notices. **Fix:** derive the badge counts in CI.

### D-10 — Weak/duplicated config surface (Low)
There are two notification-config surfaces: system SMTP via env (`emailer.py`) and per-user SMTP stored in `NotificationConfig` (`models.py:356`, including `smtp_pass` in the DB). Storing per-user SMTP passwords in the app DB is both debt and a (minor) security concern. Consolidate and encrypt-at-rest or drop per-user SMTP.

---

## Estimated remediation effort

| Bucket | Items | Rough effort |
|---|---|---|
| Immediate (security) | C-1/C-2 auth, H-1 traversal, H-3 key rotation (see SECURITY_AUDIT) | ~1 day |
| Quick wins | D-1, D-7, D-9, index pass (perf P-7) | ~2–3 days |
| Structural | D-2 migration split, D-3 state backend, D-8 lockfile, perf P-1 | ~2–3 weeks |
| Long horizon | D-4 datetime migration, D-5 ESM migration, tenancy (SECURITY H-2) | ~1–2 months |

**Future maintenance cost:** LOW if the security and multi-worker items are addressed; the code is otherwise well-factored and cheap to extend (adding a router/model is a well-worn path). **Risk level:** the *code* is low-risk; the *deployment posture* (unauth endpoints, single-worker, SQLite default, secret-in-file) is where the real risk concentrates and all of it is fixable without rewrites.
</content>
