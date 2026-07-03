import hashlib
import secrets
import sys
import os
from .db import SessionLocal, engine
from . import models
from .auth_utils import hash_password


def _seed_token(name, scope, prefix_suffix, created_at, last_used_at=None):
    raw = "th_" + prefix_suffix + secrets.token_urlsafe(20)
    prefix = raw[:12]
    token_hash = hashlib.sha256(raw.encode()).hexdigest()
    return models.ApiToken(
        name=name, token_hash=token_hash, token_prefix=prefix,
        scope=scope, created_at=created_at, last_used_at=last_used_at,
    )


def init_db():
    """Create minimal structure for a fresh install — admin user only, no demo data."""
    db = SessionLocal()
    try:
        if db.query(models.User).count() == 0:
            db.add(models.User(
                username="admin",
                email="admin@localhost",
                hashed_password=hash_password("admin"),
                display_name="Admin",
                role="admin",
            ))
            db.commit()
    except Exception:
        db.rollback()
        raise
    finally:
        db.close()


def seed_db():
    db = SessionLocal()
    try:
        if db.query(models.User).count() == 0:
            db.add_all([
                models.User(username="marco", email="marco@acme.com", hashed_password=hash_password("demo123"), display_name="Marco Rossi", role="admin"),
                models.User(username="lisa", email="lisa@acme.com", hashed_password=hash_password("demo123"), display_name="Lisa Park", role="tester"),
                models.User(username="alex", email="alex@acme.com", hashed_password=hash_password("demo123"), display_name="Alex Rivera", role="tester"),
            ])
            db.commit()

        if db.query(models.Folder).count() > 0:
            return  # already seeded

        # Folders (parents first)
        folders = [
            models.Folder(id="auth", name="Authentication", count=24),
            models.Folder(id="checkout", name="Checkout", count=41),
            models.Folder(id="billing", name="Billing & Invoicing", count=18),
            models.Folder(id="admin", name="Admin panel", count=33),
            models.Folder(id="api", name="Public API", count=56),
            models.Folder(id="mobile", name="Mobile (iOS / Android)", count=29),
            models.Folder(id="auth-login", name="Login flows", count=9, parent_id="auth"),
            models.Folder(id="auth-sso", name="SSO / OAuth", count=7, parent_id="auth"),
            models.Folder(id="auth-mfa", name="MFA", count=8, parent_id="auth"),
            models.Folder(id="co-cart", name="Cart", count=12, parent_id="checkout"),
            models.Folder(id="co-pay", name="Payment", count=18, parent_id="checkout"),
            models.Folder(id="co-coupon", name="Coupons", count=11, parent_id="checkout"),
        ]
        db.add_all(folders)
        db.flush()

        tests = [
            models.Test(id="TC-1042", title="User can sign in with valid email + password", folder_id="auth-login", type="manual", status="pass", priority="high", owner="MR", tags=["smoke", "p0"], auto=False, updated_at="2h", last_run_at="12m", duration="1m 04s"),
            models.Test(id="TC-1043", title="Invalid password shows inline error", folder_id="auth-login", type="manual", status="pass", priority="med", owner="MR", tags=["smoke"], auto=False, updated_at="2h", last_run_at="12m", duration="00:42"),
            models.Test(id="TC-1044", title="Account lockout after 5 failed attempts", folder_id="auth-login", type="automated", status="pass", priority="high", owner="LP", tags=["security"], auto=True, runner="playwright", updated_at="1d", last_run_at="3h", duration="00:18"),
            models.Test(id="TC-1045", title="Password reset email arrives within 60s", folder_id="auth-login", type="automated", status="fail", priority="high", owner="LP", tags=["smoke", "email"], auto=True, runner="playwright", updated_at="3d", last_run_at="31m", duration="01:12"),
            models.Test(id="TC-1046", title="Google SSO redirects and creates session", folder_id="auth-sso", type="automated", status="pass", priority="high", owner="AR", tags=["oauth"], auto=True, runner="playwright", updated_at="5h", last_run_at="31m", duration="00:24"),
            models.Test(id="TC-1047", title="GitHub SSO links existing account", folder_id="auth-sso", type="manual", status="skip", priority="med", owner="AR", tags=["oauth"], auto=False, updated_at="1w", last_run_at="5d", duration="—"),
            models.Test(id="TC-1048", title="MFA TOTP code accepted within 30s window", folder_id="auth-mfa", type="automated", status="pass", priority="high", owner="AR", tags=["security"], auto=True, runner="cypress", updated_at="4d", last_run_at="31m", duration="00:33"),
            models.Test(id="TC-1049", title="MFA backup codes redeemable once", folder_id="auth-mfa", type="manual", status="warn", priority="high", owner="AR", tags=["security"], auto=False, updated_at="2d", last_run_at="2d", duration="02:10"),
            models.Test(id="TC-2210", title="Add item to cart updates header counter", folder_id="co-cart", type="automated", status="pass", priority="med", owner="MR", tags=[], auto=True, runner="cypress", updated_at="6h", last_run_at="10m", duration="00:08"),
            models.Test(id="TC-2211", title="Cart persists across page reloads (logged-in)", folder_id="co-cart", type="automated", status="pass", priority="med", owner="MR", tags=[], auto=True, runner="cypress", updated_at="6h", last_run_at="10m", duration="00:11"),
            models.Test(id="TC-2212", title="Cart persists across page reloads (guest)", folder_id="co-cart", type="automated", status="fail", priority="med", owner="MR", tags=["regression"], auto=True, runner="cypress", updated_at="1d", last_run_at="10m", duration="00:14"),
            models.Test(id="TC-2301", title="Stripe card charge succeeds on test card", folder_id="co-pay", type="automated", status="pass", priority="high", owner="LP", tags=["p0", "payment"], auto=True, runner="playwright", updated_at="3d", last_run_at="10m", duration="00:52"),
            models.Test(id="TC-2302", title="3DS challenge intercepts and completes", folder_id="co-pay", type="manual", status="warn", priority="high", owner="LP", tags=["payment"], auto=False, updated_at="1d", last_run_at="1d", duration="03:22"),
            models.Test(id="TC-2303", title="Apple Pay sheet opens on Safari iOS", folder_id="co-pay", type="manual", status="pending", priority="med", owner="AR", tags=["mobile"], auto=False, updated_at="now", last_run_at="—", duration="—"),
            models.Test(id="TC-2401", title="Percentage coupon applies before tax", folder_id="co-coupon", type="automated", status="pass", priority="med", owner="LP", tags=[], auto=True, runner="jest", updated_at="1w", last_run_at="10m", duration="00:14"),
            models.Test(id="TC-2402", title="Expired coupon shows graceful error", folder_id="co-coupon", type="automated", status="pass", priority="low", owner="LP", tags=[], auto=True, runner="jest", updated_at="1w", last_run_at="10m", duration="00:09"),
            models.Test(id="TC-3001", title="Invoice PDF renders correct line items", folder_id="billing", type="manual", status="pass", priority="high", owner="MR", tags=[], auto=False, updated_at="2d", last_run_at="2d", duration="04:30"),
        ]
        db.add_all(tests)
        db.flush()

        runs = [
            models.Run(id="R-1287", name="Release 4.2.0 — Pre-prod regression", status="running", progress=64, total=142, passed=79, failed=4, blocked=1, started="31m ago", owner="MR", env="staging", branch="release/4.2.0"),
            models.Run(id="R-1286", name="Nightly smoke — main", status="fail", progress=100, total=38, passed=35, failed=3, blocked=0, started="8h ago", owner="ci-bot", env="preview", branch="main"),
            models.Run(id="R-1285", name="Hotfix verify — payment timeout", status="pass", progress=100, total=12, passed=12, failed=0, blocked=0, started="1d ago", owner="LP", env="staging", branch="hotfix/pay-timeout"),
            models.Run(id="R-1284", name="Mobile checkout sweep (iOS 17)", status="pass", progress=100, total=24, passed=22, failed=0, blocked=2, started="1d ago", owner="AR", env="staging", branch="main"),
            models.Run(id="R-1283", name="API contract regression v2", status="fail", progress=100, total=89, passed=84, failed=5, blocked=0, started="2d ago", owner="ci-bot", env="preview", branch="main"),
            models.Run(id="R-1282", name="Manual exploratory — admin panel", status="pass", progress=100, total=8, passed=8, failed=0, blocked=0, started="3d ago", owner="MR", env="local", branch="feature/admin-bulk-edit"),
        ]
        db.add_all(runs)
        db.flush()

        run_cases = [
            # R-1287 (active)
            models.RunCase(run_id="R-1287", test_id="TC-1042", status="pass"),
            models.RunCase(run_id="R-1287", test_id="TC-1043", status="pass"),
            models.RunCase(run_id="R-1287", test_id="TC-1044", status="pass"),
            models.RunCase(run_id="R-1287", test_id="TC-1045", status="fail"),
            models.RunCase(run_id="R-1287", test_id="TC-1046", status="pass"),
            models.RunCase(run_id="R-1287", test_id="TC-1047", status="pending"),
            models.RunCase(run_id="R-1287", test_id="TC-1048", status="pass"),
            models.RunCase(run_id="R-1287", test_id="TC-1049", status="pending"),
            models.RunCase(run_id="R-1287", test_id="TC-2301", status="pass"),
            models.RunCase(run_id="R-1287", test_id="TC-2302", status="pending"),
            # R-1286 (nightly)
            models.RunCase(run_id="R-1286", test_id="TC-1042", status="pass"),
            models.RunCase(run_id="R-1286", test_id="TC-1045", status="fail"),
            models.RunCase(run_id="R-1286", test_id="TC-2212", status="fail"),
            models.RunCase(run_id="R-1286", test_id="TC-2301", status="pass"),
            # R-1285 (hotfix payment)
            models.RunCase(run_id="R-1285", test_id="TC-2301", status="pass"),
            models.RunCase(run_id="R-1285", test_id="TC-2302", status="pass"),
            models.RunCase(run_id="R-1285", test_id="TC-2401", status="pass"),
            # R-1284 (mobile checkout)
            models.RunCase(run_id="R-1284", test_id="TC-2301", status="pass"),
            models.RunCase(run_id="R-1284", test_id="TC-2303", status="pending"),
            # R-1283 (API regression)
            models.RunCase(run_id="R-1283", test_id="TC-2301", status="fail"),
            models.RunCase(run_id="R-1283", test_id="TC-1046", status="pass"),
        ]
        db.add_all(run_cases)

        pipelines = [
            models.Pipeline(id="wf-1", name="ci.yml — Pull Request checks", platform="github", status="pass", duration="4m 12s", commit="a3c9f1d", author="marco.r", branch="feature/coupon-stack", when="8m ago"),
            models.Pipeline(id="wf-2", name="nightly.yml — Full regression", platform="github", status="fail", duration="23m 04s", commit="fe21088", author="ci-bot", branch="main", when="8h ago"),
            models.Pipeline(id="wf-3", name="e2e.yml — Playwright suite", platform="github", status="pass", duration="11m 38s", commit="a3c9f1d", author="marco.r", branch="feature/coupon-stack", when="8m ago"),
            models.Pipeline(id="wf-4", name="release.gitlab-ci.yml — Staging deploy", platform="gitlab", status="running", duration="2m 41s", commit="771ab02", author="luca.p", branch="release/4.2.0", when="3m ago"),
            models.Pipeline(id="wf-5", name="Jenkinsfile — Load test", platform="jenkins", status="pass", duration="18m 22s", commit="fe21088", author="ci-bot", branch="main", when="1d ago"),
            models.Pipeline(id="wf-6", name="cypress.yml — Component tests", platform="github", status="pass", duration="3m 02s", commit="a3c9f1d", author="marco.r", branch="feature/coupon-stack", when="8m ago"),
        ]
        db.add_all(pipelines)

        activities = [
            models.Activity(who="Marco R.", what="marked", target="TC-2302", detail="as ⚠ blocked — needs 3DS test card", when="12m"),
            models.Activity(who="ci-bot", what="completed run", target="R-1286 nightly.yml", detail="3 failures in cart suite", when="8h"),
            models.Activity(who="Luca P.", what="edited", target="TC-2301", detail="added pre-condition + tag p0", when="9h"),
            models.Activity(who="Anna R.", what="created", target="TC-2303", detail="new manual test for Apple Pay iOS", when="now"),
            models.Activity(who="ThoroTest AI", what="suggested", target="3 new cases", detail="missing edge cases in coupon stacking", when="5h"),
            models.Activity(who="Marco R.", what="requested review on", target="TC-1045", detail="password reset SLA — failing intermittently", when="1d"),
        ]
        db.add_all(activities)

        defects = [
            models.Defect(id="BUG-1042", title="Password reset email not arriving within SLA (60s)", status="open", severity="high", test_id="TC-1045", run_id="R-1286", description="SMTP gateway consistently exceeds 60s SLA on staging. Started after infra migration on Apr 18.", created_at="3d", created_by="Anna Ricci"),
            models.Defect(id="BUG-0987", title="Cart doesn't persist for guest users on reload", status="in_progress", severity="med", test_id="TC-2212", run_id="R-1286", description="localStorage key mismatch between cart write and read for unauthenticated sessions.", created_at="5d", created_by="Marco Rossi"),
            models.Defect(id="BUG-1033", title="3DS challenge modal closes unexpectedly on mobile", status="open", severity="high", test_id="TC-2302", description="On Safari iOS 17, the 3DS iframe receives a postMessage from a cross-origin frame which triggers the close handler prematurely.", created_at="2d", created_by="Luca Pace"),
            models.Defect(id="BUG-0901", title="MFA backup code accepted twice on rapid submission", status="open", severity="high", test_id="TC-1049", description="Race condition in backup code invalidation — two requests in <50ms both pass validation before the first commit completes.", created_at="1w", created_by="Alex Rivera"),
            models.Defect(id="BUG-0855", title="API contract v2 — pagination cursor off by one", status="open", severity="med", run_id="R-1283", description="cursor-based pagination returns duplicate last item when page size divides total count evenly.", created_at="2w", created_by="ci-bot"),
            models.Defect(id="BUG-0820", title="Nightly: Google SSO session not invalidated on logout", status="in_progress", severity="med", test_id="TC-1046", description="Google OAuth token not revoked server-side on logout. Session cookie expires but token remains valid.", created_at="3w", created_by="Marco Rossi"),
            models.Defect(id="BUG-0799", title="Coupon stacking allows expired + valid combo", status="closed", severity="low", description="Validation order checked valid-before-expired; reversing the check fixed it.", created_at="1mo", created_by="Luca Pace"),
            models.Defect(id="BUG-0780", title="Invoice PDF — line items misaligned for >10 items", status="closed", severity="low", test_id="TC-3001", description="PDF template used fixed-height rows. Switched to dynamic height calculation.", created_at="2mo", created_by="Anna Ricci"),
        ]
        db.add_all(defects)

        comments = [
            models.Comment(test_id="TC-2301", who="Luca Pace", text="Updated the expected for step 4 — capture SLA is now 4s, not 5s. See REQ-PAY-014 v3.", when="1d"),
            models.Comment(test_id="TC-2301", who="Marco Rossi", text="@anna.r the 3DS sub-flow is split out into TC-2302. Keep this one focused on happy path on the unbranded card.", when="2d"),
            models.Comment(test_id="TC-2301", who="Anna Ricci", text="Got it, removing the 3DS step from this case.", when="2d"),
            models.Comment(test_id="TC-1045", who="Marco Rossi", text="This is flaky on CI — we see it fail ~1 in 10. Likely SMTP delay. Skipping in smoke for now.", when="3d"),
            models.Comment(test_id="TC-1045", who="Anna Ricci", text="Raised BUG-1042 — email gateway SLA needs investigation.", when="3d"),
        ]
        db.add_all(comments)

        integrations = [
            models.Integration(id="int-github", name="GitHub", type="vcs_ci", icon="github", status="active", configured_by="acme/web · main", last_sync="just now"),
            models.Integration(id="int-gitlab", name="GitLab CI", type="ci", icon="gitlab", status="active", configured_by="external runner", last_sync="3m ago"),
            models.Integration(id="int-jenkins", name="Jenkins", type="ci", icon="jenkins", status="active", configured_by="ci.acme.test", last_sync="1h ago"),
            models.Integration(id="int-playwright", name="Playwright", type="runner", icon="plug", status="active", configured_by="playwright.config.ts", last_sync="12m ago"),
            models.Integration(id="int-cypress", name="Cypress", type="runner", icon="plug", status="active", configured_by="cypress.config.js", last_sync="10m ago"),
            models.Integration(id="int-linear", name="Linear", type="defects", icon="plug", status="active", configured_by="ACME workspace", last_sync="6h ago"),
            models.Integration(id="int-slack", name="Slack", type="notifications", icon="plug", status="active", configured_by="#qa-alerts", last_sync="—"),
        ]
        db.add_all(integrations)

        api_tokens = [
            _seed_token("ci-token", "report:write, runs:read", "ci", "3d ago", "5m ago"),
            _seed_token("playwright-runner", "report:write", "pw", "1w ago", "12m ago"),
            _seed_token("claude-code-local", "tests:read", "cc", "2w ago", "1h ago"),
        ]
        db.add_all(api_tokens)

        webhooks = [
            models.Webhook(url="https://acme.slack.com/hooks/qa-alerts", events=["run.completed", "defect.created"], status="active", last_status_code=200, last_delivery_at="14m ago"),
            models.Webhook(url="https://api.linear.app/intake/thorotest", events=["defect.created"], status="active", last_status_code=200, last_delivery_at="6h ago"),
        ]
        db.add_all(webhooks)

        db.commit()
    except Exception:
        db.rollback()
        raise
    finally:
        db.close()


if __name__ == "__main__":
    # Same schema bootstrap as the app (Alembic-aware), then demo data.
    from backend.main import _ensure_schema
    _ensure_schema()
    seed_db()
    print("Demo data loaded.")
