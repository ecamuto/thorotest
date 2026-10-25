# Support and release policy

This document describes the default, non-contractual support boundary for
ThoroTest. A signed commercial agreement or order form overrides it.

## Community use

- Questions and reproducible defects may be filed through GitHub issues.
- Assistance is best effort, with no guaranteed response or resolution time.
- Security reports must follow [SECURITY.md](SECURITY.md), never a public issue.

## Commercial support

Commercial support exists only for customers with an active written
entitlement. The order form must name the covered installations, contacts,
hours, response targets, channels, term, and exclusions. Until then, no SLA is
implied by repository activity, documentation, or issue responses.

Support covers documented deployment profiles and released artifacts. It does
not automatically cover customer-modified builds, unsupported databases,
disabled security controls, third-party provider outages, or unreviewed custom
integrations.

## Release policy

- Semantic versions identify releases; immutable container digests identify
  deployed artifacts.
- Security and defect fixes are shipped from supported release branches and
  documented in `CHANGELOG.md`.
- Upgrade notes call out configuration or schema changes. Database and uploads
  must be backed up together before every upgrade.
- Preview, unreleased, and `main` builds carry no compatibility commitment.

The exact supported-version window and any end-of-life notice period must be
specified in the first commercial order form before general availability.
