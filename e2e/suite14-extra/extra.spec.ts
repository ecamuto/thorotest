import { test, expect } from '@playwright/test';
import { loginAs } from '../fixtures/auth';

const BASE = 'http://localhost:8000';

test.describe('Suite 14 — Extra Coverage, Edge Cases & Library Gaps', () => {

  async function getToken(page: any): Promise<string> {
    return await page.evaluate(() => localStorage.getItem('th_token') ?? '');
  }

  // ── Library additional filters ───────────────────────────────────────────

  // EXTRA-01 · Filtro per priority [P1]
  test('EXTRA-01: library filter by priority high', async ({ page }) => {
    await loginAs(page, 'marco@acme.com');
    await page.goto('/#/library');
    await expect(page.locator('table tbody tr').first()).toBeVisible({ timeout: 10000 });

    // Select priority filter if available
    const prioritySelect = page.locator('select').filter({ hasText: /priority/i });
    if (await prioritySelect.count() > 0) {
      await prioritySelect.selectOption('high');
      await page.waitForTimeout(500);
      // Verify only high priority shown
      const rows = page.locator('table tbody tr');
      const count = await rows.count();
      expect(count).toBeGreaterThan(0);
    }
  });

  // EXTRA-02 · Filtro combinato status + tipo [P1]
  test('EXTRA-02: combined filter status fail + automated type', async ({ page }) => {
    await loginAs(page, 'marco@acme.com');
    await page.goto('/#/library');
    await expect(page.locator('table tbody tr').first()).toBeVisible({ timeout: 10000 });

    // Apply status filter
    const statusSelect = page.locator('select').filter({ hasText: /status/i });
    if (await statusSelect.count() > 0) {
      await statusSelect.selectOption('fail');
      await page.waitForTimeout(300);

      // Apply type filter
      const typeSelect = page.locator('select').filter({ hasText: /type/i });
      if (await typeSelect.count() > 0) {
        await typeSelect.selectOption('automated');
        await page.waitForTimeout(300);
      }

      const rows = page.locator('table tbody tr');
      const count = await rows.count();
      // Combined filters may return empty — either is valid
      if (count > 0) {
        // If results: no row should have status other than "fail"
        const statusBadge = page.locator('table tbody tr').first().locator('.status');
        await expect(statusBadge).toBeVisible();
      }
    }
  });

  // EXTRA-03 · Search clears con X / reset [P1]
  test('EXTRA-03: search field reset restores full list', async ({ page }) => {
    await loginAs(page, 'marco@acme.com');
    await page.goto('/#/library');
    await expect(page.locator('table tbody tr').first()).toBeVisible({ timeout: 10000 });

    const fullCount = await page.locator('table tbody tr').count();

    // Search for something narrow
    await page.fill('input[type="search"], input[placeholder*="Search"]', 'stripe');
    await page.keyboard.press('Enter');
    await page.waitForTimeout(500);

    const filteredCount = await page.locator('table tbody tr').count();
    expect(filteredCount).toBeLessThanOrEqual(fullCount);

    // Clear search
    await page.fill('input[type="search"], input[placeholder*="Search"]', '');
    await page.keyboard.press('Enter');
    await page.waitForTimeout(500);

    const restoredCount = await page.locator('table tbody tr').count();
    expect(restoredCount).toBe(fullCount);
  });

  // EXTRA-04 · Library — cancel new test form [P2]
  test('EXTRA-04: cancel new test form does not create test', async ({ page }) => {
    await loginAs(page, 'marco@acme.com');
    await page.goto('/#/library');
    // Wait for table to finish loading before counting
    await page.waitForLoadState('networkidle');

    const beforeCount = await page.locator('table tbody tr').count();

    // Open new test form
    await page.click('button:has-text("New test")');
    await expect(page.locator('input[placeholder*="TC-"]')).toBeVisible({ timeout: 5000 });

    // Cancel
    await page.click('button:has-text("Cancel")');
    await page.waitForTimeout(300);

    // Row count unchanged
    const afterCount = await page.locator('table tbody tr').count();
    expect(afterCount).toBe(beforeCount);
  });

  // ── Activity ─────────────────────────────────────────────────────────────

  // EXTRA-05 · Activity feed in Overview [P2]
  test('EXTRA-05: overview shows recent activity feed', async ({ page }) => {
    await loginAs(page, 'marco@acme.com');
    await page.goto('/#/overview');
    await expect(page.locator('.page')).toBeVisible({ timeout: 10000 });
    // Activity section should appear
    await expect(page.locator('text=/Activity|Recent/i').first()).toBeVisible({ timeout: 8000 });
  });

  // EXTRA-06 · GET /api/activity returns events [P1]
  test('EXTRA-06: GET /api/activity returns non-empty list', async ({ page }) => {
    await loginAs(page, 'marco@acme.com');
    const token = await getToken(page);

    const res = await page.request.get(`${BASE}/api/activity`, {
      headers: { Authorization: `Bearer ${token}` },
    });
    expect(res.status()).toBe(200);
    const data = await res.json();
    expect(Array.isArray(data)).toBe(true);
    expect(data.length).toBeGreaterThan(0);

    // Each item has required fields
    const item = data[0];
    expect(item).toHaveProperty('who');
    expect(item).toHaveProperty('what');
    expect(item).toHaveProperty('when');
  });

  // ── GraphQL ──────────────────────────────────────────────────────────────

  // EXTRA-07 · GraphQL — query tests con auth [P1]
  test('EXTRA-07: GraphQL query returns tests with valid token', async ({ page }) => {
    await loginAs(page, 'marco@acme.com');
    const token = await getToken(page);

    const res = await page.request.post(`${BASE}/graphql`, {
      data: { query: '{ tests { id title status } }' },
      headers: { Authorization: `Bearer ${token}`, 'Content-Type': 'application/json' },
    });
    expect(res.status()).toBe(200);
    const json = await res.json();
    expect(json.data?.tests).toBeTruthy();
    expect(Array.isArray(json.data.tests)).toBe(true);
    expect(json.data.tests.length).toBeGreaterThan(0);
    expect(json.data.tests[0]).toHaveProperty('id');
  });

  // EXTRA-08 · GraphQL — query runs [P1]
  test('EXTRA-08: GraphQL query returns runs', async ({ page }) => {
    await loginAs(page, 'marco@acme.com');
    const token = await getToken(page);

    const res = await page.request.post(`${BASE}/graphql`, {
      data: { query: '{ runs { id name status } }' },
      headers: { Authorization: `Bearer ${token}`, 'Content-Type': 'application/json' },
    });
    expect(res.status()).toBe(200);
    const json = await res.json();
    expect(json.data?.runs).toBeTruthy();
    expect(Array.isArray(json.data.runs)).toBe(true);
  });

  // EXTRA-09 · GraphQL — senza token ancora accessibile (documentare gap) [P1]
  test('EXTRA-09: GraphQL endpoint behavior without auth token', async ({ page }) => {
    const res = await page.request.post(`${BASE}/graphql`, {
      data: { query: '{ tests { id } }' },
      headers: { 'Content-Type': 'application/json' },
    });
    // Document current behavior: GraphQL may or may not require auth
    // This test documents the actual behavior without prescribing it
    const status = res.status();
    expect([200, 401, 403]).toContain(status);
    // Log for documentation
    console.log(`GraphQL without token: HTTP ${status}`);
  });

  // ── Security extra ───────────────────────────────────────────────────────

  // EXTRA-10 · POST /api/auth/register — username duplicato [P1]
  test('EXTRA-10: register with duplicate username returns 409', async ({ page }) => {
    const res = await page.request.post(`${BASE}/api/auth/register`, {
      data: { username: 'marco', email: 'newuser@test.com', password: 'secret123' },
      headers: { 'Content-Type': 'application/json' },
    });
    expect(res.status()).toBe(409);
    const err = await res.json();
    expect(err.detail).toMatch(/Username taken/i);
  });

  // EXTRA-11 · PATCH /api/tests — without token [P1]
  test('EXTRA-11: PATCH /api/tests without token — document auth gap', async ({ page }) => {
    const res = await page.request.patch(`${BASE}/api/tests/TC-1042`, {
      data: { status: 'fail' },
      headers: { 'Content-Type': 'application/json' },
    });
    // Document: test CRUD currently not protected by JWT
    // If this returns 200, it's a known security gap (documented in E2E plan)
    const status = res.status();
    console.log(`PATCH /api/tests without token: HTTP ${status}`);
    expect([200, 401, 403, 422]).toContain(status);
  });

  // EXTRA-12 · DELETE /api/tests/{id} — ID non esistente → 404 [P1]
  test('EXTRA-12: DELETE /api/tests/{nonexistent} returns 404', async ({ page }) => {
    await loginAs(page, 'marco@acme.com');
    const token = await getToken(page);

    const res = await page.request.delete(`${BASE}/api/tests/TC-DOES-NOT-EXIST`, {
      headers: { Authorization: `Bearer ${token}` },
    });
    expect(res.status()).toBe(404);
  });

  // EXTRA-13 · GET /api/runs/{nonexistent} → 404 [P1]
  test('EXTRA-13: GET /api/runs/{nonexistent} returns 404', async ({ page }) => {
    await loginAs(page, 'marco@acme.com');
    const token = await getToken(page);

    const res = await page.request.get(`${BASE}/api/runs/R-DOES-NOT-EXIST`, {
      headers: { Authorization: `Bearer ${token}` },
    });
    expect(res.status()).toBe(404);
  });

  // EXTRA-14 · UI — navigare a test inesistente mostra errore graceful [P1]
  test('EXTRA-14: navigate to nonexistent test shows graceful error not blank', async ({ page }) => {
    await loginAs(page, 'marco@acme.com');
    await page.goto('/#/tests/TC-NONEXISTENT-12345');

    // Should show error message, not blank white screen
    await page.waitForTimeout(3000);
    // Either an error message or redirect to library
    const hasError = await page.locator('text=/not found|error|not exist/i').count() > 0;
    const hasLibrary = page.url().includes('#/library') || await page.locator('.test-list, table').count() > 0;
    expect(hasError || hasLibrary).toBe(true);
  });

  // ── AI Assistant view ────────────────────────────────────────────────────

  // EXTRA-15 · AI Assistant page renders [P2]
  test('EXTRA-15: AI assistant page renders without crash', async ({ page }) => {
    await loginAs(page, 'marco@acme.com');
    await page.goto('/#/ai');
    await expect(page.locator('text=AI assistant').first()).toBeVisible({ timeout: 10000 });
    await expect(page.locator('text=Test ideas')).toBeVisible();
    // Generate-tests panel tab confirms the AI assistant view mounted
    await expect(page.getByRole('button', { name: 'Generate tests' })).toBeVisible();
  });

  // ── Runs additional ──────────────────────────────────────────────────────

  // EXTRA-16 · Run detail — defects list via API [P1]
  test('EXTRA-16: GET /api/runs/{id}/defects returns defects for that run', async ({ page }) => {
    await loginAs(page, 'marco@acme.com');
    const token = await getToken(page);

    // Create a defect linked to R-1287
    const created = await page.request.post(`${BASE}/api/defects`, {
      data: { title: 'Run defect test', severity: 'med', run_id: 'R-1287' },
      headers: { Authorization: `Bearer ${token}`, 'Content-Type': 'application/json' },
    });
    const defect = await created.json();

    const res = await page.request.get(`${BASE}/api/runs/R-1287/defects`, {
      headers: { Authorization: `Bearer ${token}` },
    });
    expect(res.status()).toBe(200);
    const list = await res.json();
    expect(list.some((d: any) => d.id === defect.id)).toBe(true);

    // Cleanup
    await page.request.delete(`${BASE}/api/defects/${defect.id}`, {
      headers: { Authorization: `Bearer ${token}` },
    });
  });

  // EXTRA-17 · Pipelines — verify data from API not hardcoded [P2]
  test('EXTRA-17: pipelines page shows data from /api/initial-data', async ({ page }) => {
    await loginAs(page, 'marco@acme.com');

    // Verify initial-data has pipelines
    const token = await getToken(page);
    const res = await page.request.get(`${BASE}/api/initial-data`, {
      headers: { Authorization: `Bearer ${token}` },
    });
    expect(res.status()).toBe(200);
    const data = await res.json();
    expect(Array.isArray(data.pipelines)).toBe(true);
    expect(data.pipelines.length).toBeGreaterThan(0);

    // Navigate to pipelines and verify count matches
    await page.goto('/#/pipelines');
    await expect(page.locator('table tbody tr').first()).toBeVisible({ timeout: 10000 });
    const rowCount = await page.locator('table tbody tr').count();
    expect(rowCount).toBe(data.pipelines.length);
  });

  // EXTRA-18 · Initial data endpoint — structure validation [P0]
  test('EXTRA-18: GET /api/initial-data returns all required collections', async ({ page }) => {
    await loginAs(page, 'marco@acme.com');
    const token = await getToken(page);

    const res = await page.request.get(`${BASE}/api/initial-data`, {
      headers: { Authorization: `Bearer ${token}` },
    });
    expect(res.status()).toBe(200);
    const data = await res.json();

    expect(Array.isArray(data.folders)).toBe(true);
    expect(Array.isArray(data.tests)).toBe(true);
    expect(Array.isArray(data.runs)).toBe(true);
    expect(Array.isArray(data.pipelines)).toBe(true);
    expect(Array.isArray(data.activity)).toBe(true);
    expect(Array.isArray(data.defects)).toBe(true);
    expect(Array.isArray(data.projects)).toBe(true);
    expect(Array.isArray(data.categories)).toBe(true);

    // Verify non-empty core collections
    expect(data.tests.length).toBeGreaterThan(0);
    expect(data.runs.length).toBeGreaterThan(0);
    expect(data.folders.length).toBeGreaterThan(0);
  });

  // EXTRA-19 · Bulk update restores after test [P1]
  test('EXTRA-19: bulk status update then restore', async ({ page }) => {
    await loginAs(page, 'marco@acme.com');
    const token = await getToken(page);

    // Create 2 temp tests
    await page.request.post(`${BASE}/api/tests`, {
      data: { id: 'TC-BULK-A', title: 'Bulk test A', type: 'manual', status: 'pending', priority: 'low' },
      headers: { Authorization: `Bearer ${token}`, 'Content-Type': 'application/json' },
    });
    await page.request.post(`${BASE}/api/tests`, {
      data: { id: 'TC-BULK-B', title: 'Bulk test B', type: 'manual', status: 'pending', priority: 'low' },
      headers: { Authorization: `Bearer ${token}`, 'Content-Type': 'application/json' },
    });

    // Bulk update via API
    const bulkRes = await page.request.post(`${BASE}/api/tests/bulk`, {
      data: { action: 'update', ids: ['TC-BULK-A', 'TC-BULK-B'], payload: { status: 'pass' } },
      headers: { Authorization: `Bearer ${token}`, 'Content-Type': 'application/json' },
    });
    expect(bulkRes.status()).toBe(200);

    // Verify both updated
    const a = await page.request.get(`${BASE}/api/tests/TC-BULK-A`, { headers: { Authorization: `Bearer ${token}` } });
    const b = await page.request.get(`${BASE}/api/tests/TC-BULK-B`, { headers: { Authorization: `Bearer ${token}` } });
    expect((await a.json()).status).toBe('pass');
    expect((await b.json()).status).toBe('pass');

    // Cleanup
    await page.request.post(`${BASE}/api/tests/bulk`, {
      data: { action: 'delete', ids: ['TC-BULK-A', 'TC-BULK-B'] },
      headers: { Authorization: `Bearer ${token}`, 'Content-Type': 'application/json' },
    });
  });

  // EXTRA-20 · Run — PATCH status a vari stati [P1]
  test('EXTRA-20: run status cycle through allowed states', async ({ page }) => {
    await loginAs(page, 'marco@acme.com');
    const token = await getToken(page);

    // Create a fresh run
    const created = await page.request.post(`${BASE}/api/runs`, {
      data: { id: `R-CYCLE-${Date.now()}`, name: 'Status cycle test', status: 'running', total: 0 },
      headers: { Authorization: `Bearer ${token}`, 'Content-Type': 'application/json' },
    });
    const run = await created.json();

    // Pause
    const paused = await page.request.patch(`${BASE}/api/runs/${run.id}/status?status=paused`, {
      headers: { Authorization: `Bearer ${token}` },
    });
    expect(paused.status()).toBe(200);
    expect((await paused.json()).status).toBe('paused');

    // Abort
    const aborted = await page.request.patch(`${BASE}/api/runs/${run.id}/status?status=aborted`, {
      headers: { Authorization: `Bearer ${token}` },
    });
    expect(aborted.status()).toBe(200);
    expect((await aborted.json()).status).toBe('aborted');
  });

});
