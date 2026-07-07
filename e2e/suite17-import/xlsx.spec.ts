import { test, expect, Page } from '@playwright/test';
import { readFileSync } from 'fs';
import { join } from 'path';
import { loginAs } from '../fixtures/auth';

const BASE = 'http://localhost:8000';

// .xlsx is a binary (zip) format, so the fixture is a committed file rather
// than generated inline. Titles are static (prefix XLSXFIX), so assertions
// tolerate a reused dev server where a prior run already imported them.
const XLSX = readFileSync(join(__dirname, 'fixtures', 'import-sample.xlsx'));

async function token(page: Page): Promise<string> {
  return page.evaluate(() => localStorage.getItem('th_token') || '');
}

async function gotoImport(page: Page) {
  await page.click('.nav-item:has-text("Import")');
  await page.waitForURL('**/#/import', { timeout: 5000 });
}

async function dropXlsx(page: Page) {
  await page.locator('input[type="file"]').setInputFiles({
    name: 'import-sample.xlsx',
    mimeType: 'application/vnd.openxmlformats-officedocument.spreadsheetml.sheet',
    buffer: XLSX,
  });
}

test.describe('Suite 17 — Import (Excel .xlsx)', () => {
  test.beforeEach(async ({ page }) => {
    await loginAs(page, 'marco@acme.com'); // admin → write role
  });

  // IMPX-XL-01 · .xlsx auto-detects and shows column mapping [P0]
  test('IMPXL-01: xlsx detected and column mapping shown', async ({ page }) => {
    await gotoImport(page);
    const [detect] = await Promise.all([
      page.waitForResponse(r => r.url().includes('/api/import/detect')),
      dropXlsx(page),
    ]);
    const body = await detect.json();
    expect(body.format).toBe('xlsx');
    expect(body.csv_meta.headers).toContain('Title');
    await expect(page.locator('.card-title:has-text("Column mapping")')).toBeVisible({ timeout: 5000 });
  });

  // IMPXL-02 · xlsx preview parses rows (binary read works) [P0]
  test('IMPXL-02: xlsx preview parses the worksheet', async ({ page }) => {
    await gotoImport(page);
    await dropXlsx(page);
    const [preview] = await Promise.all([
      page.waitForResponse(r => r.url().includes('/api/import/preview')),
      page.click('button:has-text("Preview")'),
    ]);
    const body = await preview.json();
    expect(body.format).toMatch(/^xlsx/);
    expect(body.tests).toBe(2);
  });

  // IMPXL-03 · xlsx execute persists tests [P1]
  test('IMPXL-03: xlsx import persists tests', async ({ page }) => {
    await gotoImport(page);
    await dropXlsx(page);
    const [exec] = await Promise.all([
      page.waitForResponse(r => r.url().includes('/api/import/execute')),
      page.click('button:has-text("Import")'),
    ]);
    const body = await exec.json();
    expect(exec.status()).toBe(200);
    expect(body.format).toBe('xlsx');
    // Tolerate a reused server: either freshly imported or already present.
    expect(body.imported.tests + body.imported.skipped).toBeGreaterThanOrEqual(2);
    await expect(page.getByText('Import complete')).toBeVisible({ timeout: 5000 });

    const res = await page.request.fetch(
      `${BASE}/api/tests?search=${encodeURIComponent('XLSXFIX checkout')}`,
      { headers: { Authorization: `Bearer ${await token(page)}` } },
    );
    const found = (await res.json()).find((t: any) => t.title === 'XLSXFIX checkout');
    expect(found).toBeTruthy();
    expect(found.type).toBe('automated');
  });
});
