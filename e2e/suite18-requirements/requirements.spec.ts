import { test, expect } from '@playwright/test';
import { loginAs } from '../fixtures/auth';

const BASE = 'http://localhost:8000';

async function token(page: any) {
  return await page.evaluate(() => localStorage.getItem('th_token'));
}

test.describe('Suite 18 — Requirements & Coverage', () => {

  // REQ-01 · Navigate to #/requirements — page renders [P2]
  test('REQ-01: requirements view renders without crash', async ({ page }) => {
    await loginAs(page, 'marco@acme.com');
    await page.goto('/#/requirements');
    await expect(page.locator('h1:has-text("Requirements")')).toBeVisible({ timeout: 10000 });
    await expect(page.locator('.page-h')).toBeVisible();
  });

  // REQ-02 · Table shows seeded requirements [P2]
  test('REQ-02: requirements table shows rows', async ({ page }) => {
    await loginAs(page, 'marco@acme.com');
    await page.goto('/#/requirements');
    await expect(page.locator('h1:has-text("Requirements")')).toBeVisible({ timeout: 10000 });
    await expect(page.locator('table tbody tr').first()).toBeVisible({ timeout: 8000 });
  });

  // REQ-03 · Nav item present in sidebar [P3]
  test('REQ-03: sidebar has a Requirements nav item', async ({ page }) => {
    await loginAs(page, 'marco@acme.com');
    await expect(page.locator('.nav-item[href="#/requirements"]')).toBeVisible({ timeout: 8000 });
  });

  // REQ-04 · API — list requirements [P1]
  test('REQ-04: GET /api/requirements returns a list', async ({ page }) => {
    await loginAs(page, 'marco@acme.com');
    const res = await page.request.get(`${BASE}/api/requirements`, {
      headers: { Authorization: `Bearer ${await token(page)}` },
    });
    expect(res.status()).toBe(200);
    const data = await res.json();
    expect(Array.isArray(data)).toBe(true);
    expect(data.length).toBeGreaterThan(0);
    expect(data[0]).toHaveProperty('coverage');
  });

  // REQ-05 · API — coverage filter [P1]
  test('REQ-05: covered=false returns only uncovered requirements', async ({ page }) => {
    await loginAs(page, 'marco@acme.com');
    const res = await page.request.get(`${BASE}/api/requirements?covered=false`, {
      headers: { Authorization: `Bearer ${await token(page)}` },
    });
    expect(res.status()).toBe(200);
    const data = await res.json();
    data.forEach((r: any) => expect(r.coverage.linked).toBe(0));
  });

  // REQ-06 · API — create, link a test, coverage reflects it, then delete [P1]
  test('REQ-06: create + link test updates coverage', async ({ page }) => {
    await loginAs(page, 'marco@acme.com');
    const auth = { Authorization: `Bearer ${await token(page)}`, 'Content-Type': 'application/json' };

    const created = await page.request.post(`${BASE}/api/requirements`, {
      data: { title: 'E2E requirement', type: 'feature' },
      headers: auth,
    });
    expect(created.status()).toBe(201);
    const req = await created.json();
    expect(req.id).toMatch(/^REQ-/);
    expect(req.coverage.linked).toBe(0);

    const linked = await page.request.post(`${BASE}/api/requirements/${req.id}/tests/TC-1042`, {
      headers: { Authorization: `Bearer ${await token(page)}` },
    });
    expect(linked.status()).toBe(200);
    expect((await linked.json()).coverage.linked).toBe(1);

    const del = await page.request.delete(`${BASE}/api/requirements/${req.id}`, {
      headers: { Authorization: `Bearer ${await token(page)}` },
    });
    expect(del.status()).toBe(204);
  });

  // REQ-07 · API — test detail requirements endpoint [P2]
  test('REQ-07: GET /api/tests/{id}/requirements returns linked requirements', async ({ page }) => {
    await loginAs(page, 'marco@acme.com');
    const res = await page.request.get(`${BASE}/api/tests/TC-2301/requirements`, {
      headers: { Authorization: `Bearer ${await token(page)}` },
    });
    expect(res.status()).toBe(200);
    const data = await res.json();
    expect(Array.isArray(data)).toBe(true);
  });

  // REQ-08 · Overview shows requirement coverage card [P2]
  test('REQ-08: overview renders requirement coverage card', async ({ page }) => {
    await loginAs(page, 'marco@acme.com');
    await page.goto('/#/overview');
    await expect(page.locator('.card-title:has-text("Requirement coverage")')).toBeVisible({ timeout: 10000 });
  });

  // REQ-09 · Test detail has a Requirements tab [P2]
  test('REQ-09: test detail exposes a Requirements tab', async ({ page }) => {
    await loginAs(page, 'marco@acme.com');
    await page.goto('/#/tests/TC-2301');
    await expect(page.locator('.tab:has-text("Requirements")')).toBeVisible({ timeout: 10000 });
    await page.locator('.tab:has-text("Requirements")').click();
    await expect(page.locator('.card-sub:has-text("Requirements this test helps verify")')).toBeVisible({ timeout: 8000 });
  });

  // REQ-10 · Edit modal shows change history for the record [P1]
  test('REQ-10: edit modal renders change history after an update', async ({ page }) => {
    await loginAs(page, 'marco@acme.com');
    const auth = { Authorization: `Bearer ${await token(page)}`, 'Content-Type': 'application/json' };

    // Create + mutate via API so a "updated" history row exists.
    const created = await page.request.post(`${BASE}/api/requirements`, {
      data: { title: 'E2E history requirement', type: 'feature', status: 'active' },
      headers: auth,
    });
    const req = await created.json();
    await page.request.patch(`${BASE}/api/requirements/${req.id}`, {
      data: { status: 'done' },
      headers: auth,
    });

    // Open the row's edit modal → history section fetches + renders.
    await page.goto('/#/requirements');
    await expect(page.locator('h1:has-text("Requirements")')).toBeVisible({ timeout: 10000 });
    const [response] = await Promise.all([
      page.waitForResponse(r => r.url().includes(`/api/history/requirement/${req.id}`)),
      page.locator(`tr:has-text("${req.id}") button[title="Edit"]`).click(),
    ]);
    expect(response.status()).toBe(200);
    await expect(page.locator('.app')).toContainText('Change history', { timeout: 5000 });
    await expect(page.locator('.app')).toContainText('status', { timeout: 5000 });

    // Cleanup
    await page.request.delete(`${BASE}/api/requirements/${req.id}`, {
      headers: { Authorization: `Bearer ${await token(page)}` },
    });
  });
});
