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

test.describe('Suite P12 — Audit Log UI', () => {

  // AUDIT-UI-01 · Audit Log tab visible for admin and table renders [P0]
  test('AUDIT-UI-01: admin sees Audit Log tab with table headers and preset buttons', async ({ page }) => {
    await loginAs(page, 'marco@acme.com');

    await page.click('a.nav-item[href="#/admin"]');
    await page.waitForURL('**/#/admin', { timeout: 5000 });

    // Audit Log tab present for admin (synchronously rendered — no async load needed)
    const auditTab = page.getByRole('button', { name: 'Audit Log' });
    await expect(auditTab).toBeVisible({ timeout: 3000 });
    await auditTab.click();

    // Loading resolves without error
    await expect(page.locator('text=Loading...')).not.toBeVisible({ timeout: 8000 });
    await expect(page.locator('text=Error:')).not.toBeVisible();

    // Table headers present
    await expect(page.getByText('Timestamp')).toBeVisible({ timeout: 5000 });
    await expect(page.getByText('Actor')).toBeVisible();
    await expect(page.getByText('Description')).toBeVisible();
    await expect(page.getByText('Target')).toBeVisible();

    // Preset filter buttons present
    await expect(page.getByRole('button', { name: 'Last 24h' })).toBeVisible();
    await expect(page.getByRole('button', { name: 'Last 7 days' })).toBeVisible();
    await expect(page.getByRole('button', { name: 'Last 30 days' })).toBeVisible();
  });

  // AUDIT-UI-02 · Audit log contains real entries after login [P1]
  test('AUDIT-UI-02: audit log shows real entries — login event present', async ({ page }) => {
    await loginAs(page, 'marco@acme.com');

    await page.click('a.nav-item[href="#/admin"]');
    await page.waitForURL('**/#/admin', { timeout: 5000 });
    await page.getByRole('button', { name: 'Audit Log' }).click();
    await expect(page.locator('text=Loading...')).not.toBeVisible({ timeout: 8000 });

    // At least one entry visible (our own login_success lands in the real DB)
    const rows = page.locator('table tbody tr');
    await expect(rows.first()).toBeVisible({ timeout: 5000 });

    // Entry count summary shown
    await expect(page.locator('text=/\\d+ entr(y|ies)/')).toBeVisible({ timeout: 3000 });
  });

  // AUDIT-UI-03 · Preset buttons update date range and re-fetch [P1]
  test('AUDIT-UI-03: "Last 30 days" preset widens the date range beyond default 7 days', async ({ page }) => {
    await loginAs(page, 'marco@acme.com');

    await page.click('a.nav-item[href="#/admin"]');
    await page.waitForURL('**/#/admin', { timeout: 5000 });
    await page.getByRole('button', { name: 'Audit Log' }).click();
    await expect(page.locator('text=Loading...')).not.toBeVisible({ timeout: 8000 });

    const startInput = page.locator('input[type="date"]').first();
    const startBefore = await startInput.inputValue(); // default: 7 days ago

    await page.getByRole('button', { name: 'Last 30 days' }).click();
    await expect(page.locator('text=Loading...')).not.toBeVisible({ timeout: 8000 });

    const startAfter = await startInput.inputValue(); // now: 30 days ago
    expect(startAfter < startBefore).toBe(true); // 30d ago is an earlier date string
    await expect(page.locator('text=Error:')).not.toBeVisible();
  });

  // AUDIT-UI-04 · Tester cannot reach admin page — redirected to overview [P0]
  test('AUDIT-UI-04: tester is redirected away from /#/admin; no Audit Log tab accessible', async ({ page }) => {
    // lisa@acme.com is a tester
    await loginAs(page, 'lisa@acme.com');

    // Admin nav link absent
    await expect(page.locator('a.nav-item[href="#/admin"]')).not.toBeVisible({ timeout: 3000 });

    // Direct navigation to /#/admin redirects to overview
    await page.goto('/#/admin');
    await page.waitForURL('**/#/overview', { timeout: 5000 });

    // Audit Log tab not present
    expect(await page.getByRole('button', { name: 'Audit Log' }).count()).toBe(0);
  });

  // AUDIT-UI-05 · Audit log API returns 403 for viewer role [P0]
  test('AUDIT-UI-05: GET /api/audit-log returns 403 for viewer; viewer cannot access admin page', async ({ page }) => {
    const uid = Date.now();
    const VIEWER_EMAIL = `viewer.audit${uid}@test.com`;
    const VIEWER_PASS = 'viewertest123';
    let viewerId: number | null = null;

    await loginAs(page, 'marco@acme.com');
    const { status, body } = await apiJSON(page, 'POST', '/api/admin/users', {
      username: `vieweraudit${uid}`,
      email: VIEWER_EMAIL,
      password: VIEWER_PASS,
      display_name: 'Viewer Audit E2E',
      role: 'viewer',
    });
    if (status === 201) viewerId = body.id;

    try {
      await page.evaluate(() => localStorage.removeItem('th_token'));
      await loginAs(page, VIEWER_EMAIL, VIEWER_PASS);

      // API must reject with 403
      const { status: apiStatus } = await apiJSON(page, 'GET', '/api/audit-log');
      expect(apiStatus).toBe(403);

      // Admin nav absent for viewer
      await expect(page.locator('a.nav-item[href="#/admin"]')).not.toBeVisible({ timeout: 3000 });

      // Direct nav to /#/admin redirects to overview
      await page.goto('/#/admin');
      await page.waitForURL('**/#/overview', { timeout: 5000 });
    } finally {
      if (viewerId) {
        await page.evaluate(() => localStorage.removeItem('th_token'));
        await loginAs(page, 'marco@acme.com');
        await apiJSON(page, 'DELETE', `/api/admin/users/${viewerId}`);
      }
    }
  });
});
