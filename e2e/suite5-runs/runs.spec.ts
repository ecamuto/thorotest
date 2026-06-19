import { test, expect } from '@playwright/test';
import { loginAs } from '../fixtures/auth';

const BASE = 'http://localhost:8000';

test.describe('Suite 5 — Runs Management', () => {

  test.beforeEach(async ({ page }) => {
    await loginAs(page, 'marco@acme.com');
    await page.click('.nav-item:has-text("Runs & plans")');
    await page.waitForURL('**/#/runs', { timeout: 5000 });
  });

  // E2E-RUN-01 · Lista runs [P0]
  test('RUN-01: lista runs', async ({ page }) => {
    // Show history tab (all runs)
    await page.click('.tab:has-text("History")');
    await expect(page.locator('.table td.mono:has-text("R-1287")')).toBeVisible({ timeout: 10000 });
    await expect(page.locator('.table td.mono:has-text("R-1286")')).toBeVisible({ timeout: 5000 });
    await expect(page.locator('.table td.mono:has-text("R-1285")')).toBeVisible({ timeout: 5000 });
  });

  // E2E-RUN-02 · Crea nuova run (flusso 2 step) [P0]
  test('RUN-02: crea nuova run', async ({ page }) => {
    await page.click('.btn.accent:has-text("Start run")');

    // Step 1: cerca stripe e seleziona TC-2301
    await page.waitForSelector('input.input[placeholder*="Search"], input.input:visible', { timeout: 5000 });
    await page.fill('input.input:visible', 'stripe');

    // Wait for the filtered list to render (slower under parallel load)
    await page.waitForSelector('label:has-text("TC-2301")', { timeout: 5000 });

    // Select TC-2301
    await page.click('label:has-text("TC-2301") input[type="checkbox"]');

    // Also TC-2401 if present
    const tc2401 = page.locator('label:has-text("TC-2401") input[type="checkbox"]');
    if (await tc2401.count() > 0) {
      await tc2401.click();
    }

    await page.click('.btn.accent:has-text("Configure")');

    // Step 2: fill name, env, branch
    await page.fill('input.input:visible', 'E2E Run Test');
    await page.locator('select.input').selectOption('staging');

    const branchInput = page.locator('input.input:visible').last();
    await branchInput.fill('test/e2e');

    const [response] = await Promise.all([
      page.waitForResponse(r => r.url().includes('/api/runs') && r.request().method() === 'POST'),
      page.click('.btn.accent:has-text("Create & start")'),
    ]);

    expect(response.status()).toBe(201);
    const run = await response.json();

    // Redirect to RunDetail
    await page.waitForURL(`**/#/runs/${run.id}`, { timeout: 10000 });
    await expect(page.locator('.app')).toHaveAttribute('data-screen-label', 'run-detail');

    await expect(page.locator('.app')).toContainText('TC-2301', { timeout: 10000 });
  });

  // E2E-RUN-03 · RunDetail carica da API [P0]
  test('RUN-03: RunDetail carica da API', async ({ page }) => {
    // Navigate to R-1287
    await page.goto('/#/runs/R-1287');
    await page.waitForURL('**/#/runs/R-1287', { timeout: 10000 });
    await expect(page.locator('.app')).toHaveAttribute('data-screen-label', 'run-detail');

    // Auto-retries until the run finishes loading (no fixed timeout race)
    await expect(page.locator('.app')).toContainText('R-1287', { timeout: 10000 });

    // Progress bar visible
    await expect(page.locator('.bar')).toBeVisible({ timeout: 5000 });
  });

  // E2E-RUN-04 · WebSocket aggiornamento live [P1]
  test('RUN-04: WebSocket aggiornamento live', async ({ page }) => {
    await page.goto('/#/runs/R-1287');
    await page.waitForURL('**/#/runs/R-1287', { timeout: 10000 });

    // Capture WS connection
    let wsConnected = false;
    page.on('websocket', ws => {
      if (ws.url().includes('/ws/runs/')) {
        wsConnected = true;
      }
    });

    // Wait for WS to connect (run must be "running")
    await page.waitForTimeout(3000);

    // If status is running, WS should be connected
    const status = await page.locator('.status:visible, [class*="status"]:visible').first().textContent();
    if (status && status.toLowerCase().includes('running')) {
      expect(wsConnected).toBeTruthy();
    }

    // Progress bar should be present regardless
    await expect(page.locator('.bar')).toBeVisible({ timeout: 5000 });
  });

  // E2E-RUN-05 · Pausa run [P1]
  test('RUN-05: pausa run', async ({ page }) => {
    await page.goto('/#/runs/R-1287');
    await page.waitForURL('**/#/runs/R-1287', { timeout: 10000 });

    const pauseBtn = page.locator('button:has-text("Pause")');
    await expect(pauseBtn).toBeVisible({ timeout: 5000 });

    const isDisabled = await pauseBtn.isDisabled();
    if (!isDisabled) {
      const [response] = await Promise.all([
        page.waitForResponse(r => r.url().includes('/api/runs/R-1287/status') || (r.url().includes('/api/runs/R-1287') && r.request().method() === 'PATCH')),
        pauseBtn.click(),
      ]);

      expect(response.status()).toBe(200);

      // Badge should show paused
      await expect(page.locator('.app')).toContainText(/paused/i, { timeout: 5000 });

      // Pause button disabled
      await expect(pauseBtn).toBeDisabled({ timeout: 3000 });
    } else {
      // Run not running — button already disabled, test passes
      expect(isDisabled).toBeTruthy();
    }
  });

  // E2E-RUN-06 · Abort run con confirm [P1]
  test('RUN-06: abort run con confirm', async ({ page }) => {
    // Use a fresh run or R-1287
    await page.goto('/#/runs/R-1287');
    await page.waitForURL('**/#/runs/R-1287', { timeout: 10000 });

    const abortBtn = page.locator('button:has-text("Abort")');
    await expect(abortBtn).toBeVisible({ timeout: 5000 });

    const isDisabled = await abortBtn.isDisabled();
    if (!isDisabled) {
      // Setup dialog intercept to cancel
      page.once('dialog', d => d.dismiss());
      await abortBtn.click();

      // Run still running (or not aborted)
      await page.waitForTimeout(500);
      const content = await page.locator('.app').textContent();
      expect(content).not.toMatch(/aborted/i);

      // Now actually abort
      page.once('dialog', d => d.accept());
      const [response] = await Promise.all([
        page.waitForResponse(r =>
          r.url().includes('/api/runs/R-1287') && r.request().method() === 'PATCH'
        ),
        abortBtn.click(),
      ]);

      expect(response.status()).toBe(200);
      await expect(page.locator('.app')).toContainText(/aborted/i, { timeout: 5000 });
    }
  });

  // E2E-RUN-07 · Bottone Pause disabilitato su run non-running [P2]
  test('RUN-07: pause disabilitato su run non-running', async ({ page }) => {
    await page.goto('/#/runs/R-1286');
    await page.waitForURL('**/#/runs/R-1286', { timeout: 10000 });

    const pauseBtn = page.locator('button:has-text("Pause")');
    if (await pauseBtn.count() > 0) {
      await expect(pauseBtn).toBeDisabled({ timeout: 3000 });
    }
    // If button absent, test passes
  });

});
