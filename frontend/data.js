// ThoroTest — mock data
window.TH_DATA = (function() {
  const folders = [
    { id: "auth", name: "Authentication", count: 24, children: [
      { id: "auth-login", name: "Login flows", count: 9 },
      { id: "auth-sso", name: "SSO / OAuth", count: 7 },
      { id: "auth-mfa", name: "MFA", count: 8 },
    ]},
    { id: "checkout", name: "Checkout", count: 41, children: [
      { id: "co-cart", name: "Cart", count: 12 },
      { id: "co-pay", name: "Payment", count: 18 },
      { id: "co-coupon", name: "Coupons", count: 11 },
    ]},
    { id: "billing", name: "Billing & Invoicing", count: 18 },
    { id: "admin", name: "Admin panel", count: 33 },
    { id: "api", name: "Public API", count: 56 },
    { id: "mobile", name: "Mobile (iOS / Android)", count: 29 },
  ];

  const tests = [
    { id: "TC-1042", title: "User can sign in with valid email + password", folder: "auth-login", type: "manual", status: "pass", priority: "high", owner: "MR", updated: "2h", lastRun: "12m", duration: "1m 04s", tags: ["smoke", "p0"], auto: false },
    { id: "TC-1043", title: "Invalid password shows inline error", folder: "auth-login", type: "manual", status: "pass", priority: "med", owner: "MR", updated: "2h", lastRun: "12m", duration: "00:42", tags: ["smoke"], auto: false },
    { id: "TC-1044", title: "Account lockout after 5 failed attempts", folder: "auth-login", type: "automated", status: "pass", priority: "high", owner: "LP", updated: "1d", lastRun: "3h", duration: "00:18", tags: ["security"], auto: true, runner: "playwright" },
    { id: "TC-1045", title: "Password reset email arrives within 60s", folder: "auth-login", type: "automated", status: "fail", priority: "high", owner: "LP", updated: "3d", lastRun: "31m", duration: "01:12", tags: ["smoke", "email"], auto: true, runner: "playwright" },
    { id: "TC-1046", title: "Google SSO redirects and creates session", folder: "auth-sso", type: "automated", status: "pass", priority: "high", owner: "AR", updated: "5h", lastRun: "31m", duration: "00:24", tags: ["oauth"], auto: true, runner: "playwright" },
    { id: "TC-1047", title: "GitHub SSO links existing account", folder: "auth-sso", type: "manual", status: "skip", priority: "med", owner: "AR", updated: "1w", lastRun: "5d", duration: "—", tags: ["oauth"], auto: false },
    { id: "TC-1048", title: "MFA TOTP code accepted within 30s window", folder: "auth-mfa", type: "automated", status: "pass", priority: "high", owner: "AR", updated: "4d", lastRun: "31m", duration: "00:33", tags: ["security"], auto: true, runner: "cypress" },
    { id: "TC-1049", title: "MFA backup codes redeemable once", folder: "auth-mfa", type: "manual", status: "warn", priority: "high", owner: "AR", updated: "2d", lastRun: "2d", duration: "02:10", tags: ["security"], auto: false },
    { id: "TC-2210", title: "Add item to cart updates header counter", folder: "co-cart", type: "automated", status: "pass", priority: "med", owner: "MR", updated: "6h", lastRun: "10m", duration: "00:08", tags: [], auto: true, runner: "cypress" },
    { id: "TC-2211", title: "Cart persists across page reloads (logged-in)", folder: "co-cart", type: "automated", status: "pass", priority: "med", owner: "MR", updated: "6h", lastRun: "10m", duration: "00:11", tags: [], auto: true, runner: "cypress" },
    { id: "TC-2212", title: "Cart persists across page reloads (guest)", folder: "co-cart", type: "automated", status: "fail", priority: "med", owner: "MR", updated: "1d", lastRun: "10m", duration: "00:14", tags: ["regression"], auto: true, runner: "cypress" },
    { id: "TC-2301", title: "Stripe card charge succeeds on test card", folder: "co-pay", type: "automated", status: "pass", priority: "high", owner: "LP", updated: "3d", lastRun: "10m", duration: "00:52", tags: ["p0", "payment"], auto: true, runner: "playwright" },
    { id: "TC-2302", title: "3DS challenge intercepts and completes", folder: "co-pay", type: "manual", status: "warn", priority: "high", owner: "LP", updated: "1d", lastRun: "1d", duration: "03:22", tags: ["payment"], auto: false },
    { id: "TC-2303", title: "Apple Pay sheet opens on Safari iOS", folder: "co-pay", type: "manual", status: "pending", priority: "med", owner: "AR", updated: "now", lastRun: "—", duration: "—", tags: ["mobile"], auto: false },
    { id: "TC-2401", title: "Percentage coupon applies before tax", folder: "co-coupon", type: "automated", status: "pass", priority: "med", owner: "LP", updated: "1w", lastRun: "10m", duration: "00:14", tags: [], auto: true, runner: "jest" },
    { id: "TC-2402", title: "Expired coupon shows graceful error", folder: "co-coupon", type: "automated", status: "pass", priority: "low", owner: "LP", updated: "1w", lastRun: "10m", duration: "00:09", tags: [], auto: true, runner: "jest" },
    { id: "TC-3001", title: "Invoice PDF renders correct line items", folder: "billing", type: "manual", status: "pass", priority: "high", owner: "MR", updated: "2d", lastRun: "2d", duration: "04:30", tags: [], auto: false },
  ];

  const runs = [
    { id: "R-1287", name: "Release 4.2.0 — Pre-prod regression", status: "running", progress: 64, total: 142, passed: 79, failed: 4, blocked: 1, started: "31m ago", owner: "MR", env: "staging", branch: "release/4.2.0" },
    { id: "R-1286", name: "Nightly smoke — main", status: "fail", progress: 100, total: 38, passed: 35, failed: 3, blocked: 0, started: "8h ago", owner: "ci-bot", env: "preview", branch: "main" },
    { id: "R-1285", name: "Hotfix verify — payment timeout", status: "pass", progress: 100, total: 12, passed: 12, failed: 0, blocked: 0, started: "1d ago", owner: "LP", env: "staging", branch: "hotfix/pay-timeout" },
    { id: "R-1284", name: "Mobile checkout sweep (iOS 17)", status: "pass", progress: 100, total: 24, passed: 22, failed: 0, blocked: 2, started: "1d ago", owner: "AR", env: "staging", branch: "main" },
    { id: "R-1283", name: "API contract regression v2", status: "fail", progress: 100, total: 89, passed: 84, failed: 5, blocked: 0, started: "2d ago", owner: "ci-bot", env: "preview", branch: "main" },
    { id: "R-1282", name: "Manual exploratory — admin panel", status: "pass", progress: 100, total: 8, passed: 8, failed: 0, blocked: 0, started: "3d ago", owner: "MR", env: "local", branch: "feature/admin-bulk-edit" },
  ];

  const pipelines = [
    { id: "wf-1", name: "ci.yml — Pull Request checks", platform: "github", status: "pass", duration: "4m 12s", commit: "a3c9f1d", author: "marco.r", branch: "feature/coupon-stack", when: "8m ago" },
    { id: "wf-2", name: "nightly.yml — Full regression", platform: "github", status: "fail", duration: "23m 04s", commit: "fe21088", author: "ci-bot", branch: "main", when: "8h ago" },
    { id: "wf-3", name: "e2e.yml — Playwright suite", platform: "github", status: "pass", duration: "11m 38s", commit: "a3c9f1d", author: "marco.r", branch: "feature/coupon-stack", when: "8m ago" },
    { id: "wf-4", name: "release.gitlab-ci.yml — Staging deploy", platform: "gitlab", status: "running", duration: "2m 41s", commit: "771ab02", author: "luca.p", branch: "release/4.2.0", when: "3m ago" },
    { id: "wf-5", name: "Jenkinsfile — Load test", platform: "jenkins", status: "pass", duration: "18m 22s", commit: "fe21088", author: "ci-bot", branch: "main", when: "1d ago" },
    { id: "wf-6", name: "cypress.yml — Component tests", platform: "github", status: "pass", duration: "3m 02s", commit: "a3c9f1d", author: "marco.r", branch: "feature/coupon-stack", when: "8m ago" },
  ];

  const activity = [
    { who: "Marco R.", what: "marked", target: "TC-2302", detail: "as ⚠ blocked — needs 3DS test card", when: "12m" },
    { who: "ci-bot", what: "completed run", target: "R-1286 nightly.yml", detail: "3 failures in cart suite", when: "8h" },
    { who: "Luca P.", what: "edited", target: "TC-2301", detail: "added pre-condition + tag p0", when: "9h" },
    { who: "Anna R.", what: "created", target: "TC-2303", detail: "new manual test for Apple Pay iOS", when: "now" },
    { who: "ThoroTest AI", what: "suggested", target: "3 new cases", detail: "missing edge cases in coupon stacking", when: "5h" },
    { who: "Marco R.", what: "requested review on", target: "TC-1045", detail: "password reset SLA — failing intermittently", when: "1d" },
  ];

  return { folders, tests, runs, pipelines, activity };
})();
