# Privacy Policy

_Last updated: 19 June 2026_

ThoroTest is a **self-hosted, source-available** test management platform.
This policy explains what data the project and its operators do — and do not —
collect. It is split by the way you use ThoroTest.

> This document is a good-faith template, not legal advice. Have it reviewed by
> counsel before relying on it for a production or commercial deployment.

## 1. Self-hosted software

When you download, install, and run ThoroTest on your own infrastructure:

- **We collect nothing.** The software contains **no telemetry, no analytics,
  and no phone-home behavior.**
- All data you enter — test cases, runs, results, attachments, user accounts —
  lives in **your** database (SQLite or PostgreSQL/MySQL) on **your** servers.
- You are the **data controller** for any personal data stored in your instance.
  Your own privacy obligations (e.g. GDPR, CCPA) apply to your deployment.

The only outbound network requests the software can make are ones **you
configure**, for example:

- Fetching release metadata from GitHub (changelog widget).
- OAuth sign-in with GitHub or Google, if you enable it.
- Outbound webhooks / Slack / SMTP notifications you set up.

If you do not configure these, ThoroTest makes no external calls.

## 2. The marketing website (thorotest.com)

The project website is static. It may load assets from third-party CDNs
(e.g. unpkg, Google Fonts) and query the public GitHub API to display release
information. These third parties may receive your IP address and user-agent as
part of normal HTTP requests. No analytics or tracking cookies are set by us.

## 3. Hosted offering (early access)

If you contact us to join the **hosted** waitlist, we receive the email address
you send to `hosted@thorotest.com` and any information you include in your
message. We use it only to respond to you and to inform you about the hosted
offering. We do not sell or share it. Ask us at the same address to delete it.

## 4. Your rights

For data held by **your** self-hosted instance, contact **your** administrator.
For data you sent us directly (e.g. waitlist email), contact
`hosted@thorotest.com` to access, correct, or delete it.

## 5. Changes

We may update this policy. Material changes will be reflected by the "Last
updated" date above.

## 6. Contact

Questions: `hosted@thorotest.com`.
