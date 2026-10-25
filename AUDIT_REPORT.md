# ThoroTest — Technical Due Diligence Report

**Prepared:** 2026-07-16
**Version reviewed:** 1.9.0 — branch `feat/demo-ribbon`, commit `e9040d2`
**Reviewer scope:** full-repository source review (backend, frontend, CLI, migrations, infra, CI, docs) + market research.
**Method:** manual code reading with targeted static analysis (endpoint auth scan, grep sweeps for injection/dangerous calls, index inventory) + web research for the competitive landscape. No DAST, no dependency-CVE scan, and no load test were executed; items needing runtime confirmation are marked.

Companion deliverables: `EXECUTIVE_SUMMARY.md`, `SECURITY_AUDIT.md`, `PERFORMANCE_REPORT.md`, `TECHNICAL_DEBT.md`, `COMPETITOR_ANALYSIS.md`, `ROADMAP.md`.

> **Phase 1 production-engineering update — 2026-10-24 (v1.14, unreleased).**
> The single-worker production blockers identified by the original review are
> now addressed in code: atomic Redis-backed quotas, cross-worker WebSocket
> delivery, database-backed CI jobs with renewable/fenced leases, explicit
> one-shot schema bootstrap, structured request logging, Prometheus metrics,
> and a gated multi-architecture release-image workflow with SBOM, provenance,
> attestation, and keyless signing. Application readiness now waits for both
> Redis connectivity and an active Pub/Sub subscription. The runtime lock is
> generated in an isolated environment and the current dependency audit has no
> known vulnerabilities.
>
> Local acceptance evidence: complete backend, CLI, frontend, and Playwright
> gates; a clean Python 3.12 container build; bootstrap from an empty database
> inside that image; real Redis tests proving atomic quota sharing and event
> delivery between distinct worker instances; PostgreSQL load baselines with
> one and two application workers; and Redis loss/recovery with the documented
> liveness/readiness behaviour. See `PERFORMANCE_REPORT.md` for the measured
> baseline. A PostgreSQL custom-format backup at the v1.13 schema was restored
> into a separate database and upgraded to the new head without losing its
> probe user; an injected migration failure exited non-zero and left the prior
> Alembic revision unchanged. All V14-5 local gates are therefore complete.
> This is a Phase 1 engineering completion, not yet a commercial-launch sign-off.
>
> **Provisional post-Phase-1 score movement:** Architecture 9, Code quality 9,
> Readability 9, Maintainability 9, Security 9, Testing 9, Documentation 9,
> DevOps 9, Performance 9, and Scalability 9. UX and Innovation remain 8 because
> Phase 1 did not target them. Later phases must close those two dimensions to
> satisfy the ≥9/10 objective across the entire scorecard.
>
> **Phase 2 experience update — 2026-10-25 (v1.15, unreleased).** UX and
> Innovation now reach the provisional 9/10 target. Route-level delivery
> defers approximately 266 KB of minified view JavaScript (89% of view code),
> navigation has loading/error recovery, focus and live announcements, and axe
> gates the core product flows against WCAG A/AA in dark and light themes.
> `thorotest run` now dispatches GitHub/GitLab CI through the durable job engine,
> waits through result collection, and returns provider-aware exit codes and
> JSON. The full scorecard is therefore provisionally ≥9/10; commercial launch
> still depends on the separate product decisions noted in §23 (tenancy/SSO,
> licensing, support and go-to-market), not another foundational rewrite.

> **Phase 3 commercial self-host update — 2026-10-25 (v1.16, unreleased).**
> The launch target is now explicit: one dedicated installation per customer
> organization, not a shared multi-customer SaaS. GitHub, GitLab, and Jira sync
> execute on recoverable database-leased provider jobs instead of holding HTTP
> workers; scheduled Jira sync uses the same queue. Attachments enforce an
> extension/MIME matrix and path confinement through deletion, and configurable
> AI egress is guarded unless a narrow private-target opt-in is set. A secret-safe
> strict production preflight checks the supported PostgreSQL/Redis/HTTPS
> topology, and the repository now documents customer handoff, licensing and
> support boundaries. Multi-tenant authorization, SAML/SCIM, pricing, signed
> customer agreements and SLA commitments remain explicit later/external gates.
> Local acceptance: 830 backend tests passed (4 skipped), 69 CLI tests passed,
> all 265 Playwright cases passed after one corrected documentation-version
> rerun, the production frontend/container builds succeeded, the fresh-image
> migration reached `f3a1b2c4d5e6`, strict preflight passed 14/14, and the
> dependency audit reported no known vulnerabilities.

