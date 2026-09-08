# Configuration & commands

## Make commands

| Command | Description |
|---|---|
| `make setup` | Full setup: venv + deps + Playwright |
| `make install` | Re-install deps into existing venv |
| `make dev` | Build frontend + start backend dev server on `http://localhost:8000` (hot-reload) |
| `make frontend-build` | Build frontend to `frontend/dist/` (transpile + minify + vendor assets) |
| `make frontend-watch` | Rebuild frontend on change (run beside `make dev` when editing UI) |
| `make db-reset` | Delete `testhub.db` — re-seeded on next `make dev` |
| `make db-revision m="…"` | Create Alembic migration from model changes (autogenerate) |
| `make db-upgrade` | Apply pending Alembic migrations |
| `make db-seed` | Populate DB with demo data |
| `make demo` | Alias for `make db-seed` |
| `make test` | Run backend unit tests (pytest) |
| `make test-e2e` | Run all Playwright e2e tests (requires `make dev` running) |
| `make test-e2e-auth` | Run auth e2e suite only |
| `make test-report` | Open last Playwright HTML report |
| `make open` | Open `http://localhost:8000` in default browser |
| `make docker-up` | Build image + start app and Postgres |
| `make docker-up-sqlite` | Build image + start app with SQLite |
| `make docker-down` | Stop and remove Docker containers |
| `make docker-logs` | Tail Docker container logs |
| `make clean` | Remove venv, node_modules, DB, test artifacts |

## Environment variables

Copy `.env.example` to `.env`:

```bash
cp .env.example .env
```

| Variable | Default | Description |
|---|---|---|
| `DATABASE_URL` | `sqlite:///./testhub.db` | Database connection string |
| `REDIS_URL` | _(unset)_ | Shared runtime Redis URL. Optional only for single-process development; production Compose configures it automatically |
| `REDIS_REQUIRED` | `0` | When `1`, missing or unreachable Redis makes `/ready` return 503; use on multi-worker/replica deployments |
| `REDIS_KEY_PREFIX` | `thorotest` | Namespace for every Redis key/channel; change it when installations share one Redis database |
| `REDIS_CONNECT_TIMEOUT_SECONDS` / `REDIS_SOCKET_TIMEOUT_SECONDS` | `2` / `2` | Positive Redis connection and operation timeouts |
| `REDIS_JOB_TTL_SECONDS` | `86400` | TTL contract for ephemeral CI job state (60–2592000 seconds; consumed in V14-2) |
| `SECRET_KEY` | **required** | Signs session JWTs and encrypts stored TOTP secrets. No default — the app refuses to start without one of at least 32 characters. `install.sh` generates it; set it yourself for Docker |
| `ALLOW_INSECURE_SECRET_KEY` | _(unset)_ | Skips the `SECRET_KEY` check for a throwaway local run. **Never set this on a deployment** |
| `ALLOW_OPEN_REGISTRATION` | _(unset)_ | Allows self-registration (`POST /api/auth/register`) and OAuth first-login provisioning. Off by default; new accounts get the read-only `viewer` role |
| `TESTHUB_BASE_URL` | `http://localhost:8000` | Public base URL (OAuth callbacks, default CORS origin) |
| `ALLOWED_ORIGINS` | = `TESTHUB_BASE_URL` | CORS origins — comma-separated list, or `*` for any (dev only) |
| `LOG_LEVEL` | `INFO` | Application log level (`DEBUG`, `INFO`, `WARNING`, …) |
| `SMTP_HOST` / `SMTP_PORT` / `SMTP_USER` / `SMTP_PASS` / `SMTP_FROM` | _(unset)_ | Outbound email — password resets **and** notification email. No-op if `SMTP_HOST` absent |
| `API_TOKEN_EXPIRE_DAYS` | `90` | Lifetime of newly minted `th_…` API tokens |
| `LOGIN_MAX_FAILURES` / `LOGIN_WINDOW_SECONDS` | `10` / `300` | Failed-login throttle. Counts failures only; a success clears the counter |
| `UPLOAD_DIR` / `MAX_UPLOAD_MB` | `./uploads` / `50` | Attachment storage directory and per-file size limit |
| `DEMO_MODE` | _(unset)_ | Live-run demo simulation with fabricated results (demos only — **never in production**) |
| `ANTHROPIC_API_KEY` | _(unset)_ | Enables AI assistant (BYOK). No-op if absent |
| `AI_PROVIDER` | `anthropic` | AI backend: `anthropic` or `openai` (any OpenAI-compatible API, incl. local LLMs) |
| `AI_MODEL` | `claude-sonnet-4-6` | Model ID. Required when `AI_PROVIDER=openai` |
| `AI_BASE_URL` | `https://api.openai.com/v1` | OpenAI-compatible endpoint (e.g. `http://localhost:11434/v1` for Ollama). Setting it implies `AI_PROVIDER=openai` |
| `AI_API_KEY` | _(unset)_ | API key for the OpenAI-compatible endpoint (any value for local servers) |
| `GITHUB_CLIENT_ID` / `GITHUB_CLIENT_SECRET` | _(unset)_ | GitHub OAuth login (optional) |
| `GOOGLE_CLIENT_ID` / `GOOGLE_CLIENT_SECRET` | _(unset)_ | Google OAuth login (optional) |
| `JIRA_AUTOSYNC_MINUTES` | `0` | Auto-sync all Jira integrations every N minutes (`0` = disabled). Requires outbound reachability to Jira Cloud |

