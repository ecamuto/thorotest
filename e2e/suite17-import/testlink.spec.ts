import { test, expect, Page } from '@playwright/test';
import { loginAs } from '../fixtures/auth';

const BASE = 'http://localhost:8000';

const TAG = `TL-${Date.now().toString(36)}`;

// TestLink nested-suite XML. importance/execution_type markers make it
// auto-detect as testlink (not junit).
function testlinkXml(prefix: string): string {
  return `<?xml version="1.0" encoding="UTF-8"?>
<testsuite name="TestLinkE2E">
  <testcase internalid="1" externalid="${prefix}-1" name="${TAG} ${prefix} login">
    <importance>3</importance>
    <execution_type>1</execution_type>
    <keywords><keyword name="smoke"/></keywords>
  </testcase>
  <testsuite name="Api">
    <testcase internalid="2" externalid="${prefix}-2" name="${TAG} ${prefix} api check">
      <importance>1</importance>
      <execution_type>2</execution_type>
    </testcase>
  </testsuite>
</testsuite>`;
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
    mimeType: 'application/xml',
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

test.describe('Suite 17 — Import (TestLink XML)', () => {
  test.beforeEach(async ({ page }) => {
    await loginAs(page, 'marco@acme.com'); // admin → write role
  });

  // IMPT-01 · TestLink XML auto-detects (not junit) + preview [P0]
  test('IMPT-01: TestLink XML detected and previewed', async ({ page }) => {
    await gotoImport(page);
    await dropFile(page, 'testlink.xml', testlinkXml('T01'));
    await expect(page.locator('button:has-text("TestLink XML")')).toBeVisible({ timeout: 5000 });
    const [preview] = await Promise.all([
      page.waitForResponse(r => r.url().includes('/api/import/preview')),
      page.click('button:has-text("Preview")'),
    ]);
    const body = await preview.json();
    expect(body.format).toBe('testlink_xml');
    expect(body.tests).toBe(2);
  });

  // IMPT-02 · Execute persists tests with nested-suite folders [P0]
  test('IMPT-02: TestLink import persists tests with nested folders', async ({ page }) => {
    const exec = await importFile(page, 'testlink.xml', testlinkXml('T02'));
    const body = await exec.json();
    expect(exec.status()).toBe(200);
    expect(body.format).toBe('testlink_xml');
    expect(body.imported.tests).toBe(2);
    await expect(page.getByText('Import complete')).toBeVisible({ timeout: 5000 });

    const res = await page.request.fetch(
      `${BASE}/api/tests?search=${encodeURIComponent(`${TAG} T02 api check`)}`,
      { headers: { Authorization: `Bearer ${await token(page)}` } },
    );
    const found = (await res.json()).find((t: any) => t.title === `${TAG} T02 api check`);
    expect(found).toBeTruthy();
    expect(found.type).toBe('automated'); // execution_type 2
  });

  // IMPT-03 · Re-import is idempotent (matched by external id) [P1]
  test('IMPT-03: re-import of TestLink cases skips duplicates', async ({ page }) => {
    const payload = testlinkXml('T03');
    const first = await importFile(page, 'testlink.xml', payload);
    expect((await first.json()).imported.tests).toBe(2);

    const second = await importFile(page, 'testlink.xml', payload);
    const body = await second.json();
    expect(body.imported.tests).toBe(0);
    expect(body.imported.skipped).toBeGreaterThanOrEqual(2);
  });
});
