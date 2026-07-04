import { test, expect } from '@playwright/test';
import { loginAs } from '../fixtures/auth';

const BASE = 'http://localhost:8000';

// Match /api/insights exactly — NOT sub-resources like /api/insights/test-health,
// which the Overview page also fires and which lacks the aggregate KPI fields.
const isInsightsResponse = (r: { url(): string }) => /\/api\/insights(\?|$)/.test(r.url());

test.describe('Suite 6 — Overview & Insights', () => {

  test.beforeEach(async ({ page }) => {
    await loginAs(page, 'marco@acme.com');
  });

  // E2E-OVR-01 · KPI Overview da dati reali [P1]
  test('OVR-01: KPI Overview da dati reali', async ({ page }) => {
    // Navigate to Overview and capture /api/insights
    const [response] = await Promise.all([
      page.waitForResponse(isInsightsResponse),
      page.click('.nav-item:has-text("Overview")'),
    ]);

    await page.waitForURL('**/#/overview', { timeout: 5000 });
    expect(response.status()).toBe(200);

    const data = await response.json();

    // KPI cards should reflect API data
    const metricValues = await page.locator('.metric-value').allTextContents();
    const allText = metricValues.join(' ');

    // pass_rate
    if (data.pass_rate !== undefined) {
      expect(allText).toContain(String(data.pass_rate));
    }
    // total_tests
    if (data.total_tests !== undefined) {
      expect(allText).toContain(String(data.total_tests));
    }
  });

  // E2E-OVR-02 · Insights — folder coverage [P1]
  test('OVR-02: Insights folder coverage', async ({ page }) => {
    const [response] = await Promise.all([
      page.waitForResponse(isInsightsResponse),
      page.click('.nav-item:has-text("Insights")'),
    ]);

    await page.waitForURL('**/#/insights', { timeout: 5000 });
    expect(response.status()).toBe(200);

    const data = await response.json();
    expect(data.folder_coverage).toBeDefined();
    expect(Array.isArray(data.folder_coverage)).toBeTruthy();

    // Coverage section visible
    await expect(page.locator('.card-title:has-text("Coverage by area")')).toBeVisible({ timeout: 5000 });
  });

  // E2E-OVR-03 · Insights — top flaky [P1]
  test('OVR-03: Insights top flaky tests', async ({ page }) => {
    const [response] = await Promise.all([
      page.waitForResponse(isInsightsResponse),
      page.click('.nav-item:has-text("Insights")'),
    ]);

    await page.waitForURL('**/#/insights', { timeout: 5000 });
    expect(response.status()).toBe(200);

    const data = await response.json();
    expect(data.top_flaky).toBeDefined();

    // TC-1045 should appear in flaky section
    await expect(page.locator('.card-title:has-text("Top 5 flaky tests"), .card-title:has-text("flaky")')).toBeVisible({ timeout: 5000 });
    await expect(page.locator('.app')).toContainText('TC-1045', { timeout: 5000 });
  });

});
