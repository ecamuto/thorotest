import { test, expect, Page } from '@playwright/test';
import { loginAs } from '../fixtures/auth';

const BASE = 'http://localhost:8000';

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

const VIEWER_EMAIL = 'viewer.e2e@test.com';
const VIEWER_PASS = 'viewertest123';
let viewerUserId: number | null = null;

test.describe('Suite P2 — RBAC (Roles & Permissions)', () => {

  test.beforeAll(async ({ browser }) => {
    const ctx = await browser.newContext();
    const page = await ctx.newPage();
    await loginAs(page, 'marco@acme.com');

    // Clean up leftover from prior run
    const { body: users } = await apiJSON(page, 'GET', '/api/admin/users');
    const leftover = (users as any[])?.find((u: any) => u.email === VIEWER_EMAIL);
    if (leftover) await apiJSON(page, 'DELETE', `/api/admin/users/${leftover.id}`);

    // Create viewer user for role-gated UI tests
    const { status, body } = await apiJSON(page, 'POST', '/api/admin/users', {
      username: 'viewer_e2e',
      email: VIEWER_EMAIL,
      password: VIEWER_PASS,
      display_name: 'Viewer E2E',
      role: 'viewer',
    });
    if (status === 201) viewerUserId = body.id;

    await ctx.close();
  });

  test.afterAll(async ({ browser }) => {
    if (!viewerUserId) return;
    const ctx = await browser.newContext();
    const page = await ctx.newPage();
    await loginAs(page, 'marco@acme.com');
    await apiJSON(page, 'DELETE', `/api/admin/users/${viewerUserId}`);
    await ctx.close();
  });

  // RBAC-01 · Admin nav item visibility [P0]
  test('RBAC-01: admin sidebar item visible for admin, hidden for tester', async ({ page }) => {
    await loginAs(page, 'marco@acme.com');
    await expect(page.locator('a.nav-item[href="#/admin"]')).toBeVisible({ timeout: 5000 });

    await page.evaluate(() => localStorage.removeItem('th_token'));
    await loginAs(page, 'lisa@acme.com');
    await expect(page.locator('a.nav-item[href="#/admin"]')).not.toBeVisible({ timeout: 3000 });
  });

  // RBAC-02 · Admin page loads with user table [P0]
  test('RBAC-02: admin accesses /admin page with user table', async ({ page }) => {
    await loginAs(page, 'marco@acme.com');

    await page.click('a.nav-item[href="#/admin"]');
    await page.waitForURL('**/#/admin', { timeout: 5000 });

    await expect(page.getByText('User Management')).toBeVisible({ timeout: 5000 });
    await expect(page.getByText('marco@acme.com')).toBeVisible({ timeout: 5000 });
    await expect(page.getByText('lisa@acme.com')).toBeVisible();
  });

  // RBAC-03 · Role change via dropdown (PATCH round-trip) [P0]
  test('RBAC-03: admin changes user role via dropdown', async ({ page }) => {
    if (!viewerUserId) test.skip(true, 'viewer user not created in beforeAll');

    await loginAs(page, 'marco@acme.com');
    await page.click('a.nav-item[href="#/admin"]');
    await page.waitForURL('**/#/admin', { timeout: 5000 });
    await expect(page.getByText(VIEWER_EMAIL)).toBeVisible({ timeout: 5000 });

    const viewerRow = page.locator('tr').filter({ hasText: VIEWER_EMAIL });
    const roleSelect = viewerRow.locator('select');

    await roleSelect.selectOption('manager');
    await page.waitForTimeout(600);

    const { body: after } = await apiJSON(page, 'GET', '/api/admin/users');
    const updated = (after as any[]).find((u: any) => u.email === VIEWER_EMAIL);
    expect(updated?.role).toBe('manager');

    // Restore
    await roleSelect.selectOption('viewer');
    await page.waitForTimeout(600);
    const { body: restored } = await apiJSON(page, 'GET', '/api/admin/users');
    expect((restored as any[]).find((u: any) => u.email === VIEWER_EMAIL)?.role).toBe('viewer');
  });

  // RBAC-04 · Create user via form [P1]
  test('RBAC-04: admin creates new user via new-user form', async ({ page }) => {
    await loginAs(page, 'marco@acme.com');
    await page.click('a.nav-item[href="#/admin"]');
    await page.waitForURL('**/#/admin', { timeout: 5000 });

    await page.click('button:has-text("New user"), button:has-text("Nuovo utente")');
    await expect(page.locator('input[placeholder="Username *"]')).toBeVisible({ timeout: 3000 });

    const uid = Date.now();
    const tmpEmail = `tmp${uid}@test.com`;

    await page.fill('input[placeholder="Username *"]', `tmpuser${uid}`);
    await page.fill('input[placeholder="Email *"]', tmpEmail);
    await page.fill('input[placeholder="Password *"]', 'tmppass123-long');
    await page.fill('input[placeholder="Display name"], input[placeholder="Nome visualizzato"]', 'Tmp User');
    await page.locator('form select').selectOption('viewer');
    await page.click('button[type="submit"]:has-text("Crea utente")');

    await expect(page.getByText(tmpEmail)).toBeVisible({ timeout: 5000 });

    // Cleanup
    const { body } = await apiJSON(page, 'GET', '/api/admin/users');
    const created = (body as any[]).find((u: any) => u.email === tmpEmail);
    if (created) await apiJSON(page, 'DELETE', `/api/admin/users/${created.id}`);
  });

  // RBAC-05 · Delete user; self-delete button absent [P1]
  test('RBAC-05: admin deletes a user; own row has no delete button', async ({ page }) => {
    await loginAs(page, 'marco@acme.com');

    const uid = Date.now();
    const tmpEmail = `todel${uid}@test.com`;
    await apiJSON(page, 'POST', '/api/admin/users', {
      username: `todel${uid}`,
      email: tmpEmail,
      password: 'test123-long-pw',
      display_name: 'To Delete',
      role: 'tester',
    });

    await page.click('a.nav-item[href="#/admin"]');
    await page.waitForURL('**/#/admin', { timeout: 5000 });
    await expect(page.getByText(tmpEmail)).toBeVisible({ timeout: 5000 });

    page.on('dialog', (d) => d.accept());
    const targetRow = page.locator('tr').filter({ hasText: tmpEmail });
    await targetRow.getByRole('button', { name: /Elimina|Delete/ }).click();
    await expect(page.getByText(tmpEmail)).not.toBeVisible({ timeout: 5000 });

    // Admin's own row has no delete button
    const marcoRow = page.locator('tr').filter({ hasText: 'marco@acme.com' });
    expect(await marcoRow.getByRole('button', { name: /Elimina|Delete/ }).count()).toBe(0);
  });

  // RBAC-06 · Tester UI in Library [P0]
  test('RBAC-06: tester sees "New test" in Library but no Delete buttons', async ({ page }) => {
    await loginAs(page, 'lisa@acme.com');
    await page.click('.nav-item:has-text("Test library"), .nav-item:has-text("Libreria test")');
    await page.waitForURL('**/#/library', { timeout: 5000 });
    await expect(page.locator('.table tr td.mono').first()).toBeVisible({ timeout: 10000 });

    await expect(page.locator('button:has-text("New test"), button:has-text("Nuovo test")')).toBeVisible({ timeout: 5000 });
    expect(await page.locator('button[title="Delete test"]').count()).toBe(0);
  });

  // RBAC-07 · Viewer sees no write UI in Library and Runs [P0]
  test('RBAC-07: viewer sees no write UI in Library and Runs', async ({ page }) => {
    if (!viewerUserId) test.skip(true, 'viewer user not created in beforeAll');

    await loginAs(page, VIEWER_EMAIL, VIEWER_PASS);

    await page.click('.nav-item:has-text("Test library"), .nav-item:has-text("Libreria test")');
    await page.waitForURL('**/#/library', { timeout: 5000 });
    await expect(page.locator('.table tr td.mono').first()).toBeVisible({ timeout: 10000 });

    expect(await page.locator('button:has-text("New test"), button:has-text("Nuovo test")').count()).toBe(0);
    expect(await page.locator('button[title="Delete test"]').count()).toBe(0);

    // Select a row to trigger bulk toolbar, then verify write actions are hidden
    await page.locator('.table tbody tr').first().locator('input[type="checkbox"]').check().catch(() => {});
    await page.waitForTimeout(300);
    expect(await page.locator('button:has-text("Add to run")').count()).toBe(0);
    expect(await page.locator('button:has-text("Move to folder")').count()).toBe(0);
    expect(await page.locator('button:has-text("Set status")').count()).toBe(0);

    await page.click('.nav-item:has-text("Runs"), .nav-item:has-text("Esecuzioni")');
    await page.waitForURL('**/#/runs', { timeout: 5000 });
    await page.waitForTimeout(600);
    expect(await page.locator('button:has-text("Start run"), button:has-text("Avvia run")').count()).toBe(0);
  });

  // RBAC-08 · Non-admin blocked from /admin with toast [P0]
  test('RBAC-08: non-admin navigating to #/admin shows toast and redirects to overview', async ({ page }) => {
    await loginAs(page, 'lisa@acme.com');
    await page.waitForURL('**/#/overview', { timeout: 5000 });

    // Trigger hashchange to #/admin (simulates typing in address bar)
    await page.evaluate(() => { window.location.hash = '#/admin'; });

    await expect(page.getByText('Admin access required')).toBeVisible({ timeout: 5000 });
    await expect(page).toHaveURL(/\#\/overview/, { timeout: 3000 });
    expect(await page.getByText('User Management').count()).toBe(0);
  });

  // RBAC-08b · Direct page load to #/admin as non-admin [P0]
  test('RBAC-08b: direct page load to #/admin as non-admin redirects to overview with toast', async ({ browser }) => {
    // Fresh context simulates opening URL in new tab / pasting in address bar
    const ctx = await browser.newContext();
    const page = await ctx.newPage();

    // Authenticate first (set token in localStorage), then load with #/admin hash
    await loginAs(page, 'lisa@acme.com');
    const token = await getToken(page);

    // New page in same context loads with #/admin already in URL
    const page2 = await ctx.newPage();
    await page2.addInitScript((tok) => {
      localStorage.setItem('th_token', tok);
    }, token);
    await page2.goto('/#/admin');

    await expect(page2.getByText('Admin access required')).toBeVisible({ timeout: 8000 });
    expect(await page2.getByText('User Management').count()).toBe(0);

    await ctx.close();
  });

  // RBAC-09 · API enforcement — viewer gets 403 on write [P0]
  test('RBAC-09: viewer token → 403 on POST /api/tests', async ({ page }) => {
    if (!viewerUserId) test.skip(true, 'viewer user not created in beforeAll');

    await loginAs(page, VIEWER_EMAIL, VIEWER_PASS);
    const { status } = await apiJSON(page, 'POST', '/api/tests', {
      title: 'RBAC viewer write attempt',
      type: 'manual',
      status: 'pending',
      priority: 'med',
    });
    expect(status).toBe(403);
  });

});