> **Current-validation update — 2026-08-28 (v1.13.0, branch `fix/audit-findings-v1-13`).** A review against commit `c36badb` confirmed the v1.10 remediation and identified five current gaps. The branch closes all five: category and pipeline-reconciliation RBAC, long-lived session JWTs in WebSocket URLs (replaced by one-minute scoped tickets), a non-blocking dependency audit and ignored `python-jose`/`ecdsa` advisory (migrated to PyJWT and made blocking), and webhook unit tests coupled to live DNS. During the ticket change, an additional Critical scope-confusion flaw was found and fixed: `scope=2fa_pending` tokens were accepted by REST/GraphQL session validation before TOTP completion. Regression coverage now checks REST, WebSocket, role, revocation, and API-token boundaries. The original v1.9 assessment below remains a point-in-time record rather than a current scorecard.

> **Remediation update — 2026-07-17 (v1.10.0).** The Week-1 P0 items are closed:
> - **C-1/C-2/C-3 + H-1** (unauthenticated Webhooks and Integrations routers, blind SSRF via webhook test/delivery, attachment path traversal) — fixed in commit `6d33afa`, merged to `main` via PR #22 and shipped in v1.10.0. Includes a new SSRF egress guard (`backend/net_guard.py`) applied at webhook create/update/test/delivery, and the anonymous-access regression suite `backend/tests/test_authz_p0.py` (I-6).
> - **H-3** (live Anthropic key in working-tree `.env`) — key rotated 2026-07-17; `.env` is git-ignored and the Dockerfile copies explicit paths only, so the file reaches neither commits nor images.
> - **Quick wins Q-1/Q-2/Q-3** (hot-filter indexes, `/initial-data` requirement-coverage N+1, CSV formula-injection neutralization) — merged via PR #24.
> - **Quick wins Q-4–Q-8** (12-char password policy with blocklist, random first-boot admin password, `make clean-data` repo hygiene, `requirements.lock` + pip-audit CI job + Dependabot, README badge counts derived and CI-gated) — on PR #25 (`chore/quick-wins-q4-q8`), pending merge. Backend suite now at 699 tests / 653 test functions.
>
> Findings resolved since the review are marked ✅ (merged) or 🔶 (fix in open PR) in place below; the original point-in-time assessment of commit `e9040d2` is otherwise unchanged.

---

## 1. Executive Summary

ThoroTest is a self-hosted, source-available test-management platform whose thesis is *"manual and automated tests share one timeline."* It backs that with a modern implementation: a FastAPI backend (~9.4k LOC, cleanly split into a router-per-domain layout), a React 18 frontend (~9.4k LOC JSX, self-contained/airgap-capable), REST **and** GraphQL APIs, two-way GitHub/GitLab "tests-as-code" YAML sync, native CI dispatch+import for GitHub Actions and GitLab CI, nine migration importers, a BYOK AI assistant, and an enterprise-flavored auth stack (JWT, RBAC, TOTP 2FA, OAuth, audit log, API tokens, HMAC webhooks).

The engineering is above average for the project's age: dashboards aggregate in SQL rather than in Python, migrations use Alembic, there are 626 pytest functions and 37 Playwright suites under CI, and there are **zero** TODO/FIXME/HACK markers in the tree.

The critical caveat: **two clusters of mutating endpoints ship with no authentication at all** — the entire Webhooks router and Integrations create/update/delete — plus a **blind SSRF** and an **authenticated path-traversal file-write**. These are production blockers but are localized and cheap to remediate (~1 engineer-day for the critical set). *(✅ Resolved 2026-07-17 in v1.10.0 — see remediation update above.)* The remaining risks are scaling posture (single-worker, SQLite default), enterprise gaps (SSO/SAML/SCIM, multi-tenancy), and a Commons Clause license that constrains the open-source story.

**Overall engineering quality: 7/10** (≈8 once the P0 security items are closed — *condition met as of v1.10.0*).

## 2. Overall Assessment

