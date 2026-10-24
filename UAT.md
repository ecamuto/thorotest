# UAT checklist — v1.0.0

Manual acceptance pass on a **clean machine** (or fresh clone + `make clean`).
Everything below is machine-tested already (365 pytest / 207 e2e); this pass
catches what automation can't: broken install docs, visual glitches, wrong
copy, slow feel. ~30–40 min.

Legend: each item = action → expected. Tick when it matches.

## 1. Install & boot (fresh)

- [ ] `git clone … && cd thorotest && bash install.sh` → completes without
      errors; prints frontend build + Playwright steps; `.env` created
- [ ] `make dev` → frontend builds, server starts; log shows Alembic
      `Running upgrade -> e8e566ab263b` (fresh DB path)
- [ ] `curl localhost:8000/health` → `{"status":"ok","database":"ok",…}`
- [ ] Open `http://localhost:8000` → login page < 2 s, fonts render
      (Geist, not system serif), **no requests to unpkg/googleapis** in
      devtools Network tab
- [ ] Browser console: zero errors on login page

## 2. First login & seed

- [ ] Fresh install → login `admin@localhost` / `admin` works
- [ ] `make demo` + restart → demo data present; login `marco@acme.com` /
      `demo123` lands on Overview with populated KPIs
- [ ] Overview loads < 1 s; browser console clean after navigating all
      sidebar views once

## 3. Core flows

- [ ] Library: create test via **New test** → appears in list and folder tree
- [ ] Library: search box filters server-side (type a title fragment)
- [ ] Test detail: add 2–3 steps in Definition tab, save, reload → persist
- [ ] Attachment: upload a file on a test → downloads back identical
- [ ] Run: create run from tests → run detail opens; case list present
- [ ] Run: mark cases pass/fail manually → progress bar and counters update;
      run does **NOT** auto-complete on its own (DEMO_MODE off — critical)
- [ ] Retest: completed run with failures → Retest creates follow-up run
- [ ] Defect: create from a failed case → shows in Defects view, links back
- [ ] Import: JUnit XML file → preview → execute → tests/results created
- [ ] Export: run detail → PDF export downloads and opens; library CSV too
- [ ] Insights: page renders; flaky list and folder coverage populated

## 4. Auth & security

- [ ] Logout → token invalid (back button shows login, API calls 401)
- [ ] Settings: change password → old rejected, new works
- [ ] Forgot password (no SMTP): submit email → generic "if that email
      exists" message, no error, server log shows "SMTP_HOST not configured"
- [ ] Forgot password (SMTP configured, optional): email arrives, link opens
      reset form, new password works, **old sessions logged out**
- [ ] 2FA: enable TOTP in Settings → logout → login asks for code; recovery
      code works; disable 2FA
- [ ] Roles: create `viewer` user in Admin → login as viewer → no
      create/edit buttons, Admin view inaccessible
- [ ] Wrong password 10× (fresh `.env`, rate limit on) → 429 on 11th try
- [ ] Audit log (admin): shows the logins/changes you just made

## 5. Production guards

- [ ] `.env`: set `ENVIRONMENT=production` with default SECRET_KEY →
      app **refuses to boot** with clear message; revert
- [ ] `.env`: `ENVIRONMENT=production` + `DEMO_MODE=1` + real SECRET_KEY →
      refuses to boot; revert

## 6. Docker & upgrade path

- [ ] `make docker-up` (Docker running) → both containers healthy
      (`docker compose ps`), app on :8000, login works on Postgres
- [ ] Restart app container → uploads and data survive (uploads volume)
- [ ] Upgrade path: boot a **pre-v1.0.0** database copy with v1.0.0 →
      log shows "Pre-Alembic database detected — stamping baseline"; data
      intact; second boot silent (upgrade head no-op)
- [ ] BACKUP.md: run the SQLite backup + restore procedure once, verify data

## 7. Polish sweep (subjective)

- [ ] Switch language to IT (or DE/ES/FR) → UI translates, no missing-key
      placeholders in main views
- [ ] Dark/light theme toggle persists across reload
- [ ] Resize to ~1280px width → no broken layouts in Library/Runs
- [ ] Read every string on login + overview once — typos, wrong product
      name, stale claims ("open-source" must not appear)

---

**Fail handling:** anything unticked → file it, decide blocker vs v1.0.1.
Blockers: data loss, auth bypass, fabricated results, install failure.
Everything else ships as known issue.
