import { test, expect, Page } from '@playwright/test';
import { loginAs } from '../fixtures/auth';

const BASE = 'http://localhost:8000';

const TAG = `QT-${Date.now().toString(36)}`;

// qTest test-case JSON: attributes live in a properties array; a
// test_case_version_id / pid+properties marker makes it auto-detect as qtest.
function qtestExport(prefix: string): string {
  return JSON.stringify({
    items: [
      {
        pid: `${prefix}-1`,
        name: `${TAG} ${prefix} login`,
        test_case_version_id: 1,
        properties: [
          { field_name: 'Priority', field_value_name: 'High' },
          { field_name: 'Module', field_value: '/QTestE2E/Auth' },
          { field_name: 'Automation', field_value_name: 'No' },
        ],
      },
      {
        pid: `${prefix}-2`,
        name: `${TAG} ${prefix} api check`,
        test_case_version_id: 1,
        properties: [
          { field_name: 'Priority', field_value_name: 'Low' },
          { field_name: 'Module', field_value: '/QTestE2E/Api' },
          { field_name: 'Automation', field_value_name: 'Yes' },
        ],
      },
    ],
  });
}

async function token(page: Page): Promise<string> {
  return page.evaluate(() => localStorage.getItem('th_token') || '');
}

async function gotoImport(page: Page) {
  await page.click('.nav-item:has-text("Import")');
  await page.waitForURL('**/#/import', { timeout: 5000 });
}

async function dropFile(page: Page, name: string, body: string) {
  await page.locator('input[type="file"]').setInputFiles({
    name,
    mimeType: 'application/json',
    buffer: Buffer.from(body, 'utf-8'),
  });
}

async function importFile(page: Page, name: string, body: string) {
  await gotoImport(page);
  await dropFile(page, name, body);
  const [exec] = await Promise.all([
    page.waitForResponse(r => r.url().includes('/api/import/execute')),
    page.click('button:has-text("Import")'),
  ]);
  return exec;
}

test.describe('Suite 17 — Import (qTest JSON)', () => {
  test.beforeEach(async ({ page }) => {
    await loginAs(page, 'marco@acme.com'); // admin → write role
  });

  // IMPQ-01 · qTest JSON auto-detects + preview counts [P0]
  test('IMPQ-01: qTest JSON detected and previewed', async ({ page }) => {
    await gotoImport(page);
    const [detect] = await Promise.all([
      page.waitForResponse(r => r.url().includes('/api/import/detect')),
      dropFile(page, 'qtest.json', qtestExport('Q01')),
    ]);
    expect((await detect.json()).format).toBe('qtest');

    const [preview] = await Promise.all([
      page.waitForResponse(r => r.url().includes('/api/import/preview')),
      page.click('button:has-text("Preview")'),
    ]);
    const body = await preview.json();
    expect(body.format).toBe('qtest (json)');
    expect(body.tests).toBe(2);
  });

  // IMPQ-02 · qTest execute persists tests with module folders [P0]
  test('IMPQ-02: qTest import persists tests with folders', async ({ page }) => {
    const exec = await importFile(page, 'qtest.json', qtestExport('Q02'));
    const body = await exec.json();
    expect(exec.status()).toBe(200);
    expect(body.format).toBe('qtest');
    expect(body.imported.tests).toBe(2);
    await expect(page.getByText('Import complete')).toBeVisible({ timeout: 5000 });

    const res = await page.request.fetch(
      `${BASE}/api/tests?search=${encodeURIComponent(`${TAG} Q02 api check`)}`,
      { headers: { Authorization: `Bearer ${await token(page)}` } },
    );
    const found = (await res.json()).find((t: any) => t.title === `${TAG} Q02 api check`);
    expect(found).toBeTruthy();
    expect(found.type).toBe('automated'); // Automation = Yes
  });

  // IMPQ-03 · Re-import is idempotent (matched by pid) [P1]
  test('IMPQ-03: re-import of qTest cases skips duplicates', async ({ page }) => {
    const payload = qtestExport('Q03');
    const first = await importFile(page, 'qtest.json', payload);
    expect((await first.json()).imported.tests).toBe(2);

    const second = await importFile(page, 'qtest.json', payload);
    const body = await second.json();
    expect(body.imported.tests).toBe(0);
    expect(body.imported.skipped).toBeGreaterThanOrEqual(2);
  });
});
