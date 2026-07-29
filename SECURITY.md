# Security policy

## Reporting a vulnerability

**Please do not open a public issue for security problems.**

Report privately through GitHub:
**[Security → Report a vulnerability](https://github.com/ecamuto/thorotest/security/advisories/new)**

That opens a private advisory visible only to you and the maintainers. If the
link 404s, private reporting has not been enabled on the repository yet — open a
regular issue titled "Security contact request" with no details, and you will be
given a private channel.

### What to include

The more of this you can provide, the faster it gets fixed:

- The version (`GET /api/about`, or the `version` field in `package.json`) and
  how it is deployed (Docker, bare metal, which database).
- What an attacker gains — read access to other users' data, privilege
  escalation, remote code execution, denial of service.
- Reproduction steps. A `curl` command or a short script is ideal.
- Any relevant configuration (`ALLOW_OPEN_REGISTRATION`, whether the instance is
  internet-facing, OAuth providers in use).

### What to expect

| Stage | Target |
|---|---|
| Acknowledgement | 3 working days |
| Initial assessment and severity | 7 working days |
| Fix or documented mitigation for Critical/High | 30 days |

This is a source-available project maintained by a small team, not a funded
security programme — these are honest targets, not a contractual SLA. If a
report goes quiet for longer, please ping the advisory thread.

We will credit you in the release notes unless you ask us not to.

### Coordinated disclosure

Please give us the time above before disclosing publicly. If you plan to publish
regardless, tell us the date so we can prepare a fix and advisory for the same
day. We will not pursue legal action against anyone who reports in good faith
and follows this policy.

## Supported versions

| Version | Supported |
|---|---|
| 1.12.x | ✅ |
| < 1.12 | ❌ — upgrade to the latest minor |

Only the latest minor receives security fixes. There are no long-term support
branches.

## Scope

**In scope:** the backend API, the web frontend, the CLI, authentication and
authorization, the import pipeline, outbound integrations (GitHub, GitLab, Jira,
webhooks), and the Docker deployment as shipped in this repository.

**Out of scope:**

- Findings that require an instance to be deliberately misconfigured against the
  documented guidance — for example running with `ALLOW_INSECURE_SECRET_KEY=1`,
  `DEMO_MODE` enabled outside a demo, or `NET_GUARD_ALLOW_PRIVATE_HOSTS=1` on a
  public deployment.
- Missing hardening headers or TLS configuration on a reverse proxy you operate.
- Vulnerabilities in third-party dependencies with no exploitable path through
  ThoroTest. Dependency CVEs are tracked by `pip-audit` in CI and Dependabot;
  report them only if you can demonstrate impact here.
- Automated scanner output with no demonstrated impact.

## Known limitations

These are documented deliberately rather than reported as new findings. They are
design trade-offs at the current stage, not oversights:

- **Rate limiting is per process.** Login throttling, the AI request quota, and
  2FA attempt limits are held in memory, so running multiple workers or replicas
  multiplies each effective limit. Run a single worker, or enforce limits at a
  proxy, until shared limits land. See `docs/configuration.md`.
- **No project-level isolation.** Every authenticated user can read all tests,
  runs, defects, and requirements in the instance. Roles restrict what you can
  *change*, not what you can *see*. Do not use one instance as a boundary
  between parties who should not see each other's data.
- **`viewer` is not a confidentiality boundary.** It restricts writes; a viewer
  can still read the whole workspace and the user directory.
- **Integration credentials are stored recoverably.** GitHub, GitLab, and Jira
  tokens must be replayed to those services, so they are stored in a form the
  application can read. Database access means integration-token access.

## Deployment expectations

The application assumes the operator provides:

- A strong `SECRET_KEY` (it refuses to start otherwise) — it signs sessions and
  encrypts TOTP secrets, so treat it as a master key and rotate it if exposed.
- TLS termination. Nothing in the app requires HTTPS, but tokens travel in
  `Authorization` headers and in the WebSocket query string.
- Network placement appropriate to `ALLOW_OPEN_REGISTRATION`. With it off (the
  default), accounts are created only by an admin.

See [`docs/configuration.md`](docs/configuration.md) for the full list.