### Database URLs

**PostgreSQL is the recommended production database.** SQLite is the
out-of-the-box default for evaluation and small single-team installs: it
allows one writer at a time, so live runs, imports, and provider sync
contend under load. `make docker-up` already provisions Postgres; for a
bare-metal install, point `DATABASE_URL` at your server and the schema is
created on first boot.

```bash
# PostgreSQL — recommended for production
DATABASE_URL=postgresql://user:pass@localhost:5432/thorotest

# SQLite — default; evaluation / small installs
DATABASE_URL=sqlite:///./testhub.db

# MySQL / MariaDB
DATABASE_URL=mysql+pymysql://user:pass@localhost:3306/thorotest
```

### SECRET_KEY

`SECRET_KEY` signs every session token and derives the key that encrypts TOTP
secrets at rest. A shared or guessable value means anyone can forge an admin
session and decrypt stored 2FA secrets, so there is no default and no
placeholder — the app raises on startup if it is missing, shorter than 32
characters, or still set to the placeholder that older `.env.example` files
shipped. Generate one:

```bash
python3 -c "import secrets; print(secrets.token_hex(32))"
```

`install.sh` writes a fresh key into a newly created `.env` (and replaces an
empty or placeholder one). For Docker, set it in `.env` yourself.

### Rate limiting

Login throttling, the AI request quota, and 2FA attempt limits are enforced
**per process**. Running multiple uvicorn workers or replicas multiplies each
effective limit by the number of processes, because each keeps its own
counters — this matters most for the AI quota, which spends real API credit.
The v1.14 runtime foundation opens and health-checks one shared Redis pool;
moving these counters to it is milestone V14-1. Until V14-1 lands, run a single
worker or enforce limits at a proxy in front of the app.

### Redis and readiness

`/health` retains the existing database-health contract for compatibility.
`/ready` is the traffic-readiness probe: it checks the database and Redis when
configured. Redis reports `disabled` for an intentional single-process setup,
`missing` when `REDIS_REQUIRED=1` has no URL, and `unreachable` when a configured
server cannot be contacted. Responses never contain connection URLs or secrets.

The production Compose stack includes an internal, persistent Redis service and
sets `REDIS_REQUIRED=1`; Redis is not exposed on a host port. A custom multi-node
deployment should supply a managed `redis://` or TLS `rediss://` URL and use a
different `REDIS_KEY_PREFIX` for each ThoroTest installation sharing a database.

**Backups:** all state lives in the database plus the `uploads/` directory — see
[BACKUP.md](../BACKUP.md) for backup/restore procedures per database and for Docker deployments.

## AI assistant

Defaults to Claude — set `ANTHROPIC_API_KEY` in `.env`. The endpoint is a no-op if the key is
absent — no errors, no external calls.

Any OpenAI-compatible provider also works (OpenAI, Mistral, Groq, OpenRouter, or a local LLM via
Ollama / LM Studio / vLLM):

```bash
# Hosted example (OpenAI)
AI_PROVIDER=openai
AI_MODEL=gpt-4o
AI_API_KEY=sk-...

# Local example (Ollama)
AI_BASE_URL=http://localhost:11434/v1
AI_MODEL=llama3.1
```

Setting `AI_BASE_URL` alone selects the OpenAI-compatible provider. Small local models (<8B)
sometimes return malformed JSON — the API responds 500 in that case; prefer instruction-tuned
8B+ models.

## Theming

The tweaks panel (bottom-right gear icon) switches between dark/light and compact/comfortable
density. Persists in `localStorage`.
