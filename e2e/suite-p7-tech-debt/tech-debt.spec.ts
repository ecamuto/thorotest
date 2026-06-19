import { test, expect } from '@playwright/test';
import { loginAs } from '../fixtures/auth';

test.describe('suite-p7-tech-debt', () => {
  // TD-04 / 07-02: non-admin navigating to #/admin is redirected with error toast
  test('P7-01: non-admin navigating to #/admin is redirected to overview with error toast', async ({ page }) => {
    // lisa@acme.com is a tester — non-admin
    await loginAs(page, 'lisa@acme.com');

    await page.goto('/#/admin');
    await page.waitForTimeout(500);

    // Must redirect to overview
    const hash = await page.evaluate(() => window.location.hash);
    expect(hash).toBe('#/overview');

    // Toast with "Admin access required" must be visible (exact match targets the toast div, not parent wrappers)
    const toast = page.locator('div').filter({ hasText: /^Admin access required$/ });
    await expect(toast).toBeVisible({ timeout: 5000 });

    // Toast must have error styling: borderLeft is 4px (only error severity sets this)
    await expect(toast).toHaveCSS('border-left-width', '4px');
  });

  // TD-04 / 07-02: Docs view renders without ReferenceError after window.Docs export added
  test('P7-02: Docs nav item renders Docs view without ReferenceError', async ({ page }) => {
    const jsErrors: string[] = [];
    page.on('pageerror', err => jsErrors.push(err.message));

    await loginAs(page, 'marco@acme.com');

    // Navigate via sidebar nav item (same as user clicking)
    await page.click('a.nav-item[href="#/docs"]');
    await page.waitForTimeout(500);

    // No uncaught JS errors (specifically no ReferenceError from missing window.Docs)
    const referenceErrors = jsErrors.filter(e => e.includes('ReferenceError') || e.includes('Docs is not defined'));
    expect(referenceErrors).toHaveLength(0);

    // Docs view must render a recognizable element
    await expect(page.locator('.page-title').first()).toBeVisible({ timeout: 5000 });
  });
});
