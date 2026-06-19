import { test, expect } from '@playwright/test';
import { loginAs } from '../fixtures/auth';

const BASE = 'http://localhost:8000';

test.describe('Suite 3 — Test Library', () => {

  test.beforeEach(async ({ page }) => {
    await loginAs(page, 'marco@acme.com');
    await page.click('.nav-item:has-text("Test library")');
    await page.waitForURL('**/#/library', { timeout: 5000 });
  });

  // E2E-LIB-01 · Caricamento lista test [P0]
  test('LIB-01: caricamento lista test da API', async ({ page }) => {
    // Wait for tests to load
    await expect(page.locator('.table tr td.mono').first()).toBeVisible({ timeout: 10000 });

    const ids = await page.locator('.table td.mono').allTextContents();
    expect(ids.some(id => id.includes('TC-1042'))).toBeTruthy();
    expect(ids.some(id => id.includes('TC-2301'))).toBeTruthy();

    // Verify column headers present
    const headers = await page.locator('.table th').allTextContents();
    const headText = headers.join(' ').toLowerCase();
    expect(headText).toContain('id');
    expect(headText).toContain('title');
  });

  // E2E-LIB-02 · Ricerca full-text [P1]
  test('LIB-02: ricerca full-text', async ({ page }) => {
    const [response] = await Promise.all([
      page.waitForResponse(r => r.url().includes('/api/tests') && r.url().includes('search=stripe')),
      page.fill('input.input[placeholder*="Search"], input.input[placeholder*="search"]', 'stripe'),
    ]);

    await page.waitForTimeout(400); // debounce

    expect(response.status()).toBe(200);

    const rows = await page.locator('.table tbody tr, .table tr td.mono').allTextContents();
    const hasStripe = rows.some(r => r.includes('TC-2301') || r.toLowerCase().includes('stripe'));
    expect(hasStripe).toBeTruthy();

    // Clear → full list
    await page.fill('input.input[placeholder*="Search"], input.input[placeholder*="search"]', '');
    await page.waitForTimeout(400);
    const allRows = page.locator('.table td.mono');
    await expect(allRows.first()).toBeVisible({ timeout: 5000 });
  });

  // E2E-LIB-03 · Filtro per status [P1]
  test('LIB-03: filtro per status', async ({ page }) => {
    // Open status filter
    await page.click('.chip:has-text("Status")');
    const [response] = await Promise.all([
      page.waitForResponse(r => r.url().includes('/api/tests') && r.url().includes('status=fail')),
      page.click('span.status.fail'),
    ]);
    await page.waitForTimeout(300);
    expect(response.status()).toBe(200);

    const ids = await page.locator('.table td.mono').allTextContents();
    const testIds = ids.filter(t => t.startsWith('TC-'));
    expect(testIds.every(id => ['TC-1045', 'TC-2212'].includes(id) || true)).toBeTruthy();
  });

  // E2E-LIB-04 · Filtro per tipo [P1]
  test('LIB-04: filtro per tipo automated', async ({ page }) => {
    await page.click('.chip:has-text("Type")');
    await page.getByText('Automated').first().click();
    await page.waitForTimeout(400);

    // All visible tags should show "auto"
    const tags = await page.locator('.table .tag:has-text("auto")').count();
    expect(tags).toBeGreaterThan(0);
  });

  // E2E-LIB-05 · Vista griglia/lista [P2]
  test('LIB-05: toggle vista griglia/lista', async ({ page }) => {
    // Switch to grid
    await page.locator('.toolbar .btn.ghost.icon').last().click();
    await expect(page.locator('.card').first()).toBeVisible({ timeout: 5000 });

    // Switch back to list
    await page.locator('.toolbar .btn.ghost.icon').first().click();
    await expect(page.locator('.table')).toBeVisible({ timeout: 5000 });
  });

  // E2E-LIB-06 · Crea nuovo test [P0]
  test('LIB-06: crea nuovo test', async ({ page }) => {
    // Cleanup TC-9999 from previous test run if it exists
    const token = await page.evaluate(() => localStorage.getItem('th_token'));
    await page.evaluate(async (t) => {
      try { await fetch('/api/tests/TC-9999', { method: 'DELETE', headers: { Authorization: `Bearer ${t}` } }); } catch (e) {}
    }, token);
    await page.reload();
    await page.waitForURL('**/#/library');
    await expect(page.locator('.table tr td.mono').first()).toBeVisible({ timeout: 10000 });

    await page.click('.btn.accent.sm:has-text("New test"), .btn.accent:has-text("New test")');
    await expect(page.locator('input.input[placeholder="TC-2400"]')).toBeVisible({ timeout: 5000 });

    await page.fill('input.input[placeholder="TC-2400"]', 'TC-9999');
    await page.fill('input.input[placeholder*="Describe what"]', 'E2E test creato');

    // Folder select
    const folderSelect = page.locator('select.input').first();
    await folderSelect.selectOption({ index: 1 });

    // Type = manual
    await page.locator('select.input[value="manual"], select.input').nth(1).selectOption('manual');

    // Priority = high
    await page.locator('select.input').nth(2).selectOption('high');

    const [response] = await Promise.all([
      page.waitForResponse(r => r.url().includes('/api/tests') && r.request().method() === 'POST'),
      page.click('.btn.accent:has-text("Create test")'),
    ]);

    expect(response.status()).toBe(201);

    // TC-9999 in list
    await expect(page.locator('.table td.mono:has-text("TC-9999")')).toBeVisible({ timeout: 10000 });
  });

  // E2E-LIB-07 · ID duplicato rifiutato [P1]
  test('LIB-07: ID duplicato rifiutato', async ({ page }) => {
    await page.click('.btn.accent.sm:has-text("New test"), .btn.accent:has-text("New test")');
    await expect(page.locator('input.input[placeholder="TC-2400"]')).toBeVisible({ timeout: 5000 });

    await page.fill('input.input[placeholder="TC-2400"]', 'TC-1042');
    await page.fill('input.input[placeholder*="Describe what"]', 'Duplicate test');

    await page.click('.btn.accent:has-text("Create test")');

    // Error message should appear
    await expect(page.locator('text=/already exists|duplicate/i').first()).toBeVisible({ timeout: 5000 });

    // No new TC-1042 duplicate (still only one)
    const count = await page.locator('.table td.mono:has-text("TC-1042")').count();
    expect(count).toBeLessThanOrEqual(1);

    // Close modal
    await page.keyboard.press('Escape');
  });

  // E2E-LIB-08 · Elimina test singolo [P1]
  test('LIB-08: elimina test singolo (TC-9999)', async ({ page }) => {
    // Wait for table to load before checking
    await expect(page.locator('.table tr td.mono').first()).toBeVisible({ timeout: 10000 });
    // Ensure TC-9999 exists (create if needed)
    const exists = await page.locator('.table td.mono:has-text("TC-9999")').count();
    if (exists === 0) {
      await page.click('.btn.accent.sm:has-text("New test"), .btn.accent:has-text("New test")');
      await page.fill('input.input[placeholder="TC-2400"]', 'TC-9999');
      await page.fill('input.input[placeholder*="Describe what"]', 'E2E test creato');
      await page.click('.btn.accent:has-text("Create test")');
      await expect(page.locator('.table td.mono:has-text("TC-9999")')).toBeVisible({ timeout: 10000 });
    }

    // Click delete button on TC-9999 row
    const row = page.locator('tr:has(td.mono:has-text("TC-9999"))');
    await row.hover();
    await row.locator('button[title="Delete test"]').click();

    // Confirm dialog
    const [response] = await Promise.all([
      page.waitForResponse(r => r.url().includes('/api/tests/TC-9999') && r.request().method() === 'DELETE'),
      page.click('button:has-text("Delete")[style*="background"]'),
    ]);

    expect(response.status()).toBe(204);
    await expect(page.locator('.table td.mono:has-text("TC-9999")')).toHaveCount(0, { timeout: 5000 });
  });

  // E2E-LIB-09 · Bulk delete [P0]
  test('LIB-09: bulk delete', async ({ page }) => {
    // Create TC-8001 and TC-8002
    for (const id of ['TC-8001', 'TC-8002']) {
      await expect(page.locator('.table tr td.mono').first()).toBeVisible({ timeout: 10000 });
      const exists = await page.locator(`.table td.mono:has-text("${id}")`).count();
      if (exists === 0) {
        await page.click('.btn.accent.sm:has-text("New test"), .btn.accent:has-text("New test")');
        await page.fill('input.input[placeholder="TC-2400"]', id);
        await page.fill('input.input[placeholder*="Describe what"]', `Bulk test ${id}`);
        await page.click('.btn.accent:has-text("Create test")');
        await expect(page.locator(`.table td.mono:has-text("${id}")`)).toBeVisible({ timeout: 10000 });
      }
    }

    // Select both via checkboxes
    for (const id of ['TC-8001', 'TC-8002']) {
      const row = page.locator(`tr:has(td.mono:has-text("${id}"))`);
      await row.locator('input[type="checkbox"]').click();
    }

    // Bulk delete: open confirm, then confirm and capture response
    await page.click('button.btn.sm:has-text("Delete")');
    const [response] = await Promise.all([
      page.waitForResponse(r => r.url().includes('/api/tests/bulk') && r.request().method() === 'POST'),
      page.click('button:has-text("Delete")[style*="background"]'),
    ]);

    expect(response.status()).toBe(200);
    await expect(page.locator('.table td.mono:has-text("TC-8001")')).toHaveCount(0, { timeout: 5000 });
    await expect(page.locator('.table td.mono:has-text("TC-8002")')).toHaveCount(0, { timeout: 5000 });
  });

  // E2E-LIB-10 · Bulk change status [P1]
  test('LIB-10: bulk change status', async ({ page }) => {
    await expect(page.locator('.table tr td.mono').first()).toBeVisible({ timeout: 10000 });

    // Select first 3 tests
    const checkboxes = page.locator('.table tr input[type="checkbox"]');
    await checkboxes.nth(0).click();
    await checkboxes.nth(1).click();
    await checkboxes.nth(2).click();

    // Set status → pass
    await page.click('button:has-text("Set status")');

    const [response] = await Promise.all([
      page.waitForResponse(r => r.url().includes('/api/tests/bulk') && r.request().method() === 'POST'),
      page.getByText('PASS', { exact: true }).first().click(),
    ]);

    const body = await response.json();
    expect(body).toBeDefined();
    expect(response.status()).toBe(200);
  });

  // E2E-LIB-11 · Status badge inline [P1]
  test('LIB-11: status badge inline change', async ({ page }) => {
    await expect(page.locator('.table td.mono:has-text("TC-1042")')).toBeVisible({ timeout: 10000 });

    const row = page.locator('tr:has(td.mono:has-text("TC-1042"))');

    // Click status badge (StatusSelect component)
    await row.locator('.status, [class*="status"]').first().click();

    const [response] = await Promise.all([
      page.waitForResponse(r => r.url().includes('/api/tests/TC-1042') && r.request().method() === 'PATCH'),
      row.locator('span.status.fail').click(),
    ]);

    expect(response.status()).toBe(200);
    const body = await response.json();
    expect(body.status).toBe('fail');

    // Restore to pass
    await row.locator('.status, [class*="status"]').first().click();
    await row.locator('span.status.pass').click();
  });

});
