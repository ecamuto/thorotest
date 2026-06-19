import { test, expect } from '@playwright/test';
import { loginAs } from '../fixtures/auth';

test.describe('Suite 8 — Tema e Tweaks', () => {

  test.beforeEach(async ({ page }) => {
    await loginAs(page, 'marco@acme.com');
    // Reset to dark/compact defaults
    await page.evaluate(() => {
      const s = localStorage.getItem('th_tweaks');
      if (!s) return;
      const t = JSON.parse(s);
      t.theme = 'dark';
      t.density = 'compact';
      localStorage.setItem('th_tweaks', JSON.stringify(t));
    });
    await page.reload();
    await page.waitForURL('**/#/overview', { timeout: 10000 });
  });

  async function openTweaksPanel(page: any) {
    await expect(page.locator('.app')).toBeVisible({ timeout: 10000 });
    await page.evaluate(async () => {
      for (let i = 0; i < 20; i++) {
        window.postMessage({ type: '__activate_edit_mode' }, '*');
        await new Promise(r => setTimeout(r, 150));
        if (document.querySelector('.twk-panel')) break;
      }
    });
    await expect(page.locator('.twk-panel')).toBeVisible({ timeout: 5000 });
  }

  // E2E-TWEAK-01 · Cambio tema [P2]
  test('TWEAK-01: cambio tema dark → light e persistenza', async ({ page }) => {
    await openTweaksPanel(page);

    // Click "Light" option in theme segment
    await page.click('.twk-panel .twk-seg button:has-text("Light")');

    // html[data-theme="light"]
    await expect(page.locator('html')).toHaveAttribute('data-theme', 'light', { timeout: 3000 });

    // Restore dark
    await page.click('.twk-panel .twk-seg button:has-text("Dark")');
    await expect(page.locator('html')).toHaveAttribute('data-theme', 'dark', { timeout: 3000 });
  });

  // E2E-TWEAK-02 · Cambio densità [P2]
  test('TWEAK-02: cambio densità compact → comfortable', async ({ page }) => {
    await openTweaksPanel(page);

    // Click "Comfortable" option in density segment
    await page.click('.twk-panel .twk-seg button:has-text("Comfortable")');

    // html[data-density="comfortable"]
    await expect(page.locator('html')).toHaveAttribute('data-density', 'comfortable', { timeout: 3000 });

    // Restore compact
    await page.click('.twk-panel .twk-seg button:has-text("Compact")');
    await expect(page.locator('html')).toHaveAttribute('data-density', 'compact', { timeout: 3000 });
  });

});
