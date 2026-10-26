# v1.16.0 release sign-off

**Candidate date:** 2026-10-26

**Deployment model:** dedicated self-hosted instance for one trusted customer
organization

**Current status:** local release-candidate gates passed; pull-request CI and
the Git tag remain the publication gates

This is the current technical assessment and release record. The longer audit,
security, performance, and debt reports are preserved as historical v1.9
baselines; their resolved findings must not be read as the current product
state.

## Release contract

The release is acceptable only when all of the following are true:

- `package.json`, `package-lock.json`, the README badge, changelog, supported
  security version, and Git tag agree on `1.16.0`;
- every direct Python requirement exists in `requirements.lock` at a version
  satisfying its declared constraint;
- backend, CLI, production frontend, and complete Playwright suites pass;
- the dependency CVE scan and production container build pass;
- the runtime image is non-root and strict production preflight passes inside
  that image;
- a database at the last public v1.13 schema upgrades to the current Alembic
  head, starts with PostgreSQL and required Redis, and passes the black-box
  security/readiness probe;
- a quiesced PostgreSQL dump and uploads-volume copy restore into fresh storage,
  after which operator login, authenticated reads, release metadata, and the
  upload sentinel still work;
- the tagged multi-architecture image is published with SBOM, provenance,
  GitHub attestation, and a keyless cosign signature.

Static checks run with `make release-check`. The complete local image drill runs
with `make release-drill`. Pull requests run both contracts in CI; version tags
repeat them before image publication.

## Black-box production-image checks

`python -m backend.release_probe` verifies a running image without importing
its application internals. It checks:

- secret-safe liveness and PostgreSQL/Redis/event-bus readiness;
- CSP, `nosniff`, referrer policy, and rejection of an untrusted CORS origin;
- anonymous denial on protected data, closed registration, and encoded
  attachment traversal rejection;
- bootstrap/restore operator authentication, authenticated reads, and matching
  released version/changelog metadata.

This is a repeatable dynamic smoke gate, not a claim of independent penetration
testing. A third-party penetration test remains recommended for larger or
regulated customers.

## Current engineering assessment

| Area | Score | Current evidence |
|---|---:|---|
| Architecture | 9/10 | Modular monolith, explicit bootstrap, Redis shared runtime, durable leased jobs. |
| Code quality | 9/10 | Cohesive domain modules, narrow adapters, no unresolved TODO/FIXME markers. |
| Readability | 9/10 | Consistent naming and rationale-focused comments. |
| Maintainability | 9/10 | Alembic path, pinned runtime, automated release/dependency contracts. |
| Security | 9/10 | Authz regressions, shared SSRF guard, upload confinement, blocking CVE and black-box gates. |
| Testing | 9/10 | Backend, CLI, browser, Redis integration, migration, failure and image drills. |
| Documentation | 9/10 | Production, backup, support, security, commercial, and release procedures. |
| DevOps | 9/10 | Non-root image, strict preflight, signed multi-arch publication, rollback guidance. |
| Performance | 9/10 | SQL hot paths, indexes, route delivery, PostgreSQL baseline, provider work off HTTP. |
| Scalability | 9/10 | PostgreSQL + Redis reference topology, multi-worker delivery and recoverable jobs. |
| UX | 9/10 | Route recovery, keyboard/focus semantics, screen-reader announcements, axe gates. |
| Innovation | 9/10 | Unified manual/automated timeline, two-way Git, durable CI control, BYOK AI. |

These scores apply to the supported dedicated-instance profile. They do not
claim shared-SaaS tenant isolation or enterprise identity provisioning.

## Known non-blocking limitations

- All authenticated users share one organization-wide visibility boundary.
  Use separate instances when parties must not see each other's data.
- SAML/SCIM and project-level object authorization are not included.
- Browser release testing is Chromium-based; Firefox and WebKit are best-effort.
- Session JWTs remain seven-day bearers with global per-user revocation rather
  than short-lived access plus per-session refresh-token rotation.
- Attachments use a persistent filesystem volume; S3-compatible storage is a
  future scale option.
- The frozen pre-Alembic bridge, ISO-string timestamps, and frontend `window`
  globals remain controlled maintenance debt.

None of these prevents a dedicated installation for one trusted organization;
they define when a later enterprise or shared-hosting phase becomes necessary.

## Evidence record

| Gate | Local candidate | Tagged release |
|---|---|---|
| Release/dependency contract | Passed: 6/6 | Pending |
| Backend + CLI tests | Passed: 836 + 69; 4 backend skipped | Pending |
| Production frontend + Playwright | Passed: build + 265 Chromium cases | Pending |
| Dependency audit | Passed: no known vulnerabilities | Pending |
| Production image and black-box probe | Passed: 11/11 before and after restore | Pending |
| v1.13 upgrade + PostgreSQL/uploads restore | Passed: `c1f6b2a34d70` → `f3a1b2c4d5e6` | Pending |
| Multi-architecture image, SBOM, attestation, signature | N/A | Pending |

Local candidate image digest:
`sha256:c1858382b8e545e7d573e3a6bd03160c08fbd542f261947c8185e2940858cdfa`.
This digest identifies the local single-architecture validation build only; it
must not be substituted for the digest published by the tag workflow.

The tagged-release column is filled only from GitHub Actions and the published
immutable image digest. A local pass cannot substitute for publication evidence.
