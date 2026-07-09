import { test, expect } from '@playwright/test';
import { loginAs } from '../fixtures/auth';

test.describe('Suite 7 — Pipelines', () => {

  test.beforeEach(async ({ page }) => {
    await loginAs(page, 'marco@acme.com');
  });

  // E2E-PIPE-01 · Pagina pipeline [P2]
  test('PIPE-01: pagina pipeline caricata', async ({ page }) => {
    await page.click('.nav-item:has-text("CI pipelines")');
    await page.waitForURL('**/#/pipelines', { timeout: 5000 });
    await expect(page.locator('.app')).toHaveAttribute('data-screen-label', 'pipelines');

    // Pipelines are not seeded: a fresh instance shows the empty state, but
    // another test may have recorded a run — accept either (empty state OR rows).
    await expect(async () => {
      const empty = await page.locator('.empty', { hasText: 'No pipeline runs yet' }).count();
      const rows = await page.locator('.table tbody tr').count();
      expect(empty > 0 || rows > 0).toBeTruthy();
    }).toPass({ timeout: 10000 });
  });

});