| Area | Assessment |
|---|---|
| Product concept | Strong, differentiated, validated against the market. |
| Code quality | High; small modules, consistent idioms, good "why" comments. |
| Security | Solid primitives undermined by two glaring access-control holes. |
| Performance | Good at team scale; architectural ceiling at growth. |
| Scalability | Single-process assumptions block horizontal scale today. |
| Testing | Strong breadth; light on negative-authz cases. |
| DevOps | Reasonable Docker/CI; gaps in secrets, metrics, migration isolation. |
| Docs | Above average; minor drift. |
| Investability | Fundable with security P0s as a first-milestone gate. |

## 3. Project Strengths
- **Differentiated product** — unified manual+automated timeline; bidirectional Git sync; native CI trigger+import; REST+GraphQL+webhooks+AI in one OSS tool.
- **Clean architecture** — `backend/routers/*` one file per domain; thin handlers delegating to `*_sync.py`/`*_utils.py`; injectable fetchers make provider code testable without network (`github_sync.sync_repo(fetcher=...)`).
- **SQL-first hot paths** — `/api/insights`, `/insights/test-health` aggregate with `func.count`/`GROUP BY` (`main.py:308-431`).
- **Auth primitives done right** — argon2id + legacy auto-upgrade (`auth_utils.py:40-59`), JWT `token_version` revocation on REST+GraphQL, OAuth single-use state nonces (`oauth.py:54-70`), secrets never echoed.
- **Test discipline** — 626 pytest fns / 55 files + 37 e2e specs, CI-gated across backend/CLI/e2e jobs; 0 TODO/FIXME.
- **Ops hygiene** — Alembic, `/health` threadpool DB ping, WAL pragmas, Docker + compose healthchecks, self-contained assets.

## 4. Project Weaknesses
- **Access control gaps** (Webhooks + Integrations write, see §9) — Critical. ✅ *Fixed in v1.10.0.*
- **SSRF** via unauth webhook test/delivery — Critical. ✅ *Fixed in v1.10.0.*
- **Path traversal** in attachment upload — High. ✅ *Fixed in v1.10.0.*
- **Secret in working-tree `.env`** (real AI key) — High. ✅ *Key rotated 2026-07-17.*
- **No object-level authorization / tenancy** — High for multi-team.
- **Single-process state** (WS, throttle, AI limit, CI jobs) blocks multi-worker — High for scale.
- **SQLite default** for production path — Medium.
- **Dual migration system**, ISO-string timestamps, FE `window` globals — Moderate debt.
- **Commons Clause** license — strategic risk.

## 5. Critical Risks
1. **Anonymous compromise of integrations/webhooks** → token retargeting/exfiltration, secret theft, alert tampering, SSRF pivot into internal networks. ✅ *Closed in v1.10.0 (`6d33afa`).*
2. **Arbitrary file write** by any authenticated user → potential RCE. ✅ *Closed in v1.10.0 (`6d33afa`).*
3. **Leaked live API key** → billing/abuse exposure until rotated. ✅ *Rotated 2026-07-17.*
4. **Un-scalable state** → data-consistency and delivery failures the moment a second worker/replica is added. *(Open — roadmap S-1.)*

All four are fixable without architectural rewrites; #1–#3 are ~1.5 engineer-days combined *(and were closed in ~1 day, as estimated)*.

## 6. Technical Findings (map)

| Domain | Key files | Headline |
|---|---|---|
| Auth | `auth_utils.py`, `routers/auth.py`, `routers/oauth.py`, `routers/totp.py` | Strong primitives; policy/lifecycle improvable |
| Access control | `routers/webhooks.py`, `routers/integrations.py`, `routers/attachments.py` | **Two unauth routers + traversal** |
| Data model | `models.py` (22 tables) | Coherent; string PKs; ISO-string timestamps; thin indexing |
| Aggregation | `main.py` insights/initial-data | SQL-first; one N+1 in requirement coverage |
| Realtime | `ws_manager.py`, `notifications.py` | In-memory registries (single-worker) |
| Integrations | `github_sync.py`, `gitlab_sync.py`, `jira_sync.py`, `routers/ci.py` | Injectable, tested; sync I/O on request path |
| Frontend | `frontend/*.jsx` (~9.4k LOC) | Modern React; window globals; no code-split |
| CLI | `cli/` (zero deps, node:test) | Clean, dependency-free |

## 7. Architecture Review
**Style:** modular monolith. FastAPI app (`main.py`) mounts ~30 domain routers under `/api`, a Strawberry GraphQL router under `/graphql`, two WebSocket endpoints, and serves the built SPA as static files. Persistence via SQLAlchemy 2.0 ORM against SQLite/Postgres/MySQL.

