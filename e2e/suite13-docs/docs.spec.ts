import { test, expect } from '@playwright/test';
import { loginAs } from '../fixtures/auth';

const BASE = 'http://localhost:8000';

test.describe('Suite 13 — Docs & API View', () => {

  // DOC-01 · Navigate to Docs page [P2]
  test('DOC-01: docs page loads with sidebar navigation', async ({ page }) => {
    await loginAs(page, 'marco@acme.com');
    await page.goto('/#/docs');
    await expect(page.locator('text=Docs & API').first()).toBeVisible({ timeout: 10000 });
    // All nav sections visible
    await expect(page.locator('button:has-text("Quickstart")')).toBeVisible();
    await expect(page.locator('button:has-text("REST API")')).toBeVisible();
    await expect(page.locator('button:has-text("CLI")')).toBeVisible();
    await expect(page.locator('button:has-text("SDKs")')).toBeVisible();
    await expect(page.locator('button:has-text("Webhooks")')).toBeVisible();
  });

  // DOC-02 · Quickstart section shows steps [P2]
  test('DOC-02: quickstart section renders code steps', async ({ page }) => {
    await loginAs(page, 'marco@acme.com');
    await page.goto('/#/docs');
    // Quickstart is default section
    await expect(page.locator('text=Start the server')).toBeVisible({ timeout: 8000 });
    await expect(page.locator('text=Get a token')).toBeVisible();
    await expect(page.locator('pre.code').first()).toBeVisible();
  });

  // DOC-03 · REST API section loads /openapi.json [P1]
  test('DOC-03: REST API section loads and displays endpoints from /openapi.json', async ({ page }) => {
    await loginAs(page, 'marco@acme.com');
    await page.goto('/#/docs');
    await page.click('button:has-text("REST API")');

    // Wait for spec to load
    await expect(page.locator('text=REST API').first()).toBeVisible({ timeout: 5000 });
    // Tab groups should appear (tests, runs, etc.)
    await expect(page.locator('button.tab').first()).toBeVisible({ timeout: 10000 });
    // At least one endpoint card
    await expect(page.locator('div[style*="border: 1px solid"]').first()).toBeVisible({ timeout: 10000 });

    // Also verify /openapi.json is accessible
    const res = await page.request.get(`${BASE}/openapi.json`);
    expect(res.status()).toBe(200);
    const spec = await res.json();
    expect(spec.paths).toBeTruthy();
    expect(Object.keys(spec.paths).length).toBeGreaterThan(5);
  });

  // DOC-04 · REST API — espandi endpoint card [P2]
  test('DOC-04: clicking endpoint card expands details', async ({ page }) => {
    await loginAs(page, 'marco@acme.com');
    await page.goto('/#/docs');
    await page.click('button:has-text("REST API")');

    // Wait for endpoint cards
    await expect(page.locator('button').filter({ hasText: '/api/tests' }).first()).toBeVisible({ timeout: 10000 });

    // Click first endpoint to expand
    const firstEndpoint = page.locator('button').filter({ hasText: '/api/tests' }).first();
    await firstEndpoint.click();

    // Details should appear (path params, query params, or response)
    await expect(page.locator('text=/Path params|Query params|Request body|Response/i').first()).toBeVisible({ timeout: 5000 });
  });

  // DOC-05 · REST API — tab navigation [P1]
  test('DOC-05: REST API tab navigation switches endpoint groups', async ({ page }) => {
    await loginAs(page, 'marco@acme.com');
    await page.goto('/#/docs');
    await page.click('button:has-text("REST API")');

    await expect(page.locator('button.tab').first()).toBeVisible({ timeout: 10000 });

    // Click "runs" tab
    const runsTab = page.locator('button.tab:has-text("runs")');
    if (await runsTab.count() > 0) {
      await runsTab.click();
      // Should show runs-related endpoints
      await expect(page.getByText('/api/runs', { exact: false }).first()).toBeVisible({ timeout: 5000 });
    }

    // Click "defects" tab
    const defectsTab = page.locator('button.tab:has-text("defects")');
    if (await defectsTab.count() > 0) {
      await defectsTab.click();
      await expect(page.getByText('/api/defects', { exact: false }).first()).toBeVisible({ timeout: 5000 });
    }
  });

  // DOC-06 · CLI section — copy command [P2]
  test('DOC-06: CLI section shows commands and copy works', async ({ page }) => {
    await loginAs(page, 'marco@acme.com');
    await page.goto('/#/docs');
    await page.click('button:has-text("CLI")');

    await expect(page.locator('text=thorotest run').first()).toBeVisible({ timeout: 8000 });
    await expect(page.locator('text=thorotest sync').first()).toBeVisible();

    // Click first command to copy
    await page.context().grantPermissions(['clipboard-write', 'clipboard-read']);
    const firstCmd = page.locator('button:has-text("thorotest run")').first();
    await firstCmd.click();
    // "copy" text changes to "✓ copied" momentarily
    await expect(page.locator('text=✓ copied').first()).toBeVisible({ timeout: 3000 });
  });

  // DOC-07 · SDKs section renders code snippets [P2]
  test('DOC-07: SDKs section shows TypeScript, Python, Go snippets', async ({ page }) => {
    await loginAs(page, 'marco@acme.com');
    await page.goto('/#/docs');
    await page.click('button:has-text("SDKs")');

    await expect(page.locator('text=TypeScript / JavaScript')).toBeVisible({ timeout: 8000 });
    await expect(page.locator('text=Python')).toBeVisible();
    await expect(page.locator('text=Go').first()).toBeVisible();
    await expect(page.locator('pre.code').first()).toBeVisible();
  });

  // DOC-08 · Webhooks section — copy event name [P2]
  test('DOC-08: webhooks section shows events and copy works', async ({ page }) => {
    await loginAs(page, 'marco@acme.com');
    await page.goto('/#/docs');
    await page.click('button:has-text("Webhooks")');

    await expect(page.locator('text=run.completed').first()).toBeVisible({ timeout: 8000 });
    await expect(page.locator('text=defect.created')).toBeVisible();

    // Click to copy an event name
    await page.context().grantPermissions(['clipboard-write', 'clipboard-read']);
    await page.click('button:has-text("run.completed")');
    await expect(page.locator('text=✓ copied').first()).toBeVisible({ timeout: 3000 });
  });

  // DOC-09 · Docs accessible via sidebar [P2]
  test('DOC-09: docs accessible from sidebar navigation', async ({ page }) => {
    await loginAs(page, 'marco@acme.com');
    // Find and click Docs link in sidebar
    await page.click('text=Docs');
    await page.waitForURL('**/#/docs', { timeout: 8000 });
    await expect(page.locator('text=Docs & API').first()).toBeVisible({ timeout: 5000 });
  });

  // DOC-10 · API — /openapi.json structure [P1]
  test('DOC-10: /openapi.json has expected API structure', async ({ page }) => {
    await loginAs(page, 'marco@acme.com');
    const token = await page.evaluate(() => localStorage.getItem('th_token'));

    const res = await page.request.get(`${BASE}/openapi.json`);
    expect(res.status()).toBe(200);
    const spec = await res.json();

    // Verify key paths exist
    expect(spec.paths['/api/tests']).toBeTruthy();
    expect(spec.paths['/api/runs']).toBeTruthy();
    expect(spec.paths['/api/defects']).toBeTruthy();
    expect(spec.paths['/api/auth/login']).toBeTruthy();
    expect(spec.paths['/api/me']).toBeTruthy();

    // Verify components/schemas
    expect(spec.components?.schemas).toBeTruthy();
    expect(spec.components.schemas['TestOut']).toBeTruthy();
    expect(spec.components.schemas['RunOut']).toBeTruthy();
    expect(spec.components.schemas['DefectOut']).toBeTruthy();
  });

});
