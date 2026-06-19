import { test, expect } from '@playwright/test';
import { loginAs } from '../fixtures/auth';

test.describe('Suite 2 — Navigazione e Routing', () => {

  test.beforeEach(async ({ page }) => {
    await loginAs(page, 'marco@acme.com');
  });

  // E2E-NAV-01 · Hash routing sidebar [P0]
  test('NAV-01: hash routing sidebar', async ({ page }) => {
    const items: { label: string; hash: string; screen: string }[] = [
      { label: 'Overview',       hash: '#/overview',   screen: 'overview' },
      { label: 'Test library',   hash: '#/library',    screen: 'library' },
      { label: 'Runs & plans',   hash: '#/runs',       screen: 'runs' },
      { label: 'CI pipelines',   hash: '#/pipelines',  screen: 'pipelines' },
      { label: 'Insights',       hash: '#/insights',   screen: 'insights' },
    ];

    for (const item of items) {
      await page.click(`.nav-item:has-text("${item.label}")`);
      await expect(page).toHaveURL(new RegExp(item.hash.replace('/', '\\/')), { timeout: 5000 });
      await expect(page.locator('.app')).toHaveAttribute('data-screen-label', item.screen);
    }
  });

  // E2E-NAV-02 · Deep link diretto [P1]
  test('NAV-02: deep link diretto test e run', async ({ page }) => {
    // Deep link to test
    await page.goto('/#/tests/TC-2301');
    await page.waitForURL('**/#/tests/TC-2301', { timeout: 10000 });
    await expect(page.locator('.app')).toHaveAttribute('data-screen-label', 'test-detail');
    // Auto-retries until the detail view finishes loading (no fixed-read race)
    await expect(page.locator('.app')).toContainText('TC-2301', { timeout: 10000 });

    // Deep link to run
    await page.goto('/#/runs/R-1287');
    await page.waitForURL('**/#/runs/R-1287', { timeout: 10000 });
    await expect(page.locator('.app')).toHaveAttribute('data-screen-label', 'run-detail');
    await expect(page.locator('.app')).toContainText('R-1287', { timeout: 10000 });
  });

  // E2E-NAV-03 · Back/Forward browser [P1]
  test('NAV-03: back/forward browser', async ({ page }) => {
    // Overview → Library
    await page.click('.nav-item:has-text("Test library")');
    await page.waitForURL('**/#/library', { timeout: 5000 });

    // Library → TestDetail TC-1042 (click the ID cell — the row centre lands on
    // the interactive status badge, which stops propagation and won't navigate)
    await page.click('td.mono:has-text("TC-1042")');
    await page.waitForURL('**/#/tests/TC-1042', { timeout: 10000 });
    await expect(page.locator('.app')).toHaveAttribute('data-screen-label', 'test-detail');

    // Back → Library
    await page.goBack();
    await page.waitForURL('**/#/library', { timeout: 5000 });
    await expect(page.locator('.app')).toHaveAttribute('data-screen-label', 'library');

    // Forward → TC-1042
    await page.goForward();
    await page.waitForURL('**/#/tests/TC-1042', { timeout: 5000 });
    await expect(page.locator('.app')).toHaveAttribute('data-screen-label', 'test-detail');
  });

  // E2E-NAV-04 · Breadcrumb cliccabile [P1]
  test('NAV-04: breadcrumb cliccabile', async ({ page }) => {
    // Navigate to TestDetail
    await page.goto('/#/tests/TC-1042');
    await page.waitForURL('**/#/tests/TC-1042', { timeout: 10000 });

    // Click breadcrumb back to Library
    await page.click('.breadcrumb .crumb-link:has-text("Test library"), .btn.ghost.sm:has-text("Library")');
    await page.waitForURL('**/#/library', { timeout: 5000 });
    await expect(page.locator('.app')).toHaveAttribute('data-screen-label', 'library');

    // Navigate to RunDetail
    await page.goto('/#/runs/R-1287');
    await page.waitForURL('**/#/runs/R-1287', { timeout: 10000 });

    // Click breadcrumb back to Runs
    await page.click('.btn.ghost.sm:has-text("Runs"), .breadcrumb .crumb-link:has-text("Runs")');
    await page.waitForURL('**/#/runs', { timeout: 5000 });
    await expect(page.locator('.app')).toHaveAttribute('data-screen-label', 'runs');
  });

  // E2E-NAV-05 · Apertura in nuova scheda [P2]
  test('NAV-05: apertura in nuova scheda', async ({ page, context }) => {
    // Right-click Runs nav item and open in new tab
    const [newPage] = await Promise.all([
      context.waitForEvent('page'),
      page.click('.nav-item:has-text("Runs & plans")', { button: 'middle' }),
    ]);
    await newPage.waitForLoadState('domcontentloaded');
    await expect(newPage).toHaveURL(new RegExp('#/runs'), { timeout: 10000 });

    // Authenticated — no login page
    await expect(newPage.locator('.login-page')).toHaveCount(0);
    await newPage.close();
  });

});