**Layering & cohesion:** good. Handlers are thin; business logic lives in domain modules (`*_sync.py`, `*_utils.py`, `importers/`); HTTP clients are separated from DB upserts and made injectable for tests. SOLID/DRY/KISS are broadly respected; no over-engineering.

**Coupling concerns:** (1) module-level singletons for runtime state couple correctness to a single process (`ws_manager`, `notif_manager`, `_login_failures`, `ai._rate_store`, `ci._JOBS`); (2) frontend `window`-global wiring couples views to global state; (3) `/api/initial-data` couples SPA load to a backend fan-out.

**Configuration:** env-driven via `.env`/`dotenv`; production guards (refuse default `SECRET_KEY`/`DEMO_MODE` when `ENVIRONMENT=production`) are a nice touch.

**Extensibility:** adding a model+router+migration is a well-worn path; importer plug-in pattern is clean. **Testability:** high, thanks to dependency injection and fetcher seams.

**Weaknesses (severity):** no tenancy/authorization layer (High), single-process state (High), migrations executed in app lifespan (Medium), dual migration system (Medium).

## 8. Code Quality Review
- **Smells:** minimal. Largest backend files (`schemas.py` 633, `main.py` 608, `oauth.py` 515) are cohesive, not god-objects. Frontend has a few large views (`view-test-detail.jsx` 1099, `view-settings.jsx` 1032) that would benefit from extraction.
- **Duplication:** low; some repeated secret-preservation and pagination patterns already centralized (`_pagination.py`).
- **Dead code / TODOs:** 0 TODO/FIXME/HACK; no obvious dead modules. Multiple stray `*.db`/`*.local.*`/log files in the tree are hygiene noise (git-ignored).
- **Naming & consistency:** strong and consistent; docstrings explain rationale, not mechanics.
- **Error handling:** provider clients translate errors into meaningful HTTP codes (`github_sync`, `ai.py` map SDK errors → 502/503); auth failures are audited. Good.
- **Input validation:** Pydantic schemas throughout; gaps are in *authorization*, not parsing — except attachment `entity_type`/filename (unvalidated, see §9).
- **Magic values:** mostly named constants (`INITIAL_DATA_CAPS`, rate windows, timeouts).

## 9. Security Review (summary — full detail in `SECURITY_AUDIT.md`)

