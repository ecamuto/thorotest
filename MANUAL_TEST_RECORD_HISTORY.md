# Manual Test Plan — Record Change History

Feature: per-record audit trail (who / when / what changed) for **Tests**,
**Requirements**, **Defects**. Branch: `feat/record-history`.

Distinct from the global **AuditLog** (security events) and **Activity** (feed):
this stores field-level `old → new` diffs scoped to a single record, shown inline
in that record's detail.

---

## 0. Launch the app

Run from the repo root:

```bash
# kill any stale server on :8000
lsof -ti:8000 | xargs kill 2>/dev/null

# build frontend + fresh DB + seed + server (separate manual.db, leaves e2e.db alone)
npm run build
rm -f manual.db manual.db-shm manual.db-wal
DATABASE_URL="sqlite:///./manual.db" venv/bin/python -m backend.seed
DATABASE_URL="sqlite:///./manual.db" LOGIN_RATELIMIT_DISABLED=1 venv/bin/uvicorn backend.main:app --port 8000
```

Open http://localhost:8000

**Logins** (all password `demo123`):
- `marco@acme.com` — admin (create/edit/delete everything)
- `lisa@acme.com` — tester (create/edit, NO delete; can read history)

> `create_all` builds the `record_history` table on startup — the Alembic
> migration is not needed for manual testing. Use a fresh `manual.db` so you
> start with clean history.

---

## 1. Test — "Changes" tab

Open `#/tests/TC-2301`, click the **Changes** tab.

| #   | Action                                                        | Expected in **Changes**                                  |
| --- | ------------------------------------------------------------- | -------------------------------------------------------- |
| 1.1 | First open                                                    | Existing rows, or "No changes recorded yet"              |
| 1.2 | Change **status** (status badge → different value), reopen tab | Row `status: <old> → <new>`, your name, "just now"       |
| 1.3 | Edit **title** inline (click title → Save)                    | Row `title: <old> → <new>`                               |
| 1.4 | Change **priority** / **owner**                              | One row per changed field                                |
| 1.5 | Assign **categories** (if surfaced in UI)                    | Row `categories: — → <ids>`                              |
| 1.6 | Edit **steps** (Definition tab → add/change step → Save), reopen | Row `steps: N steps → M steps` (or `M steps (edited)` if same count) |
| 1.7 | Re-save with **no change** (same status)                    | **No** new row (no-op skipped)                           |

Tracked Test fields: `title, status, priority, owner, tags, folder_id, project_id, categories, steps`.
Not tracked: comments (separate feed), run results (separate table).

---

## 2. Requirement — edit modal

Go to `#/requirements`, click the **Edit** (gear) button on a row.

| #   | Action                                             | Expected                                           |
| --- | -------------------------------------------------- | -------------------------------------------------- |
| 2.1 | Open modal                                          | **Change history** section at the bottom           |
| 2.2 | Requirement never edited                           | "No changes recorded yet"                          |
| 2.3 | Change **status** → Save → reopen Edit             | Row `status: <old> → <new>`                        |
| 2.4 | Change **priority** + **owner** together → Save → reopen | **One** "updated" row containing **two** diffs |

---

## 3. Defect — history modal (clock button)

Go to `#/defects`.

| #   | Action                                                | Expected                                     |
| --- | ----------------------------------------------------- | -------------------------------------------- |
| 3.1 | Click the **clock** button on a row                   | Modal "Change history — BUG-xxxx"            |
| 3.2 | Untouched defect                                      | "No changes recorded yet"                    |
| 3.3 | Change **status** via the inline dropdown, reopen clock | Row `status: open → <new>`                 |

---

## 4. Edge / negative cases

| #   | Check                                                | Expected                                    |
| --- | ---------------------------------------------------- | ------------------------------------------- |
| 4.1 | Create a new test/requirement/defect                 | A **"created"** row (no diffs)              |
| 4.2 | Delete a record (as admin), then hit the history API | A **"deleted"** row is recorded (see §5 — record is gone from UI, verify via API) |
| 4.3 | Diff where old/new is empty                          | Shows `—` (struck-through) correctly        |
| 4.4 | Row order                                            | Newest at the **top**                       |
| 4.5 | Log in as `lisa@acme.com` (tester), read a record's history | 200 OK, rows visible                 |

---

## 5. Direct API check (optional)

```bash
TOKEN=$(curl -s -X POST localhost:8000/api/auth/login \
  -H 'Content-Type: application/json' \
  -d '{"email":"marco@acme.com","password":"demo123"}' \
  | python3 -c 'import sys,json;print(json.load(sys.stdin)["access_token"])')

# history for a test (also: /api/history/requirement/REQ-xxxx, /api/history/defect/BUG-xxxx)
curl -s localhost:8000/api/history/test/TC-2301 \
  -H "Authorization: Bearer $TOKEN" | python3 -m json.tool
```

Expected: JSON array, newest-first, each entry:
`{id, action, actor_name, changes: [{field, old, new}], created_at}`.

Unknown entity type → 404:
```bash
curl -s -o /dev/null -w '%{http_code}\n' localhost:8000/api/history/banana/X-1 \
  -H "Authorization: Bearer $TOKEN"   # → 404
```

---

## Automated coverage (already green, for reference)

- Unit: `backend/tests/test_record_history.py` (11 tests)
- E2E: `DET-11` (suite4), `REQ-10` (suite18), `DEF-11` (suite11)

```bash
venv/bin/python -m pytest backend/tests/test_record_history.py -q
npx playwright test -g "DET-11|REQ-10|DEF-11"
```
