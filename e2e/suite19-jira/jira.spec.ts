import { test, expect } from '@playwright/test';
import { loginAs } from '../fixtures/auth';

const BASE = 'http://localhost:8000';

async function token(page: any): Promise<string> {
  return await page.evaluate(() => localStorage.getItem('th_token') ?? '');
}

test.describe('Suite 19 — Jira integration (no live Jira)', () => {

  test.afterEach(async ({ page }) => {
    // Clean up any jira integration this suite created
    const t = await token(page).catch(() => '');
    if (t) {
      await page.request.delete(`${BASE}/api/integrations/int-jira-e2e`, { headers: { Authorization: `Bearer ${t}` } }).catch(() => {});
    }
  });

  // JIRA-01 · Integration create redacts api_token [P1]
  test('JIRA-01: creating a jira integration never returns api_token', async ({ page }) => {
    await loginAs(page, 'marco@acme.com');
    const t = await token(page);
    const res = await page.request.post(`${BASE}/api/integrations`, {
      data: {
        id: 'int-jira-e2e', name: 'Jira E2E', type: 'jira',
        config: { base_url: 'https://acme.atlassian.net', email: 'e@e.com', api_token: 'SECRET_E2E', project_key: 'PAY' },
      },
      headers: { Authorization: `Bearer ${t}`, 'Content-Type': 'application/json' },
    });
    expect(res.status()).toBe(201);
    const cfg = (await res.json()).config;
    expect(cfg.api_token).toBe('');
    expect(cfg.api_token_set).toBe(true);
  });

  // JIRA-02 · Secret not leaked in list [P1]
  test('JIRA-02: api_token not present in GET /api/integrations', async ({ page }) => {
    await loginAs(page, 'marco@acme.com');
    const t = await token(page);
    await page.request.post(`${BASE}/api/integrations`, {
      data: {
        id: 'int-jira-e2e', name: 'Jira E2E', type: 'jira',
        config: { base_url: 'https://acme.atlassian.net', email: 'e@e.com', api_token: 'SECRET_E2E', project_key: 'PAY' },
      },
      headers: { Authorization: `Bearer ${t}`, 'Content-Type': 'application/json' },
    });
    const list = await page.request.get(`${BASE}/api/integrations`, { headers: { Authorization: `Bearer ${t}` } });
    expect(JSON.stringify(await list.json())).not.toContain('SECRET_E2E');
  });

  // JIRA-03 · Push unknown defect → 404 [P2]
  test('JIRA-03: push unknown defect returns 404', async ({ page }) => {
    await loginAs(page, 'marco@acme.com');
    const t = await token(page);
    const res = await page.request.post(`${BASE}/api/defects/BUG-NOPE-XYZ/push`, { headers: { Authorization: `Bearer ${t}` } });
    expect(res.status()).toBe(404);
  });

  // JIRA-04 · Jira appears in the add-integration picker [P2]
  test('JIRA-04: Jira is offered as an integration provider', async ({ page }) => {
    await loginAs(page, 'marco@acme.com');
    await page.goto('/#/integrations');
    await expect(page.locator('h1:has-text("Integrations")')).toBeVisible({ timeout: 10000 });
    await page.click('button:has-text("Add integration")');
    await expect(page.locator('button:has-text("Jira")')).toBeVisible({ timeout: 8000 });
  });

  // JIRA-05 · Jira config form renders its fields [P2]
  test('JIRA-05: Jira config form shows base URL + project key + API token', async ({ page }) => {
    await loginAs(page, 'marco@acme.com');
    await page.goto('/#/integrations');
    await expect(page.locator('h1:has-text("Integrations")')).toBeVisible({ timeout: 10000 });
    await page.click('button:has-text("Add integration")');
    await page.click('button:has-text("Jira")');
    await expect(page.locator('input[placeholder="https://your-org.atlassian.net"]')).toBeVisible({ timeout: 8000 });
    await expect(page.locator('input[placeholder="PAY"]')).toBeVisible();
    await expect(page.locator('input[placeholder="Atlassian API token"]')).toBeVisible();
  });

  // JIRA-06 · Defects view exposes a Tracker column with Push to Jira [P2]
  test('JIRA-06: defects view has a Push to Jira action', async ({ page }) => {
    await loginAs(page, 'marco@acme.com');
    await page.goto('/#/defects');
    await expect(page.locator('h1:has-text("Defects")')).toBeVisible({ timeout: 10000 });
    await expect(page.locator('th:has-text("Tracker")')).toBeVisible({ timeout: 8000 });
    await expect(page.locator('button:has-text("Push to Jira")').first()).toBeVisible({ timeout: 8000 });
  });
});
