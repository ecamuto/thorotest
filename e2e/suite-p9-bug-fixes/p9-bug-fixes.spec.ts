import { test, expect } from '@playwright/test';
import { loginAs } from '../fixtures/auth';

const BASE = 'http://localhost:8000';

// Hardcoded bug IDs that were in the view-config.jsx stub (must never appear from real API)
const STUB_IDS = ['BUG-441', 'BUG-440', 'BUG-438'];

test.describe('Suite P9 — Pre-existing Bug Fixes', () => {

  // P9-01: Defects stub removed — view renders real API data, not hardcoded rows
  test('P9-01: Defects view shows real API data — stub rows absent', async ({ page }) => {
    const jsErrors: string[] = [];
    page.on('pageerror', err => jsErrors.push(err.message));

    // Intercept /api/defects and return an empty list to isolate UI from DB state
    await page.route('**/api/defects**', route =>
      route.fulfill({ status: 200, contentType: 'application/json', body: '[]' })
    );

    await loginAs(page, 'marco@acme.com');
    await page.goto('/#/defects');
    await expect(page.locator('h1, .page-title').filter({ hasText: /defects/i }).first()).toBeVisible({ timeout: 10000 });

    // Stub rows must NOT be present — if they appear the stub is back
    for (const id of STUB_IDS) {
      await expect(page.locator(`text=${id}`)).not.toBeVisible();
    }

    // No ReferenceError (window.Defects must resolve to the real component)
    const refErrors = jsErrors.filter(e => e.includes('ReferenceError') || e.includes('Defects is not defined'));
    expect(refErrors).toHaveLength(0);
  });

  // P9-02: Defects view calls /api/defects (real component network behaviour)
  test('P9-02: Defects view fires GET /api/defects request on load', async ({ page }) => {
    let defectsCalled = false;
    await page.route('**/api/defects**', async route => {
      defectsCalled = true;
      await route.fulfill({ status: 200, contentType: 'application/json', body: '[]' });
    });

    await loginAs(page, 'marco@acme.com');
    await page.goto('/#/defects');
    await expect(page.locator('h1, .page-title').filter({ hasText: /defects/i }).first()).toBeVisible({ timeout: 10000 });

    expect(defectsCalled).toBe(true);
  });

  // P9-03: POST /api/ai/suggest-edge-cases with folder_id=null returns 422 with friendly message
  test('P9-03: suggest-edge-cases with folder_id=null returns 422 folder_id required', async ({ page }) => {
    await loginAs(page, 'marco@acme.com');
    const token = await page.evaluate(() => localStorage.getItem('th_token'));

    const res = await page.request.post(`${BASE}/api/ai/suggest-edge-cases`, {
      data: { folder_id: null },
      headers: { Authorization: `Bearer ${token}`, 'Content-Type': 'application/json' },
    });

    expect(res.status()).toBe(422);
    const body = await res.json();
    // Application-level null guard fires — not an opaque Pydantic schema error
    expect(body.detail).toBe('folder_id is required');
  });

});
