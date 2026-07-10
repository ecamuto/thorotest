import { test, expect } from '@playwright/test';
import { loginAs } from '../fixtures/auth';

const BASE = 'http://localhost:8000';

test.describe('Suite 4 — Test Detail', () => {

  test.beforeEach(async ({ page }) => {
    await loginAs(page, 'marco@acme.com');
  });

  // E2E-DET-01 · Caricamento dettaglio [P0]
  test('DET-01: caricamento dettaglio TC-2301', async ({ page }) => {
    await page.goto('/#/tests/TC-2301');
    await page.waitForURL('**/#/tests/TC-2301', { timeout: 10000 });
    await expect(page.locator('.app')).toHaveAttribute('data-screen-label', 'test-detail');
    await expect(page.locator('.app')).toContainText('TC-2301', { timeout: 5000 });

    const content = await page.locator('.app').textContent();
    expect(content).toContain('TC-2301');
  });

  // E2E-DET-02 · Edit titolo inline [P1]
  test('DET-02: edit titolo inline', async ({ page }) => {
    await page.goto('/#/tests/TC-2301');
    await page.waitForURL('**/#/tests/TC-2301', { timeout: 10000 });

    // Get original title
    const originalTitle = await page.locator('h1').first().textContent();

    // Click on title to edit
    await page.click('h1[title="Click to edit title"]');
    const input = page.locator('input.input:visible').first();
    await expect(input).toBeVisible({ timeout: 5000 });

    const newTitle = 'E2E Title Edit Test';
    await input.fill(newTitle);

    const [response] = await Promise.all([
      page.waitForResponse(r => r.url().includes('/api/tests/TC-2301') && r.request().method() === 'PATCH'),
      page.click('.btn.sm.accent:has-text("Save")'),
    ]);

    expect(response.status()).toBe(200);
    await expect(page.locator('h1').first()).toContainText(newTitle, { timeout: 5000 });

    // Restore original title
    await page.click('h1[title="Click to edit title"]');
    const restoreInput = page.locator('input.input:visible').first();
    await restoreInput.fill(originalTitle!.trim());
    await page.click('.btn.sm.accent:has-text("Save")');
  });

  // E2E-DET-03 · Change status da TestDetail [P1]
  test('DET-03: change status da TestDetail', async ({ page }) => {
    await page.goto('/#/tests/TC-2301');
    await page.waitForURL('**/#/tests/TC-2301', { timeout: 10000 });

    // Click status badge
    await page.locator('.status, [class*="status"]').first().click();

    const [response] = await Promise.all([
      page.waitForResponse(r => r.url().includes('/api/tests/TC-2301') && r.request().method() === 'PATCH'),
      page.click('span.status.fail'),
    ]);

    expect(response.status()).toBe(200);

    // Restore
    await page.locator('.status, [class*="status"]').first().click();
    await page.click('span.status.pass');
  });

  // E2E-DET-04 · Elimina test da TestDetail [P1]
  test('DET-04: elimina test da TestDetail (TC-7777)', async ({ page }) => {
    // Create TC-7777 first
    await page.click('.nav-item:has-text("Test library")');
    await page.waitForURL('**/#/library', { timeout: 5000 });

    const exists = await page.locator('.table td.mono:has-text("TC-7777")').count();
    if (exists === 0) {
      await page.click('.btn.accent.sm:has-text("New test"), .btn.accent:has-text("New test")');
      await page.fill('input.input[placeholder="TC-2400"]', 'TC-7777');
      await page.fill('input.input[placeholder*="Describe what"]', 'E2E temp delete test');
      await page.click('.btn.accent:has-text("Create test")');
      await expect(page.locator('.table td.mono:has-text("TC-7777")')).toBeVisible({ timeout: 10000 });
    }

    // Open TC-7777
    await page.goto('/#/tests/TC-7777');
    await page.waitForURL('**/#/tests/TC-7777', { timeout: 10000 });

    // Delete
    await page.click('button:has-text("Delete"):visible');
    await expect(page.locator('.btn:has-text("Delete"):visible').last()).toBeVisible({ timeout: 3000 });

    const [response] = await Promise.all([
      page.waitForResponse(r => r.url().includes('/api/tests/TC-7777') && r.request().method() === 'DELETE'),
      page.locator('button:has-text("Delete")[style*="background"]').click(),
    ]);

    expect(response.status()).toBe(204);
    await page.waitForURL('**/#/library', { timeout: 10000 });
    await expect(page.locator('.app')).toHaveAttribute('data-screen-label', 'library');
  });

  // E2E-DET-05 · Tab Run History [P1]
  test('DET-05: tab Run History', async ({ page }) => {
    await page.goto('/#/tests/TC-2301');
    await page.waitForURL('**/#/tests/TC-2301', { timeout: 10000 });

    const [response] = await Promise.all([
      page.waitForResponse(r => r.url().includes('/api/tests/TC-2301/history')),
      page.click('.tab:has-text("Run history")'),
    ]);

    expect(response.status()).toBe(200);
    const body = await response.json();
    expect(Array.isArray(body)).toBeTruthy();
    expect(body.length).toBeGreaterThan(0);
  });

  // E2E-DET-06 · Tab Defects — lista [P1]
  test('DET-06: tab Defects lista BUG-1042', async ({ page }) => {
    await page.goto('/#/tests/TC-1045');
    await page.waitForURL('**/#/tests/TC-1045', { timeout: 10000 });

    const [response] = await Promise.all([
      page.waitForResponse(r => r.url().includes('/api/tests/TC-1045/defects')),
      page.click('.tab:has-text("Defects")'),
    ]);

    expect(response.status()).toBe(200);
    await expect(page.locator('.table td.mono:has-text("BUG-1042")').first()).toBeVisible({ timeout: 5000 });
  });

  // E2E-DET-07 · Tab Defects — crea defect [P1]
  test('DET-07: crea defect', async ({ page }) => {
    await page.goto('/#/tests/TC-1045');
    await page.waitForURL('**/#/tests/TC-1045', { timeout: 10000 });

    await page.click('.tab:has-text("Defects")');
    await page.click('.btn.sm.accent:has-text("Create defect")');

    await expect(page.locator('input.input[placeholder*="bug"], input.input[placeholder*="Describe"]').first()).toBeVisible({ timeout: 5000 });

    await page.locator('input.input[placeholder*="bug"], input.input[placeholder*="Describe"]').first().fill('E2E defect test');
    await page.locator('label:has-text("Severity") + select.input').selectOption('high');

    const [response] = await Promise.all([
      page.waitForResponse(r => r.url().includes('/api/defects') && r.request().method() === 'POST'),
      page.click('.btn.accent:not(.sm):has-text("Create")'),
    ]);

    expect(response.status()).toBe(201);
    const body = await response.json();
    expect(body.id).toMatch(/^BUG-/);
    await expect(page.locator(`.table td.mono:has-text("${body.id}")`).first()).toBeVisible({ timeout: 5000 });
  });

  // E2E-DET-08 · Tab Comments — lista [P0]
  test('DET-08: tab Comments lista', async ({ page }) => {
    await page.goto('/#/tests/TC-2301');
    await page.waitForURL('**/#/tests/TC-2301', { timeout: 10000 });

    const [response] = await Promise.all([
      page.waitForResponse(r => r.url().includes('/api/tests/TC-2301/comments')),
      page.click('.tab:has-text("Comments")'),
    ]);

    expect(response.status()).toBe(200);
    const body = await response.json();
    expect(Array.isArray(body)).toBeTruthy();

    // Pre-existing comments
    await expect(page.locator('.app')).toContainText(/Luca|Marco|Anna/, { timeout: 5000 });
  });

  // E2E-DET-09 · Tab Comments — aggiungi commento [P0]
  test('DET-09: aggiungi commento come Lisa Park', async ({ page }) => {
    // Login as Lisa
    await page.evaluate(() => localStorage.removeItem('th_token'));
    await loginAs(page, 'lisa@acme.com');

    await page.goto('/#/tests/TC-2301');
    await page.waitForURL('**/#/tests/TC-2301', { timeout: 10000 });

    await page.click('.tab:has-text("Comments")');

    await page.fill('textarea.textarea', 'Commento E2E test');

    const [response] = await Promise.all([
      page.waitForResponse(r => r.url().includes('/api/tests/') && r.url().includes('/comments') && r.request().method() === 'POST'),
      page.click('.btn.primary.sm:has-text("Comment"), .btn.sm:has-text("Comment")'),
    ]);

    expect(response.status()).toBe(201);

    // Comment appears with Lisa Park name
    await expect(page.locator('.app')).toContainText('Lisa Park', { timeout: 5000 });
    await expect(page.locator('.app')).toContainText('Commento E2E test', { timeout: 5000 });
  });

  // E2E-DET-10 · Tab Git History [P2]
  test('DET-10: tab Git History non crasho', async ({ page }) => {
    await page.goto('/#/tests/TC-2301');
    await page.waitForURL('**/#/tests/TC-2301', { timeout: 10000 });

    await page.click('.tab:has-text("Git history")');

    // No crash = no error element, content is visible
    await expect(page.locator('.app')).not.toContainText('Error', { timeout: 3000 });
    const content = await page.locator('.app').textContent();
    expect(content).toBeTruthy();
  });

  // E2E-DET-11 · Tab Changes — record change history [P1]
  test('DET-11: tab Changes registra un edit', async ({ page }) => {
    await page.goto('/#/tests/TC-2301');
    await page.waitForURL('**/#/tests/TC-2301', { timeout: 10000 });

    // Generate a change: flip status to fail (PATCH -> record_history "updated")
    await page.locator('.status, [class*="status"]').first().click();
    await Promise.all([
      page.waitForResponse(r => r.url().includes('/api/tests/TC-2301') && r.request().method() === 'PATCH'),
      page.click('span.status.fail'),
    ]);

    // Open Changes tab — expect the history endpoint + a rendered entry
    const [response] = await Promise.all([
      page.waitForResponse(r => r.url().includes('/api/history/test/TC-2301')),
      page.click('.tab:has-text("Changes")'),
    ]);
    expect(response.status()).toBe(200);
    const body = await response.json();
    expect(Array.isArray(body)).toBeTruthy();
    expect(body.length).toBeGreaterThan(0);

    // "status" field diff visible in the timeline
    await expect(page.locator('.app')).toContainText('status', { timeout: 5000 });

    // Restore
    await page.locator('.status, [class*="status"]').first().click();
    await page.click('span.status.pass');
  });

});
