import { test, expect } from '@playwright/test';
import { loginAs } from '../fixtures/auth';

const MOCK_GENERATE = [
  {
    title: 'E2E pending test — phase06 fixture',
    steps: [
      { action: 'Navigate to login page', expected_result: 'Login form is visible' },
      { action: 'Submit empty form', expected_result: 'Validation errors shown' },
    ],
  },
];

test.describe('Suite P6 — Phase 06 fixes', () => {
  test.beforeEach(async ({ page }) => {
    await loginAs(page, 'marco@acme.com');
  });

  // SC7-01: window.__currentFolderId set by Library → enables "Suggest edge cases" in AIAssistant
  test('P6-01 (SC7-01): suggest-edge-cases button enabled after folder selected in Library', async ({ page }) => {
    // 1. Go to Library and select a folder
    await page.goto('/#/library');
    await page.waitForURL('**/#/library', { timeout: 10000 });
    await expect(page.locator('.table tr td.mono').first()).toBeVisible({ timeout: 10000 });

    // Click "Login flows" folder (auth-login) — sets window.__currentFolderId = "auth-login"
    await page.locator('.tree-row:has-text("Login flows")').click();
    await page.waitForTimeout(300);

    // Verify side effect was applied
    const folderId = await page.evaluate(() => (window as any).__currentFolderId);
    expect(folderId).toBe('auth-login');

    // 2. Navigate to AI view — app.jsx passes window.__currentFolderId as currentFolderId prop
    await page.goto('/#/ai');
    await page.waitForSelector('.card-title', { timeout: 10000 });

    // 3. Switch to "Suggest edge cases" panel
    await page.click('button.btn.sm:has-text("Suggest edge cases")');
    await expect(page.locator('.card-title:has-text("Suggest edge cases")')).toBeVisible({ timeout: 5000 });

    // 4. Primary "Suggest edge cases" action button must be ENABLED (folder is known)
    const suggestBtn = page.locator('button.btn.primary:not(.sm):has-text("Suggest edge cases")');
    await expect(suggestBtn).toBeEnabled({ timeout: 3000 });

    // "Navigate to a folder first" warning must NOT appear
    await expect(page.locator('text=Navigate to a folder first')).not.toBeVisible();
  });

  // SC2-04 + SC3-01: AI-generated tests saved with status "pending"; folder_id sent as string (no parseInt)
  test('P6-02 (SC2-04/SC3-01): generated tests saved as pending, visible in Library pending filter', async ({ page }) => {
    // Mock AI endpoint — no real Anthropic key required
    await page.route('**/api/ai/generate-tests', async route => {
      await route.fulfill({
        status: 200,
        contentType: 'application/json',
        body: JSON.stringify(MOCK_GENERATE),
      });
    });

    // Intercept createTest POST to verify payload shape
    let capturedCreateBody: any = null;
    let createdId: string | null = null;
    await page.route('**/api/tests', async route => {
      if (route.request().method() !== 'POST') { await route.continue(); return; }
      capturedCreateBody = await route.request().postDataJSON();
      // Let real request through so test lands in DB (for pending-filter check)
      await route.continue();
    });

    // 1. Select a folder in Library first (sets window.__currentFolderId)
    await page.goto('/#/library');
    await page.waitForURL('**/#/library', { timeout: 10000 });
    await expect(page.locator('.table tr td.mono').first()).toBeVisible({ timeout: 10000 });
    await page.locator('.tree-row:has-text("Login flows")').click();
    await page.waitForTimeout(300);

    // 2. Navigate to AI view
    await page.goto('/#/ai');
    await page.waitForSelector('textarea.textarea', { timeout: 10000 });

    // 3. Generate tests
    await page.locator('textarea.textarea').fill('Login edge cases for phase06 E2E test');
    const generateBtn = page.locator('button.btn.primary:not(.sm):has-text("Generate")');
    await expect(generateBtn).toBeEnabled({ timeout: 3000 });
    await generateBtn.click();

    await expect(page.locator('text=E2E pending test — phase06 fixture')).toBeVisible({ timeout: 5000 });

    // 4. Save selected — real POST to DB
    const saveBtn = page.locator('button:has-text("Save selected")');
    await expect(saveBtn).toBeEnabled({ timeout: 3000 });

    const [createResp] = await Promise.all([
      page.waitForResponse(r => r.url().includes('/api/tests') && r.request().method() === 'POST'),
      saveBtn.click(),
    ]);

    // Verify POST body: status must be "pending", folder_id must be a string (not NaN)
    await expect.poll(() => capturedCreateBody).not.toBeNull();
    expect(capturedCreateBody.status).toBe('pending');
    expect(capturedCreateBody.folder_id).toBe('auth-login');
    expect(capturedCreateBody.folder_id).not.toBeNaN();

    // Extract created test ID for library check
    const createBody = await createResp.json();
    createdId = createBody.id;
    expect(typeof createdId).toBe('string');

    // 5. Go to Library and filter by "pending" — test must appear
    await page.goto('/#/library');
    await page.waitForURL('**/#/library', { timeout: 10000 });
    await expect(page.locator('.table tr td.mono').first()).toBeVisible({ timeout: 10000 });

    // Open status filter and select "pending"
    // Use waitForResponse + click pattern; .first() targets dropdown item (DOM-order before table rows)
    const [pendingResp] = await Promise.all([
      page.waitForResponse(r => r.url().includes('/api/tests') && r.url().includes('status=pending')),
      (async () => {
        await page.click('.chip:has-text("Status")');
        await page.waitForTimeout(300);
        await page.locator('span.status.skip:has-text("PENDING")').first().click();
      })(),
    ]);
    expect(pendingResp.status()).toBe(200);

    // Newly created test must appear in pending filter
    await expect(page.locator(`.table td.mono:has-text("${createdId}")`)).toBeVisible({ timeout: 8000 });

    // Cleanup — delete the created test so subsequent runs stay clean
    const token = await page.evaluate(() => (window as any).localStorage.getItem('th_token'));
    await page.evaluate(async ({ id, t }: { id: string; t: string }) => {
      await fetch(`/api/tests/${id}`, { method: 'DELETE', headers: { Authorization: `Bearer ${t}` } });
    }, { id: createdId!, t: token });
  });
});
