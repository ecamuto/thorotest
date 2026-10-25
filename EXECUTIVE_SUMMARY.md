# ThoroTest — Executive Summary (Technical Due Diligence)

**Prepared:** 2026-07-16 · **Version reviewed:** 1.9.0 · **For:** investment/CTO-level technical evaluation
**Companion reports:** `AUDIT_REPORT.md`, `SECURITY_AUDIT.md`, `PERFORMANCE_REPORT.md`, `TECHNICAL_DEBT.md`, `COMPETITOR_ANALYSIS.md`, `ROADMAP.md`

---

## Verdict

**ThoroTest is a well-engineered, feature-rich, source-available test-management platform that is ahead of the open-source field on its differentiators (unified manual+automated timeline, two-way Git "tests-as-code", native CI dispatch+import, REST+GraphQL+webhooks, BYOK AI). The code quality and test discipline are genuinely above average for a project this young.**

**However, it is not currently safe to deploy on an untrusted network.** Two clusters of state-changing API endpoints — the entire Webhooks router and the write half of the Integrations router — ship **with no authentication whatsoever**, and there is a matching **blind SSRF** and an **authenticated path-traversal-to-file-write**. These are shipping-blockers, but they are localized, obvious in hindsight, and cheap to fix (~1 engineer-day for the critical set). The surrounding auth architecture (argon2id, JWT revocation, OAuth CSRF nonces, RBAC, audit log) is otherwise solid, which is why these read as oversights rather than systemic weakness.

**Investment thesis:** strong product/engineering foundation with a **short, well-defined path to production-ready**. The material risks are (1) the security defects above, (2) single-worker / SQLite-default scaling posture, (3) enterprise-readiness gaps (SSO/SAML/SCIM, multi-tenancy), and (4) a **Commons Clause license** that limits the "open source" narrative and monetization. All four are addressable; none require a rewrite.

---

## Top strengths
1. **Clear, defensible product wedge** — manual + automated results on one timeline; migrate-off-TestRail importers; bidirectional Git sync no OSS competitor offers.
2. **Modern, clean stack** — FastAPI + React 18, router-per-domain backend (~9.4k LOC), thin handlers, dashboards that aggregate in SQL.
3. **Serious test culture** — 626 pytest functions across 55 files + 37 Playwright e2e suites, CI-gated; **zero** TODO/FIXME/HACK markers.
4. **Thoughtful ops touches** — Alembic migrations, `/health` with threadpool DB ping, WAL-tuned SQLite, Docker healthchecks, airgap-capable self-contained frontend.
5. **Strong auth *primitives*** — argon2id with legacy-hash auto-upgrade, token-version revocation honored by REST *and* GraphQL, single-use OAuth state nonces, secrets never echoed in API responses.

## Top risks
1. 🔴 **Unauthenticated Webhooks + Integrations write APIs** (Critical ×2) + **blind SSRF** (Critical) — anonymous CRUD, secret theft, token retargeting, server-side request forgery.
2. 🔴 **Attachment path traversal → arbitrary file write** (High) — realistic RCE path for any logged-in user.
3. 🟠 **Live Anthropic API key sitting in working-tree `.env`** (High) — rotate now.
4. 🟠 **Not horizontally scalable as-is** — WS/rate-limit/CI state is per-process; SQLite is the default. One-worker ceiling.
5. 🟠 **No object-level tenancy** — every authenticated user sees all data; blocks multi-team/SaaS.
6. 🟡 **Commons Clause license** — source-available, *not* OSI open source; adoption/monetization headwind.

## Engineering scorecard (1–10)

| Dimension | Score |
|---|---|
| Architecture | 7 |
| Code quality | 8 |
| Readability | 9 |
| Maintainability | 8 |
| Performance | 6 |
| **Security** | **4** |
| Scalability | 5 |
| Testing | 8 |
| Documentation | 8 |
| DevOps | 6 |
| UX | 7 |
| Innovation | 8 |
| **Overall engineering quality** | **7 / 10** |

*Security drags an otherwise 7.5–8 project down; close the P0 items and the realistic overall is ~8.*

## Recommended immediate actions (this week)
1. Authenticate Webhooks + Integrations write endpoints; add SSRF guard. (~1.5d)
2. Fix attachment path validation. (~0.5d)
3. Rotate the leaked AI key; remove real secrets from the tree. (~0.25d)
4. Add anonymous-access regression tests for every mutating route so this class of bug can't reship. (~1d)

## 12-month arc
- **Q1:** security P0s + quick perf wins → Redis-backed shared state → Postgres default (secure + multi-worker).
- **Q2:** multi-tenancy + SSO/SAML/SCIM (enterprise unlock).
- **Q3:** frontend modernization, requirements traceability, push reporters.
- **Q4:** debt paydown, scale hardening, CLI `run`, and a strategic license decision.

**Bottom line for a CTO:** fund it, but make the P0 security fixes and the anonymous-access test gate a condition of the first milestone. The team clearly *can* build well — the gap is a hardening pass and enterprise plumbing, not core competence.
</content>
