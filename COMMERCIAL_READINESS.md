# Commercial self-host readiness

**Target release:** v1.16.0

**Launch model:** one dedicated ThoroTest installation per customer
organization, operated by the customer or by an explicitly contracted party.

This is the controlling launch checklist for Phase 3. It deliberately excludes
a shared multi-customer SaaS: project-level tenant isolation, SAML, and SCIM are
valuable enterprise work, but are not prerequisites for a dedicated instance.

The executable release gates and current engineering evidence are tracked in
[RELEASE_SIGNOFF.md](RELEASE_SIGNOFF.md).

## Product and licensing position

- The repository remains source-available under MIT plus Commons Clause; the
  controlling text is [LICENSE](LICENSE), summarized in [TERMS.md](TERMS.md).
- Internal business use and modification are allowed. Third parties may not
  sell a product or service whose value derives substantially from ThoroTest.
- ThoroTest must not be marketed as OSI open source.
- A separate commercial agreement, order form, support entitlement, SLA, DPA,
  or alternative license is effective only when explicitly signed. Nothing in
  this checklist silently creates those contractual commitments.
- Before the first paid order, legal counsel must validate the customer-facing
  license/order form and confirm ownership or compatible terms for every
  accepted external contribution.

## Supported production profile

- Immutable signed ThoroTest release image.
- PostgreSQL as the authoritative database.
- Redis required for global quotas and cross-worker realtime delivery.
- One-shot `python -m backend.bootstrap`; application workers never run DDL.
- Persistent `uploads/` storage backed up atomically with the database.
- TLS termination, explicit CORS origins, JSON logs, internal Prometheus
  metrics, SMTP, and at least one enabled durable provider worker.
- Dedicated instance boundary: all authenticated users belong to the same
  trusted customer organization. Project-level security isolation is not
  claimed in v1.16.

The environment must pass:

```bash
python -m backend.preflight --strict
```

## Customer handoff evidence

- Preflight output and immutable image digest/attestation.
- Successful bootstrap log and `/ready` response.
- Named customer administrators; open registration disabled unless contracted.
- Tested login/password-reset flow and configured sender identity.
- Backup plus restore evidence covering PostgreSQL and uploads.
- Monitoring destination for readiness, 5xx, Redis, and provider-job failures.
- Upgrade and rollback owner, maintenance window, and support contacts.
- Known-boundary acknowledgement: dedicated single-organization instance, no
  SAML/SCIM, and no object-level tenant isolation in this release.

## Engineering release gate

- Backend, CLI, frontend production build, and complete Playwright suites pass.
- Dependency CVE audit and production container build pass.
- Provider sync proves queueing, polling, crash recovery, terminal retention,
  and secret-safe errors.
- Attachment extension/MIME policy and upload/download/delete confinement pass.
- Public outbound targets are guarded; private AI targets require their narrow
  explicit opt-in.
- Database upgrade and backup/restore drills pass for the release candidate.

## Business gate outside the repository

The following require an owner decision and cannot be proven by tests:

- price, billing interval, taxes, renewal, and refund terms;
- paid support hours, response targets, escalation channel, and exclusions;
- final order form/commercial license and privacy/DPA review;
- sales ownership, customer onboarding owner, and incident communications;
- whether future Enterprise features use a separate edition or entitlement.

No release should be described as generally available for paid customers until
both the engineering gate and these named business decisions are signed off.
