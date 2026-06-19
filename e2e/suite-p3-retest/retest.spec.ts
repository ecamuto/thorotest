import { test, expect, Page } from '@playwright/test';
import { loginAs } from '../fixtures/auth';

const BASE = 'http://localhost:8000';
const TESTER_EMAIL = 'tester.p3.e2e@test.com';
const TESTER_PASS = 'testerp3test123';

let testerUserId: number | null = null;
let retestRunId: string | null = null;

async function getToken(page: Page): Promise<string> {
  return page.evaluate(() => localStorage.getItem('th_token') || '');
}

async function apiJSON(
  page: Page,
  method: string,
  path: string,
  body?: unknown,
): Promise<{ status: number; body: any }> {
  const token = await getToken(page);
  const res = await page.request.fetch(`${BASE}${path}`, {
    method,
    headers: { Authorization: `Bearer ${token}`, 'Content-Type': 'application/json' },
    data: body !== undefined ? JSON.stringify(body) : undefined,
  });
  let parsed: any = null;
  try { parsed = await res.json(); } catch {}
  return { status: res.status(), body: parsed };
}

async function goToRun(page: Page, runId: string) {
  await page.evaluate((id: string) => { window.location.hash = `#/runs/${id}`; }, runId);
  await page.waitForURL(`**/#/runs/${runId}`, { timeout: 5000 });
  await page.waitForSelector('.card', { timeout: 5000 });
}

