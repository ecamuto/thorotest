import { test, expect, Page } from '@playwright/test';
import { loginAs } from '../fixtures/auth';

const BASE = 'http://localhost:8000';

// Unique suffix so re-runs against a reused dev server don't collide on
// titles or Xray issue keys.
const TAG = `XR-${Date.now().toString(36)}`;

// Xray test-definition array (testtype marker → auto-detected as xray).
function xrayDefs(prefix: string): string {
  return JSON.stringify([
    {
      testtype: 'Manual',
      key: `${prefix}-1`,
      xray_test_repository_folder: '/XrayE2E/Auth',
      fields: { summary: `${TAG} ${prefix} login`, priority: { name: 'High' }, labels: ['smoke'] },
    },
    {
      testtype: 'Automated',
      key: `${prefix}-2`,
      xray_test_repository_folder: '/XrayE2E/Api',
      fields: { summary: `${TAG} ${prefix} api check` },
    },
  ]);
}

// Xray execution-results object referencing test keys.
function xrayResults(prefix: string): string {
  return JSON.stringify({
    info: { summary: `${TAG} ${prefix} run`, testExecutionKey: `${prefix}-EX1` },
    tests: [
      { testKey: `${prefix}-1`, status: 'PASS' },
      { testKey: `${prefix}-2`, status: 'FAIL' },
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
  // Reload to remount the import view — after a completed import it stays on
  // the "complete" state with no file input, so a fresh mount is needed.
  await page.reload();
  await gotoImport(page);
  await dropFile(page, name, body);
  const [exec] = await Promise.all([
    page.waitForResponse(r => r.url().includes('/api/import/execute')),
    page.click('button:has-text("Import")'),
  ]);
  return exec;
}

test.describe('Suite 17 — Import (Xray JSON)', () => {
  test.beforeEach(async ({ page }) => {
    await loginAs(page, 'marco@acme.com'); // admin → write role
  });

  // IMPX-01 · Xray test definitions auto-detect + preview counts [P0]
  test('IMPX-01: Xray test definitions detected and previewed', async ({ page }) => {
    await gotoImport(page);
    const [detect] = await Promise.all([
      page.waitForResponse(r => r.url().includes('/api/import/detect')),
      dropFile(page, 'xray.json', xrayDefs('X01')),
    ]);
    expect((await detect.json()).format).toBe('xray');

    const [preview] = await Promise.all([
      page.waitForResponse(r => r.url().includes('/api/import/preview')),
      page.click('button:has-text("Preview")'),
    ]);
    const body = await preview.json();
    expect(body.format).toBe('xray (json)');
    expect(body.tests).toBe(2);
  });

  // IMPX-02 · Xray definitions execute persists tests with folders [P0]
  test('IMPX-02: Xray definitions import persists tests', async ({ page }) => {
    const exec = await importFile(page, 'xray.json', xrayDefs('X02'));
    const body = await exec.json();
    expect(exec.status()).toBe(200);
    expect(body.format).toBe('xray');
    expect(body.imported.tests).toBe(2);
    await expect(page.getByText('Import complete')).toBeVisible({ timeout: 5000 });

    const res = await page.request.fetch(
      `${BASE}/api/tests?search=${encodeURIComponent(`${TAG} X02 login`)}`,
      { headers: { Authorization: `Bearer ${await token(page)}` } },
    );
    expect((await res.json()).some((t: any) => t.title === `${TAG} X02 login`)).toBeTruthy();
  });

  // IMPX-03 · Results file links to previously imported tests [P0]
  test('IMPX-03: Xray results link to imported definitions and create a run', async ({ page }) => {
    // Import definitions first, then execution results referencing their keys.
    await importFile(page, 'xray-defs.json', xrayDefs('X03'));
    const exec = await importFile(page, 'xray-results.json', xrayResults('X03'));
    const body = await exec.json();
    expect(exec.status()).toBe(200);
    expect(body.imported.runs).toBe(1);
    await expect(page.getByText('Import complete')).toBeVisible({ timeout: 5000 });

    // The run exists and its cases resolved to the imported tests.
    const res = await page.request.fetch(`${BASE}/api/runs`, {
      headers: { Authorization: `Bearer ${await token(page)}` },
    });
    const run = (await res.json()).find((r: any) => (r.name || '').includes(`${TAG} X03 run`));
    expect(run).toBeTruthy();
    expect(run.total).toBe(2);
    expect(run.passed).toBe(1);
    expect(run.failed).toBe(1);
  });

  // IMPX-04 · Re-importing definitions is idempotent [P1]
  test('IMPX-04: re-import of Xray definitions skips duplicates', async ({ page }) => {
    const defs = xrayDefs('X04');
    const first = await importFile(page, 'xray.json', defs);
    expect((await first.json()).imported.tests).toBe(2);

    await page.reload();
    const second = await importFile(page, 'xray.json', defs);
    const body = await second.json();
    expect(body.imported.tests).toBe(0);
    expect(body.imported.skipped).toBeGreaterThanOrEqual(2);
  });
});
