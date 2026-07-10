import { test, expect } from '@playwright/test';
import { loginAs } from '../fixtures/auth';

const BASE = 'http://localhost:8000';

test.describe('Suite 11 — Defects View & API', () => {

  // DEF-01 · Navigate to #/defects — page renders [P2]
  test('DEF-01: navigate to defects view renders without crash', async ({ page }) => {
    await loginAs(page, 'marco@acme.com');
    await page.goto('/#/defects');
    // Page title visible
    await expect(page.locator('h1:has-text("Defects")')).toBeVisible({ timeout: 10000 });
    // No JS error (page should render)
    await expect(page.locator('.page-h')).toBeVisible();
  });

  // DEF-02 · Defects table renders data [P2]
  test('DEF-02: defects table shows rows', async ({ page }) => {
    await loginAs(page, 'marco@acme.com');
    await page.goto('/#/defects');
    await expect(page.locator('h1:has-text("Defects")')).toBeVisible({ timeout: 10000 });
    // Table should have at least one row
    await expect(page.locator('table tbody tr').first()).toBeVisible({ timeout: 8000 });
  });

  // DEF-03 · API — lista defect con filtro status [P1]
  test('DEF-03: GET /api/defects?status=open returns only open defects', async ({ page }) => {
    await loginAs(page, 'marco@acme.com');
    const token = await page.evaluate(() => localStorage.getItem('th_token'));

    const res = await page.request.get(`${BASE}/api/defects?status=open`, {
      headers: { Authorization: `Bearer ${token}` },
    });
    expect(res.status()).toBe(200);
    const data = await res.json();
    expect(Array.isArray(data)).toBe(true);
    data.forEach((d: any) => {
      expect(d.status).toBe('open');
    });
  });

  // DEF-04 · API — lista defect con filtro severity [P1]
  test('DEF-04: GET /api/defects?severity=critical returns only critical', async ({ page }) => {
    await loginAs(page, 'marco@acme.com');
    const token = await page.evaluate(() => localStorage.getItem('th_token'));

    const res = await page.request.get(`${BASE}/api/defects?severity=critical`, {
      headers: { Authorization: `Bearer ${token}` },
    });
    expect(res.status()).toBe(200);
    const data = await res.json();
    data.forEach((d: any) => {
      expect(d.severity).toBe('critical');
    });
  });

  // DEF-05 · API — crea defect e recupera per ID [P1]
  test('DEF-05: POST /api/defects creates defect retrievable by GET', async ({ page }) => {
    await loginAs(page, 'marco@acme.com');
    const token = await page.evaluate(() => localStorage.getItem('th_token'));

    const created = await page.request.post(`${BASE}/api/defects`, {
      data: { title: 'E2E API defect', severity: 'high', description: 'API test' },
      headers: { Authorization: `Bearer ${token}`, 'Content-Type': 'application/json' },
    });
    expect(created.status()).toBe(201);
    const defect = await created.json();
    expect(defect.id).toMatch(/^BUG-/);
    expect(defect.status).toBe('open');
    expect(defect.severity).toBe('high');

    // Retrieve by ID
    const get = await page.request.get(`${BASE}/api/defects/${defect.id}`, {
      headers: { Authorization: `Bearer ${token}` },
    });
    expect(get.status()).toBe(200);
    const fetched = await get.json();
    expect(fetched.title).toBe('E2E API defect');

    // Cleanup
    await page.request.delete(`${BASE}/api/defects/${defect.id}`, {
      headers: { Authorization: `Bearer ${token}` },
    });
  });

  // DEF-06 · API — aggiorna status defect [P1]
  test('DEF-06: PATCH /api/defects/{id} updates status', async ({ page }) => {
    await loginAs(page, 'marco@acme.com');
    const token = await page.evaluate(() => localStorage.getItem('th_token'));

    // Create first
    const created = await page.request.post(`${BASE}/api/defects`, {
      data: { title: 'Status update test defect', severity: 'med' },
      headers: { Authorization: `Bearer ${token}`, 'Content-Type': 'application/json' },
    });
    const defect = await created.json();

    // Update status
    const updated = await page.request.patch(`${BASE}/api/defects/${defect.id}`, {
      data: { status: 'in_progress' },
      headers: { Authorization: `Bearer ${token}`, 'Content-Type': 'application/json' },
    });
    expect(updated.status()).toBe(200);
    const result = await updated.json();
    expect(result.status).toBe('in_progress');

    // Cleanup
    await page.request.delete(`${BASE}/api/defects/${defect.id}`, {
      headers: { Authorization: `Bearer ${token}` },
    });
  });

  // DEF-07 · API — elimina defect [P1]
  test('DEF-07: DELETE /api/defects/{id} removes defect', async ({ page }) => {
    await loginAs(page, 'marco@acme.com');
    const token = await page.evaluate(() => localStorage.getItem('th_token'));

    // Create
    const created = await page.request.post(`${BASE}/api/defects`, {
      data: { title: 'To be deleted defect', severity: 'low' },
      headers: { Authorization: `Bearer ${token}`, 'Content-Type': 'application/json' },
    });
    const defect = await created.json();

    // Delete
    const del = await page.request.delete(`${BASE}/api/defects/${defect.id}`, {
      headers: { Authorization: `Bearer ${token}` },
    });
    expect([200, 204]).toContain(del.status());

    // Verify gone
    const get = await page.request.get(`${BASE}/api/defects/${defect.id}`, {
      headers: { Authorization: `Bearer ${token}` },
    });
    expect(get.status()).toBe(404);
  });

  // DEF-08 · API — defect con test_id e run_id [P1]
  test('DEF-08: create defect linked to test and run', async ({ page }) => {
    await loginAs(page, 'marco@acme.com');
    const token = await page.evaluate(() => localStorage.getItem('th_token'));

    const created = await page.request.post(`${BASE}/api/defects`, {
      data: { title: 'Linked defect', severity: 'critical', test_id: 'TC-1045', run_id: 'R-1287' },
      headers: { Authorization: `Bearer ${token}`, 'Content-Type': 'application/json' },
    });
    expect(created.status()).toBe(201);
    const defect = await created.json();
    expect(defect.test_id).toBe('TC-1045');
    expect(defect.run_id).toBe('R-1287');

    // Verify appears in test's defects
    const testDefects = await page.request.get(`${BASE}/api/tests/TC-1045/defects`, {
      headers: { Authorization: `Bearer ${token}` },
    });
    expect(testDefects.status()).toBe(200);
    const list = await testDefects.json();
    expect(list.some((d: any) => d.id === defect.id)).toBe(true);

    // Cleanup
    await page.request.delete(`${BASE}/api/defects/${defect.id}`, {
      headers: { Authorization: `Bearer ${token}` },
    });
  });

  // DEF-09 · API — search defect [P1]
  test('DEF-09: GET /api/defects?search= filters by title', async ({ page }) => {
    await loginAs(page, 'marco@acme.com');
    const token = await page.evaluate(() => localStorage.getItem('th_token'));

    // Create a searchable defect
    const created = await page.request.post(`${BASE}/api/defects`, {
      data: { title: 'UNIQUE_SEARCH_TERM defect', severity: 'low' },
      headers: { Authorization: `Bearer ${token}`, 'Content-Type': 'application/json' },
    });
    const defect = await created.json();

    const res = await page.request.get(`${BASE}/api/defects?search=UNIQUE_SEARCH_TERM`, {
      headers: { Authorization: `Bearer ${token}` },
    });
    expect(res.status()).toBe(200);
    const results = await res.json();
    expect(results.some((d: any) => d.id === defect.id)).toBe(true);

    // Cleanup
    await page.request.delete(`${BASE}/api/defects/${defect.id}`, {
      headers: { Authorization: `Bearer ${token}` },
    });
  });

  // DEF-10 · UI — crea defect da TestDetail tab + vedi nella lista [P1]
  test('DEF-10: create defect via TestDetail Defects tab shows in defects list', async ({ page }) => {
    await loginAs(page, 'marco@acme.com');
    await page.goto('/#/tests/TC-2301');
    await expect(page.locator('.test-detail, [data-screen-label="test-detail"]')).toBeVisible({ timeout: 10000 });

    // Go to Defects tab
    await page.click('.tab:has-text("Defects")');
    await page.click('button:has-text("Create defect")');

    await page.fill('input[placeholder*="bug"], input[placeholder*="Describe"]', 'DEF-10 E2E defect');
    // Select severity high
    await page.selectOption('select', 'high');
    await page.click('.btn.accent:not(.sm):has-text("Create")');

    // Defect appears in list
    await expect(page.locator('text=DEF-10 E2E defect')).toBeVisible({ timeout: 8000 });

    // Cleanup via API
    const token = await page.evaluate(() => localStorage.getItem('th_token'));
    const list = await page.request.get(`${BASE}/api/tests/TC-2301/defects`, {
      headers: { Authorization: `Bearer ${token}` },
    });
    const defects = await list.json();
    const def = defects.find((d: any) => d.title === 'DEF-10 E2E defect');
    if (def) {
      await page.request.delete(`${BASE}/api/defects/${def.id}`, {
        headers: { Authorization: `Bearer ${token}` },
      });
    }
  });

  // DEF-11 · Change history modal (who/when/what) [P1]
  test('DEF-11: change history modal renders field diff', async ({ page }) => {
    await loginAs(page, 'marco@acme.com');
    const token = await page.evaluate(() => localStorage.getItem('th_token'));
    const auth = { Authorization: `Bearer ${token}`, 'Content-Type': 'application/json' };

    // Create + mutate via API so an "updated" history row exists.
    const created = await page.request.post(`${BASE}/api/defects`, {
      data: { title: 'DEF-11 history defect', severity: 'high' },
      headers: auth,
    });
    const def = await created.json();
    await page.request.patch(`${BASE}/api/defects/${def.id}`, {
      data: { status: 'resolved' },
      headers: auth,
    });

    // Open the row's history modal via the clock button.
    await page.goto('/#/defects');
    await expect(page.locator('h1:has-text("Defects")')).toBeVisible({ timeout: 10000 });
    const [response] = await Promise.all([
      page.waitForResponse(r => r.url().includes(`/api/history/defect/${def.id}`)),
      page.locator(`tr:has-text("${def.id}") button[title="Change history"]`).click(),
    ]);
    expect(response.status()).toBe(200);
    await expect(page.locator(`.app:has-text("Change history — ${def.id}")`)).toBeVisible({ timeout: 5000 });
    await expect(page.locator('.app')).toContainText('status', { timeout: 5000 });

    // Cleanup
    await page.request.delete(`${BASE}/api/defects/${def.id}`, {
      headers: { Authorization: `Bearer ${token}` },
    });
  });

});