test.describe.serial('Suite P3 — Retest, Assignment & My Work', () => {

  test.beforeAll(async ({ browser }) => {
    const ctx = await browser.newContext();
    const page = await ctx.newPage();
    await loginAs(page, 'marco@acme.com');

    // Remove leftover user from prior run
    const { body: users } = await apiJSON(page, 'GET', '/api/admin/users');
    const leftover = (users as any[])?.find((u: any) => u.email === TESTER_EMAIL);
    if (leftover) await apiJSON(page, 'DELETE', `/api/admin/users/${leftover.id}`);

    // Create tester user
    const { status, body } = await apiJSON(page, 'POST', '/api/admin/users', {
      username: 'tester_p3_e2e',
      email: TESTER_EMAIL,
      password: TESTER_PASS,
      display_name: 'Tester P3 E2E',
      role: 'tester',
    });
    if (status === 201) testerUserId = body.id;

    await ctx.close();
  });

  test.afterAll(async ({ browser }) => {
    const ctx = await browser.newContext();
    const page = await ctx.newPage();
    await loginAs(page, 'marco@acme.com');

    // Unassign any cases assigned to tester_p3_e2e in R-1287
    const { body: run } = await apiJSON(page, 'GET', '/api/runs/R-1287');
    for (const c of (run as any)?.cases ?? []) {
      if (c.assigned_to === 'tester_p3_e2e') {
        await apiJSON(page, 'PATCH', `/api/runs/R-1287/cases/${c.id}`, { assigned_to: null });
      }
    }

    if (testerUserId) {
      await apiJSON(page, 'DELETE', `/api/admin/users/${testerUserId}`);
    }

    await ctx.close();
  });

  // ── Flow 1: Retest button visibility ────────────────────────────────────────

  // RETEST-01: running run → no button
  test('RETEST-01: no Retest button on running run', async ({ page }) => {
    await loginAs(page, 'marco@acme.com');
    await goToRun(page, 'R-1287');
    await expect(page.locator('button:has-text("Retest failed")')).not.toBeVisible({ timeout: 3000 });
  });

  // RETEST-02: passing run with zero failures → no button
  test('RETEST-02: no Retest button on passed run with no failures', async ({ page }) => {
    await loginAs(page, 'marco@acme.com');
    await goToRun(page, 'R-1285');
    await expect(page.locator('button:has-text("Retest failed")')).not.toBeVisible({ timeout: 3000 });
  });

  // RETEST-03: failed run with failures → button visible
  test('RETEST-03: Retest button visible on failed run with failures', async ({ page }) => {
    await loginAs(page, 'marco@acme.com');
    await goToRun(page, 'R-1286');
    await expect(page.locator('button:has-text("Retest failed")')).toBeVisible({ timeout: 5000 });
  });

  // ── Flow 2: Retest action ────────────────────────────────────────────────────

  // RETEST-04: clicking Retest navigates to new run named "Retest: …"
  test('RETEST-04: clicking Retest creates and navigates to new run', async ({ page }) => {
    await loginAs(page, 'marco@acme.com');
    await goToRun(page, 'R-1286');

    const btn = page.locator('button:has-text("Retest failed")');
    await expect(btn).toBeVisible({ timeout: 5000 });
    await btn.click();

    // Wait for navigation away from R-1286 to the new retest run
    await page.waitForURL(url => url.href.includes('/runs/') && !url.href.includes('R-1286'), { timeout: 10000 });
    const m = page.url().match(/#\/runs\/([^/?]+)/);
    retestRunId = m?.[1] ?? null;

    await expect(page.locator('text=Retest: Nightly smoke')).toBeVisible({ timeout: 5000 });
  });

  // RETEST-05: retest run header shows "Retest of:" link back to R-1286
  test('RETEST-05: retest run shows source link', async ({ page }) => {
    if (!retestRunId) test.skip();
    await loginAs(page, 'marco@acme.com');
    await goToRun(page, retestRunId!);
    await expect(page.locator('text=Retest of:')).toBeVisible({ timeout: 5000 });
  });

  // RETEST-06: "Retest of:" link navigates back to the original run
  test('RETEST-06: Retest of link navigates back to original run', async ({ page }) => {
    if (!retestRunId) test.skip();
    await loginAs(page, 'marco@acme.com');
    await goToRun(page, retestRunId!);
    // Click the anchor inside the "Retest of:" div
    await page.locator('a[href*="/runs/R-1286"]').click();
    await page.waitForURL('**/#/runs/R-1286', { timeout: 5000 });
  });

  // ── Flow 3: Assignment dropdown ──────────────────────────────────────────────

  // RETEST-07: admin sees assignment dropdown per case row
  test('RETEST-07: admin sees assignment dropdown on active run', async ({ page }) => {
    await loginAs(page, 'marco@acme.com');
    await goToRun(page, 'R-1287');
    await expect(page.locator('select.input').first()).toBeVisible({ timeout: 5000 });
  });

  // RETEST-08: selecting a user persists after navigating away and back
  test('RETEST-08: assignment persists on reload', async ({ page }) => {
    await loginAs(page, 'marco@acme.com');
    await goToRun(page, 'R-1287');

    const select = page.locator('select.input').first();
    await expect(select).toBeVisible({ timeout: 5000 });
    await select.selectOption({ label: 'Tester P3 E2E' });
    await page.waitForTimeout(500); // let PATCH settle

    // Navigate away then back
    await page.evaluate(() => { window.location.hash = '#/runs'; });
    await page.waitForURL('**/#/runs', { timeout: 3000 });
    await goToRun(page, 'R-1287');

    await expect(page.locator('select.input').first()).toHaveValue('tester_p3_e2e', { timeout: 5000 });
  });

  // RETEST-09: tester role has no assignment dropdown
  test('RETEST-09: tester cannot see assignment dropdown', async ({ page }) => {
    await loginAs(page, TESTER_EMAIL, TESTER_PASS);
    await goToRun(page, 'R-1287');
    await expect(page.locator('select.input')).not.toBeVisible({ timeout: 3000 });
  });

  // ── Flow 4: My Work page ─────────────────────────────────────────────────────

  // RETEST-10: My Work nav item visible and navigates to page
  test('RETEST-10: My Work nav item navigates to #/my-work', async ({ page }) => {
    await loginAs(page, 'marco@acme.com');
    await page.click('a.nav-item[href="#/my-work"]');
    await page.waitForURL('**/#/my-work', { timeout: 5000 });
    await expect(page.locator('h1:has-text("My work")')).toBeVisible({ timeout: 5000 });
  });

  // RETEST-11: assigned user sees their cases grouped by run
  test('RETEST-11: My Work shows assigned cases grouped by run', async ({ page }) => {
    // WS simulation may have completed R-1287 — reset to "running" so my-cases returns it
    await loginAs(page, 'marco@acme.com');
    const { body: run } = await apiJSON(page, 'GET', '/api/runs/R-1287');
    if (!['running', 'paused', 'pending'].includes((run as any)?.status)) {
      await apiJSON(page, 'PATCH', '/api/runs/R-1287/status?status=running', undefined);
    }

    await page.evaluate(() => localStorage.removeItem('th_token'));
    await loginAs(page, TESTER_EMAIL, TESTER_PASS);
    await page.evaluate(() => { window.location.hash = '#/my-work'; });
    await page.waitForURL('**/#/my-work', { timeout: 5000 });
    await expect(page.locator('h1:has-text("My work")')).toBeVisible({ timeout: 5000 });
    // R-1287 is the assigned run (from RETEST-08)
    await expect(page.locator('a').filter({ hasText: 'Release 4.2.0' }).first()).toBeVisible({ timeout: 5000 });
  });

  // RETEST-12: user with no assignments sees empty state
  test('RETEST-12: My Work shows empty state when no assignments', async ({ page }) => {
    // Admin (marco) has no assignments
    await loginAs(page, 'marco@acme.com');
    await page.evaluate(() => { window.location.hash = '#/my-work'; });
    await page.waitForURL('**/#/my-work', { timeout: 5000 });
    await expect(page.locator('h1:has-text("My work")')).toBeVisible({ timeout: 5000 });
    await expect(page.locator('text=No cases assigned')).toBeVisible({ timeout: 5000 });
  });
});
