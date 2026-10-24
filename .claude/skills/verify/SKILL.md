---
name: verify
description: Build, launch, and drive ThoroTest locally to verify changes end-to-end (backend FastAPI + static frontend + Playwright).
---

# Verify ThoroTest

## Build
- Frontend: `npm run build` (esbuild, JSX globals → `frontend/dist/`). Backend needs no build.

## Launch (isolated)
```bash
SCRATCH=<tmp dir>
DATABASE_URL="sqlite:///$SCRATCH/verify.db" ./venv/bin/python -m backend.seed   # alembic upgrade head + demo data
DATABASE_URL="sqlite:///$SCRATCH/verify.db" ./venv/bin/python -m uvicorn backend.main:app --port 8931 &
SERVER_PID=$!
```
Server serves the built frontend at `/`. Demo login: `marco@acme.com` / `demo123` (admin). Others: lisa/alex @acme.com, same password, role tester.

## Drive
- API: `POST /api/auth/login` → `access_token` → `Authorization: Bearer`.
- UI: Playwright is a devDependency. Scripts outside the repo must resolve modules via `createRequire('/path/to/repo/package.json')`. Login selectors: `input[type=email]`, `input[type=password]`, `button[type=submit]`; allow ~2.5s after login for initial-data fetch.

## AI features without a real key
Point the backend at a local OpenAI-compatible mock:
```bash
AI_PROVIDER=openai AI_MODEL=mock AI_BASE_URL=http://127.0.0.1:<mock>/v1 AI_API_KEY=x
```
Mock only needs `POST /v1/chat/completions` returning `choices[0].message.content` with the JSON payload the feature expects. Without config, AI endpoints return 503 "AI features not configured" — useful as an error-path probe.

## Gotchas
- `backend.seed` as `__main__` runs the explicit bootstrap first — good migration smoke test.
- Stop the isolated server with `kill "$SERVER_PID"`.
