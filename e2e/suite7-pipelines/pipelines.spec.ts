import { test, expect } from '@playwright/test';
import { loginAs } from '../fixtures/auth';

test.describe('Suite 7 — Pipelines', () => {

  test.beforeEach(async ({ page }) => {
    await loginAs(page, 'marco@acme.com');
  });

  // E2E-PIPE-01 · Lista pipeline [P2]
  test('PIPE-01: lista pipeline caricata', async ({ page }) => {
    await page.click('.nav-item:has-text("CI pipelines")');
    await page.waitForURL('**/#/pipelines', { timeout: 5000 });
    await expect(page.locator('.app')).toHaveAttribute('data-screen-label', 'pipelines');

    // At least 6 pipeline rows/items
    await expect(page.locator('.table tr').first()).toBeVisible({ timeout: 10000 });
    const rows = await page.locator('.table tr').count();
    expect(rows).toBeGreaterThanOrEqual(6);

    // Status badges present (pass/fail/running)
    const badges = await page.locator('.status, [class*="status"]').count();
    expect(badges).toBeGreaterThan(0);
  });

});