| Sev | Finding | Location | Status |
|---|---|---|---|
| 🔴 Critical | Webhooks API fully unauthenticated (CRUD + secret regen) | `routers/webhooks.py` | ✅ Fixed v1.10.0 |
| 🔴 Critical | Integrations create/update/delete unauthenticated | `routers/integrations.py:24,36,88` | ✅ Fixed v1.10.0 |
| 🔴 Critical | Blind SSRF via unauth `POST /webhooks/{id}/test` + delivery | `routers/webhooks.py:71` | ✅ Fixed v1.10.0 (`net_guard.py`) |
| 🟠 High | Path traversal → arbitrary file write on upload | `routers/attachments.py:40-79` | ✅ Fixed v1.10.0 |
| 🟠 High | No object-level authorization (all authed users see all data) | app-wide | Open (roadmap M-1) |
| 🟠 High | Live Anthropic key in working-tree `.env` | `.env:36` | ✅ Rotated 2026-07-17 |
| 🟡 Medium | SSRF via admin-set integration/AI base URLs | `github/gitlab/ai` | Open (roadmap S-8) |
| 🟡 Medium | Attachment IDOR + no MIME allow-list | `attachments.py` | Open (roadmap S-5) |
| 🟡 Medium | CSV formula injection in exports | `runs.py`/`tests.py` export | ✅ Fixed (PR #24) |
| 🟡 Medium | Per-process login throttle (bypassable multi-worker) | `auth.py:37` | Open (roadmap S-1) |
| 🟡 Medium | Weak password policy (6 chars) | `auth.py:69` | 🔶 Fix in PR #25 |
| 🟡 Medium | 7-day JWT, global-only revocation | `auth_utils.py:21` | Open (roadmap M-4) |
| 🟢 Low | CORS `*` permitted; default admin cred; verify GraphQL resolver authz | various | Default admin cred 🔶 PR #25; rest open |

**Done well:** argon2id + legacy upgrade, OAuth CSRF nonces, token revocation on REST+GraphQL, secrets never echoed, user-enumeration-resistant password reset, prod boot guards, HMAC-signed webhooks, ORM-only queries (no SQL-injection surface). The two Critical access-control holes are oversights against an otherwise strong baseline — *and were closed within a day of the report (v1.10.0), with `test_authz_p0.py` guarding against recurrence.*

## 10. Performance Review (summary — full detail in `PERFORMANCE_REPORT.md`)
- **Strengths:** SQL aggregation on dashboards, blocking work offloaded to threads, AI queries use `joinedload`, payloads capped, SQLite WAL-tuned.
- **Bottlenecks:** `/initial-data` fan-out with a requirement-coverage N+1 (P-1, ✅ fixed in PR #24); single-writer SQLite default (P-3); in-memory state blocks multi-worker (P-4); sync provider I/O on request path (P-5); missing indexes on `run_cases`/`tests`/`defects` hot columns (P-7, ✅ added in PR #24, Alembic `a7c3e9f14b02`); no caching layer; frontend ships without route code-splitting.
- **Est. quick wins:** index pass + N+1 fix = large latency reduction at scale for hours of work. *(Both merged in PR #24.)*

## 11. Database Review
- **Engine:** SQLAlchemy 2.0 ORM; SQLite default, Postgres/MySQL via `DATABASE_URL`. Portability is real (dialect-neutral DDL in the legacy path).
- **Schema:** 22 tables, coherent domain model; string PKs (`TC-…`, `R-…`) chosen for human-readable ids and stable cross-system matching (`external_provider`/`external_key`) — a deliberate, sensible tradeoff.
- **Constraints:** FKs with `ondelete` on association tables and child rows; useful `UniqueConstraint`s (custom fields, oauth identity, requirement_tests). Good.
- **Indexing:** thin. Present: `api_tokens.token_hash`, `tests(external_provider,external_key)`, `record_history(entity_type,entity_id)`. **Missing** on frequently filtered/joined columns: `run_cases.run_id`/`test_id`, `tests.folder_id`/`status`, `defects.status`/`severity`. Add before scale.
- **Timestamps:** stored as ISO strings (`String(64)`), compared lexicographically. Works under a strict UTC-ISO invariant but forfeits DB date functions and is fragile long-term (DEBT D-4).
- **Migrations:** Alembic (11 revisions) + a legacy in-place path for pre-Alembic installs; run inside app boot (see DevOps).
- **Consistency/growth:** fine to low-thousands of rows; needs indexes + Postgres for larger installs.

## 12. DevOps Review
- **Docker:** clean two-stage build (node build → python slim runtime), healthcheck present. **Runs as root** (no `USER`) — container-hardening gap. Compose ships a **hardcoded weak Postgres password** (`thorotest`) and an uploads volume.
- **CI:** GitHub Actions with three jobs (pytest, CLI node:test, Playwright), JUnit artifacts, concurrency cancellation, `!cancelled()` to publish results while still gating. Solid.
- **Secrets:** loaded from `.env` file (real key present in tree — see §9). No secret-manager integration.
- **Migrations on boot:** convenient but races across replicas and couples deploy safety to app start (DEBT D-2).
- **Observability:** `/health` (liveness+DB) is good; **no `/metrics`**, no structured logging, no alerting/tracing. README lists Prometheus as planned.
- **Backup/recovery:** `BACKUP.md` exists (good); recovery process should be drill-tested.
- **Rollback:** image-based rollback via compose `restart`; no documented DB-migration rollback strategy beyond Alembic downgrades.

## 13. Testing Review
- **Breadth:** 626 pytest functions / 55 files (backend) + 37 Playwright `.spec.ts` suites (e2e), plus a Node `cli/test/` suite. CI runs all three.
- **Quality:** provider code is unit-testable via injected fetchers; e2e covers auth, navigation, library, runs, pipelines, import, OAuth, audit log, custom fields. Strong.
- **Gaps:** (1) **negative authorization** — the unauth-endpoint defects (§9) imply missing "anonymous request must 401/403" tests for mutating routes; add them as regression guards. *(✅ Added in v1.10.0: `backend/tests/test_authz_p0.py`.)* (2) SSRF/path-traversal abuse cases. *(✅ Covered by the same suite.)* (3) load/perf tests exist as a script (`scripts/loadtest.py`) but no published baseline. (4) no dependency-CVE gate. *(🔶 PR #25 adds a pip-audit CI job + Dependabot.)*
- **Flakiness:** commit history shows deliberate de-flaking work (webhook/PATCH awaits) — good sign of maturity.

## 14. Documentation Review
- **Strong:** thorough README, `docs/` set (architecture, api, cli, configuration, github/gitlab CI), `BACKUP.md`, `PRIVACY.md`, `TERMS.md`, `CHANGELOG.md`, in-app About page.
- **Gaps/drift:** test-count badges out of date (576 vs 626); `.env.example` leaks internal "Phase N" naming; no explicit "production hardening" checklist that would have surfaced the auth gaps; security policy / disclosure process not evident (`SECURITY.md` recommended).
- **Onboarding:** `install.sh` + `make dev`/`make docker-up` are frictionless.

## 15. UX Review
- **Positives:** unified timeline concept, coverage bars, live run view over WebSocket, import preview-before-write, i18n (en/it/de/es/fr), self-hosted fonts, in-app docs/About.
- **Concerns (static-review level; not user-tested):** large monolithic views may mean heavy first paint (no code-splitting); SPA blocks on one `/initial-data` call; accessibility not verified (no evidence of a11y testing — audit ARIA/contrast/keyboard nav); no visible empty/error-state design review. Recommend a dedicated a11y + first-load UX pass.

## 16. Market Research
The market splits into closed SaaS (TestRail/Zephyr/Xray/qTest/Qase), established OSS (Kiwi TCMS, TestLink, Squash TM), and emerging tools. ThoroTest sits in "source-available self-hosted" while matching SaaS-era modernity. Full detail and sources in `COMPETITOR_ANALYSIS.md`.

## 17. Competitor Comparison (condensed)

| | ThoroTest | Kiwi TCMS | TestLink | Squash TM | TestRail | Xray/Zephyr |
|---|---|---|---|---|---|---|
| License | MIT+Commons Clause (source-available) | GPLv2 (OSI) | GPL (OSI) | LGPL (OSI) | Proprietary | Proprietary |
| Manual+Auto one timeline | ✅ | Partial | Manual-first | Partial | Separate | Via Jira |
| 2-way Git tests-as-code | ✅ | ❌ | ❌ | ❌ | ❌ | ❌ |
| CI trigger+import | ✅ | Push reporters | ❌ | Add-ons | Import | ✅ |
| REST+GraphQL+webhooks | ✅ | REST/RPC | XML-RPC | REST | REST | REST |
| AI assistant | ✅ BYOK | ❌ | ❌ | ❌ | Add-on | Add-on |
| Community/maturity | Early | **High** | High (legacy) | Med | High | High |
| SSO/SAML/SCIM | Planned | Partial | ❌ | ✅ | ✅ | ✅ |

**Read:** ThoroTest leads the OSS field on Git/CI/API/AI; trails on community maturity, true-OSI licensing, and enterprise auth/tenancy.

## 18. Best Practices Missing
- Authenticate-by-default posture (deny-by-default router dependencies) — would have prevented §9 Critical/1–2.
- SSRF egress allow-list shared across outbound HTTP callers.
- Secret management (no secrets in files); dependency lockfile + CVE scanning.
- Object-level authorization / tenancy.
- SSO/SAML/OIDC + SCIM.
- `/metrics`, structured logs, tracing.
- Migration step decoupled from app boot; non-root container; strong DB credentials.
- `SECURITY.md` + coordinated disclosure.

## 19. Technical Debt Assessment
Overall **LOW–MODERATE** (full detail in `TECHNICAL_DEBT.md`). Concentrations: dual migration system (D-1), migrations-on-boot (D-2), in-memory state singletons (D-3), ISO-string timestamps (D-4), FE window globals (D-5), Python dep pinning (D-8). Code-level debt is low; deployment-posture debt is where risk concentrates and is fixable incrementally.

## 20. Scalability Assessment

| Users | Verdict | Limiter |
|---|---|---|
| 10 | ✅ as-is | — |
| 1,000 | ⚠️ Postgres + 1 worker | SQLite→PG, `/initial-data` |
| 10,000 | ⚠️ Redis state + replicas + FE split | in-memory state, indexes |
| 100,000 | ❌ re-architecture | externalize state, task queue, caching |
| 1,000,000 | ❌ not a goal | multi-service/tenancy/event bus |

Breaking points in order: SQLite writes → single-worker state → `/initial-data` N+1 → missing indexes.

## 21. Engineering Scorecard

| Dimension | Score /10 | Rationale |
|---|---|---|
| Architecture | 7 | Clean modular monolith; single-process state + no tenancy cap it. |
| Code Quality | 8 | Small cohesive modules, 0 TODO, good comments. |
| Readability | 9 | Consistent naming, rationale docstrings, clickable structure. |
| Maintainability | 8 | Easy to extend; some large FE views; dual migrations. |
| Performance | 6 | SQL-first dashboards, but N+1 + missing indexes + no cache. |
| Security | 4 | Strong primitives, but two unauth routers + SSRF + traversal. *(All fixed in v1.10.0 — post-remediation ≈7.)* |
| Scalability | 5 | One-worker ceiling; SQLite default. |
| Testing | 8 | 626 unit + 37 e2e, CI-gated; light on negative-authz *(closed in v1.10.0; suite now 685)*. |
| Documentation | 8 | Broad and clear; minor drift; no SECURITY.md. |
| DevOps | 6 | Good Docker/CI; secrets-in-file, root container, no metrics. |
| UX | 7 | Strong concepts; a11y/first-load unverified. |
| Innovation | 8 | Git 2-way sync + CI dispatch + GraphQL + AI in one OSS tool. |
| **Overall** | **7** | Security holds it back; ≈8 once P0s close. |

## 22. Prioritized Improvement Plan
Full plan with IDs, effort, and ROI in `ROADMAP.md`. Sequence:
- **Week 1 (P0):** authenticate Webhooks + Integrations; SSRF guard; fix attachment traversal; rotate AI key; add anonymous-access regression tests. (~1 day of fixes + 1 day of tests.) ✅ **Done 2026-07-17 (v1.10.0).**
- **Weeks 1–3 (quick wins):** index pass ✅, `/initial-data` N+1 fix ✅, CSV-injection guard ✅ (merged, PR #24); password policy 🔶, dep lockfile + CVE scan 🔶, repo hygiene 🔶, random admin password 🔶, badge drift 🔶 (PR #25).
- **Month 1–2:** Redis-backed shared state (multi-worker unlock), sync I/O off request path, Postgres default, migration/boot separation, structured logs + metrics.
- **Month 3–6:** object-level tenancy, SSO/SAML/SCIM, FE ESM + code-split, JWT lifecycle, requirements traceability, push reporters.
- **Month 6–12:** datetime migration, retire legacy migration path, scheduled reports, scale hardening, CLI `run`, license decision.

## 23. Final Recommendations
1. **Treat the §9 Critical/High items as a release gate.** They are small, unambiguous, and cheap; nothing else should ship over them. ✅ *Gate met: fixed and merged before the v1.10.0 tag.*
2. **Adopt deny-by-default routing** so an omitted auth dependency fails closed, and enforce it with the negative-authz test suite.
3. **Commit to Postgres + Redis + multi-worker** as the reference production topology; it is the single biggest unlock for scale and is mostly plumbing.
4. **Decide the enterprise path early** — tenancy + SSO/SCIM define whether this can be sold up-market or hosted multi-customer.
5. **Resolve the license question** deliberately: Commons Clause protects against SaaS resale but forecloses the "open source" community flywheel and some procurement.
6. **Stand up basic supply-chain hygiene** (lockfile, `pip-audit`/Dependabot, `SECURITY.md`).

## 24. Conclusion
ThoroTest is a **credible, well-built, and genuinely differentiated** entrant in self-hosted test management. The core engineering — architecture, testing, API breadth, and product concept — is strong enough to justify investment. Its problems are **specific and bounded**, not structural: a hardening pass (close the access-control holes, add SSRF/traversal defenses, remove secrets from the tree), a scaling pass (Postgres + Redis + multi-worker), and an enterprise-readiness pass (tenancy + SSO). A capable team could take this from "impressive prototype with sharp edges" to "production-grade product" within two to three quarters. The recommendation is **fund, with the P0 security fixes and an anonymous-access test gate as explicit conditions of the first milestone.** *Update 2026-07-17: both conditions are already met — fixes and the negative-authz suite shipped in v1.10.0.*

---
*This report is based on static source review as of commit `e9040d2`. Confirm the runtime-flagged items (GraphQL resolver authz, load numbers, dependency CVEs) with dynamic testing before final investment sign-off.*
</content>
