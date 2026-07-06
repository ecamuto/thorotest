import { test, expect, Page } from '@playwright/test';
import { loginAs } from '../fixtures/auth';

const BASE = 'http://localhost:8000';

// Unique suffix so re-runs against a reused dev server don't collide on titles.
const TAG = `IMP-${Date.now().toString(36)}`;

const CSV = [
  'title,section,type,priority',
  `${TAG} login valid creds,Imported/Auth,manual,high`,
  `${TAG} login locked account,Imported/Auth,manual,med`,
  `${TAG} checkout flow,Imported/Checkout,automated,critical`,
].join('\n');

const JUNIT = `<?xml version="1.0" encoding="UTF-8"?>
<testsuites name="${TAG} junit run">
  <testsuite name="Imported JUnit Suite">
    <testcase name="${TAG} junit pass" classname="suite.A"/>
    <testcase name="${TAG} junit fail" classname="suite.A"><failure message="boom"/></testcase>
    <testcase name="${TAG} junit skip" classname="suite.A"><skipped/></testcase>
  </testsuite>
</testsuites>`;

const JSON_GENERIC = JSON.stringify({
  tests: [
    { title: `${TAG} json one`, folder: 'Imported/JSON', priority: 'high', type: 'manual' },
    { title: `${TAG} json two`, folder: 'Imported/JSON', status: 'pass' },
  ],
});

// TestRail native XML: <suite><sections><section><cases><case>. Nested
// section exercises the folder-hierarchy walk.
const TESTRAIL_XML = `<?xml version="1.0" encoding="UTF-8"?>
<suite>
  <name>${TAG} testrail suite</name>
  <sections>
    <section>
      <name>Auth</name>
      <cases>
        <case><id>C1</id><title>${TAG} tr login</title><priority_id>4</priority_id></case>
      </cases>
      <sections>
        <section>
          <name>OAuth</name>
          <cases>
            <case><id>C2</id><title>${TAG} tr oauth google</title><priority_id>3</priority_id></case>
          </cases>
        </section>
      </sections>
    </section>
  </sections>
</suite>`;

// Allure results array: each object with a status → grouped into one run.
const ALLURE_JSON = JSON.stringify([
  { name: `${TAG} allure pass`, status: 'passed', labels: [{ name: 'suite', value: 'Imported/Allure' }] },
  { name: `${TAG} allure fail`, status: 'failed', labels: [{ name: 'suite', value: 'Imported/Allure' }] },
]);

async function token(page: Page): Promise<string> {
  return page.evaluate(() => localStorage.getItem('th_token') || '');
}

async function gotoImport(page: Page) {
  await page.click('.nav-item:has-text("Import")');
  await page.waitForURL('**/#/import', { timeout: 5000 });
}

async function dropFile(page: Page, name: string, mimeType: string, body: string) {
  await page.locator('input[type="file"]').setInputFiles({
    name,
    mimeType,
    buffer: Buffer.from(body, 'utf-8'),
  });
}

