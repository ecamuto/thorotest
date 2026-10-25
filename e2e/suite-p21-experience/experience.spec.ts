import { test, expect } from '@playwright/test';
import AxeBuilder from '@axe-core/playwright';
import { loginAs } from '../fixtures/auth';

async function waitForStablePaint(page: any) {
  await page.evaluate(async () => {
    await document.fonts.ready;
    await new Promise<void>((resolve) => requestAnimationFrame(() =>
      requestAnimationFrame(() => resolve())));
  });
}

test.describe('Phase 2 — progressive and accessible experience', () => {
  test.beforeEach(async ({ page }) => {
    await page.emulateMedia({ reducedMotion: 'reduce' });
    await loginAs(page, 'marco@acme.com');
    await expect(page).toHaveTitle('Overview — ThoroTest');
  });

  test('UX-01: route scripts load on demand and only once', async ({ page }) => {
    await expect(page.locator('script[data-route-module]')).toHaveCount(0);

    await page.getByRole('link', { name: 'Test library' }).click();
    await expect(page).toHaveTitle('Test library — ThoroTest');
    await expect(page.locator('script[data-route-module="views/view-library.js"]')).toHaveCount(1);
    await expect(page.locator('script[data-route-module="views/view-runs.js"]')).toHaveCount(0);

    await page.getByRole('link', { name: 'Runs & plans' }).click();
    await expect(page).toHaveTitle('Runs & plans — ThoroTest');
    await expect(page.locator('script[data-route-module="views/view-runs.js"]')).toHaveCount(1);

    await page.getByRole('link', { name: 'Test library' }).click();
    await expect(page).toHaveTitle('Test library — ThoroTest');
    await expect(page.locator('script[data-route-module="views/view-library.js"]')).toHaveCount(1);
  });

  test('UX-02: direct links resolve their ordered view dependencies', async ({ page }) => {
    await page.goto('/#/tests/TC-2301');
    await expect(page).toHaveTitle('Test details — ThoroTest');
    await expect(page.locator('script[data-route-module="views/view-requirements.js"]')).toHaveCount(1);
    await expect(page.locator('script[data-route-module="views/view-test-detail.js"]')).toHaveCount(1);
    await expect(page.locator('.app')).toContainText('TC-2301');
  });

  test('UX-03: SPA navigation announces the route and moves focus', async ({ page }) => {
    await page.getByRole('link', { name: 'CI pipelines' }).click();
    await expect(page).toHaveTitle('CI pipelines — ThoroTest');
    await expect(page.locator('[role="status"][aria-live="polite"]')).toContainText('CI pipelines loaded');
    await expect.poll(() => page.evaluate(() => document.activeElement?.id)).toBe('main-content');
  });

  for (const route of [
    { name: 'overview', path: '/#/overview', ready: '.page-title' },
    { name: 'library', path: '/#/library', ready: '.tree-row' },
    { name: 'runs', path: '/#/runs', ready: '.page-title' },
  ]) {
    test(`A11Y-${route.name}: no serious or critical WCAG A/AA violations`, async ({ page }) => {
      await page.goto(route.path);
      await expect(page.locator(route.ready).first()).toBeVisible({ timeout: 15_000 });
      await waitForStablePaint(page);
      const results = await new AxeBuilder({ page })
        .withTags(['wcag2a', 'wcag2aa', 'wcag21a', 'wcag21aa'])
        .analyze();
      const blocking = results.violations.filter((v) =>
        v.impact === 'serious' || v.impact === 'critical');
      const summary = blocking.map((v) => ({
        id: v.id,
        impact: v.impact,
        nodes: v.nodes.map((n) => ({
          target: n.target.join(' '),
          html: n.html,
          failure: n.failureSummary,
        })),
      }));
      expect(summary).toEqual([]);
    });
  }

  test('A11Y-light: light theme has no serious or critical WCAG A/AA violations', async ({ page }) => {
    await page.evaluate(() => localStorage.setItem('tt-theme', 'light'));
    await page.reload();
    await expect(page.locator('.page-title')).toBeVisible({ timeout: 15_000 });
    await expect(page.locator('html')).toHaveAttribute('data-theme', 'light');
    await waitForStablePaint(page);
    const results = await new AxeBuilder({ page })
      .withTags(['wcag2a', 'wcag2aa', 'wcag21a', 'wcag21aa'])
      .analyze();
    const summary = results.violations
      .filter((v) => v.impact === 'serious' || v.impact === 'critical')
      .map((v) => ({ id: v.id, nodes: v.nodes.map((n) => ({
        target: n.target.join(' '), html: n.html, failure: n.failureSummary,
      })) }));
    expect(summary).toEqual([]);
  });
});