test.describe('Suite 17 — Import (CSV / JUnit / JSON)', () => {
  test.beforeEach(async ({ page }) => {
    await loginAs(page, 'marco@acme.com'); // admin → write role
  });

  // IMP-01 · Import view loads with upload dropzone [P0]
  test('IMP-01: import page loads with dropzone', async ({ page }) => {
    await gotoImport(page);
    await expect(page.locator('.page-title:has-text("Import")')).toBeVisible();
    await expect(page.getByText('Drop file here or click to browse')).toBeVisible();
  });

  // IMP-02 · CSV upload auto-detects format + reveals mapping [P0]
  test('IMP-02: CSV upload detects format and shows column mapping', async ({ page }) => {
    await gotoImport(page);
    const [detect] = await Promise.all([
      page.waitForResponse(r => r.url().includes('/api/import/detect')),
      dropFile(page, 'tests.csv', 'text/csv', CSV),
    ]);
    expect(detect.status()).toBe(200);
    await expect(page.locator('.card-title:has-text("Column mapping")')).toBeVisible({ timeout: 5000 });
  });

  // IMP-03 · CSV preview returns counts + sample without writing [P0]
  test('IMP-03: CSV preview shows parsed counts and sample rows', async ({ page }) => {
    await gotoImport(page);
    await dropFile(page, 'tests.csv', 'text/csv', CSV);
    const [preview] = await Promise.all([
      page.waitForResponse(r => r.url().includes('/api/import/preview')),
      page.click('button:has-text("Preview")'),
    ]);
    expect(preview.status()).toBe(200);
    const body = await preview.json();
    expect(body.tests).toBe(3);
    expect(body.folders).toBe(2); // Imported/Auth + Imported/Checkout
    await expect(page.locator('.card-title:has-text("Preview")')).toBeVisible();
    await expect(page.getByText(`${TAG} login valid creds`)).toBeVisible();
  });

  // IMP-04 · CSV execute persists; tests show in Library [P0]
  test('IMP-04: CSV import completes and tests land in Library', async ({ page }) => {
    await gotoImport(page);
    await dropFile(page, 'tests.csv', 'text/csv', CSV);
    const [exec] = await Promise.all([
      page.waitForResponse(r => r.url().includes('/api/import/execute')),
      page.click('button:has-text("Import")'),
    ]);
    expect(exec.status()).toBe(200);
    const body = await exec.json();
    expect(body.ok).toBe(true);
    expect(body.imported.tests).toBe(3);
    // execute counts created folder *nodes* (Imported, Auth, Checkout = 3),
    // preview counts distinct leaf paths (2) — different, both correct.
    expect(body.imported.folders).toBe(3);
    await expect(page.getByText('Import complete')).toBeVisible({ timeout: 5000 });

    // Verify persisted via API search
    const res = await page.request.fetch(
      `${BASE}/api/tests?search=${encodeURIComponent(`${TAG} checkout flow`)}`,
      { headers: { Authorization: `Bearer ${await token(page)}` } },
    );
    expect(res.status()).toBe(200);
    const tests = await res.json();
    expect(tests.some((t: any) => t.title === `${TAG} checkout flow`)).toBeTruthy();
  });

  // IMP-05 · JUnit XML execute creates a run with case results [P1]
  test('IMP-05: JUnit XML import creates tests and a run', async ({ page }) => {
    await gotoImport(page);
    await dropFile(page, 'results.xml', 'application/xml', JUNIT);
    // Detect should classify as junit_xml — confirm the format button is active
    await expect(page.locator('button:has-text("JUnit XML")')).toBeVisible({ timeout: 5000 });
    const [exec] = await Promise.all([
      page.waitForResponse(r => r.url().includes('/api/import/execute')),
      page.click('button:has-text("Import")'),
    ]);
    const body = await exec.json();
    expect(exec.status()).toBe(200);
    expect(body.format).toBe('junit_xml');
    expect(body.imported.tests).toBe(3);
    expect(body.imported.runs).toBe(1);
    await expect(page.getByText('Import complete')).toBeVisible({ timeout: 5000 });

    // The imported run is retrievable
    const res = await page.request.fetch(`${BASE}/api/runs`, {
      headers: { Authorization: `Bearer ${await token(page)}` },
    });
    const runs = await res.json();
    expect(runs.some((r: any) => (r.name || '').includes(`${TAG} junit run`))).toBeTruthy();
  });

  // IMP-06 · JSON generic execute persists tests [P1]
  test('IMP-06: JSON import completes and persists tests', async ({ page }) => {
    await gotoImport(page);
    await dropFile(page, 'data.json', 'application/json', JSON_GENERIC);
    const [exec] = await Promise.all([
      page.waitForResponse(r => r.url().includes('/api/import/execute')),
      page.click('button:has-text("Import")'),
    ]);
    const body = await exec.json();
    expect(exec.status()).toBe(200);
    expect(body.imported.tests).toBe(2);
    await expect(page.getByText('Import complete')).toBeVisible({ timeout: 5000 });
  });

  // IMP-07 · /api/import/* is gated — anonymous rejected [P0]
  test('IMP-07: import endpoints require auth (anonymous 401)', async ({ page }) => {
    for (const path of ['/api/import/detect', '/api/import/preview', '/api/import/execute']) {
      const res = await page.request.fetch(`${BASE}${path}`, {
        method: 'POST',
        multipart: { file: { name: 'tests.csv', mimeType: 'text/csv', buffer: Buffer.from(CSV) } },
      });
      expect(res.status(), `${path} should reject anonymous`).toBe(401);
    }
  });

  // IMP-08 · TestRail XML detects + imports nested sections as folders [P1]
  test('IMP-08: TestRail XML import creates tests with nested folders', async ({ page }) => {
    await gotoImport(page);
    await dropFile(page, 'suite.xml', 'application/xml', TESTRAIL_XML);
    await expect(page.locator('button:has-text("TestRail XML")')).toBeVisible({ timeout: 5000 });
    const [exec] = await Promise.all([
      page.waitForResponse(r => r.url().includes('/api/import/execute')),
      page.click('button:has-text("Import")'),
    ]);
    const body = await exec.json();
    expect(exec.status()).toBe(200);
    expect(body.format).toBe('testrail_xml');
    expect(body.imported.tests).toBe(2);
    await expect(page.getByText('Import complete')).toBeVisible({ timeout: 5000 });

    // Nested case landed under the Auth/OAuth hierarchy.
    const res = await page.request.fetch(
      `${BASE}/api/tests?search=${encodeURIComponent(`${TAG} tr oauth google`)}`,
      { headers: { Authorization: `Bearer ${await token(page)}` } },
    );
    expect((await res.json()).some((t: any) => t.title === `${TAG} tr oauth google`)).toBeTruthy();
  });

  // IMP-09 · Allure JSON creates tests + a run with results [P1]
  test('IMP-09: Allure JSON import creates tests and a run', async ({ page }) => {
    await gotoImport(page);
    await dropFile(page, 'allure.json', 'application/json', ALLURE_JSON);
    const [exec] = await Promise.all([
      page.waitForResponse(r => r.url().includes('/api/import/execute')),
      page.click('button:has-text("Import")'),
    ]);
    const body = await exec.json();
    expect(exec.status()).toBe(200);
    expect(body.format).toBe('json');
    expect(body.imported.tests).toBe(2);
    expect(body.imported.runs).toBe(1);
    await expect(page.getByText('Import complete')).toBeVisible({ timeout: 5000 });
  });
});
