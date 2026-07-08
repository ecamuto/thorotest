import { test, expect, Page } from '@playwright/test';
import { loginAs } from '../fixtures/auth';

const BASE = 'http://localhost:8000';

// Unique suffix so re-runs against a reused dev server don't collide on
// titles or Zephyr keys.
const TAG = `ZEP-${Date.now().toString(36)}`;

// A Zephyr Scale export: two test cases (one carries an "objective" marker so
// the detector classifies it without an explicit format) plus an execution
// that references a cycle → becomes a run.
function zephyrExport(prefix: string): string {
  return JSON.stringify({
    values: [
      {
        key: `${prefix}-T1`,
        name: `${TAG} ${prefix} login valid`,
        folder: '/ZephyrE2E/Auth',
        priority: 'High',
        status: 'Approved',
        objective: 'verify login',
        labels: ['smoke'],
      },
      {
        key: `${prefix}-T2`,
        name: `${TAG} ${prefix} checkout`,
        folder: '/ZephyrE2E/Checkout',
        priority: 'Normal',
      },
      {
        testCase: { key: `${prefix}-T1` },
        testCycle: { key: `${prefix}-C1`, name: `${TAG} ${prefix} Regression` },
        status: 'Pass',
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

test.describe('Suite 17 — Import (Zephyr Scale JSON)', () => {
  test.beforeEach(async ({ page }) => {
    await loginAs(page, 'marco@acme.com'); // admin → write role
  });

  // IMPZ-01 · Zephyr JSON auto-detects as "zephyr" and previews counts [P0]
  test('IMPZ-01: Zephyr JSON detected and preview shows counts', async ({ page }) => {
    await gotoImport(page);
    const [detect] = await Promise.all([
      page.waitForResponse(r => r.url().includes('/api/import/detect')),
      dropFile(page, 'zephyr.json', zephyrExport('D01')),
    ]);
    expect(detect.status()).toBe(200);
    expect((await detect.json()).format).toBe('zephyr');

    const [preview] = await Promise.all([
      page.waitForResponse(r => r.url().includes('/api/import/preview')),
      page.click('button:has-text("Preview")'),
    ]);
    const body = await preview.json();
    expect(body.format).toBe('zephyr (json)');
    expect(body.tests).toBe(2);
    expect(body.runs).toBe(1);
  });

  // IMPZ-02 · Zephyr execute persists tests + a run from the cycle [P0]
  test('IMPZ-02: Zephyr import persists tests and a run', async ({ page }) => {
    await gotoImport(page);
    await dropFile(page, 'zephyr.json', zephyrExport('D02'));
    const [exec] = await Promise.all([
      page.waitForResponse(r => r.url().includes('/api/import/execute')),
      page.click('button:has-text("Import")'),
    ]);
    const body = await exec.json();
    expect(exec.status()).toBe(200);
    expect(body.format).toBe('zephyr');
    expect(body.imported.tests).toBe(2);
    expect(body.imported.runs).toBe(1);
    await expect(page.getByText('Import complete')).toBeVisible({ timeout: 5000 });

    // Persisted test is retrievable and the cycle became a run.
    const t = await page.request.fetch(
      `${BASE}/api/tests?search=${encodeURIComponent(`${TAG} D02 login valid`)}`,
      { headers: { Authorization: `Bearer ${await token(page)}` } },
    );
    expect((await t.json()).some((x: any) => x.title === `${TAG} D02 login valid`)).toBeTruthy();

    const r = await page.request.fetch(`${BASE}/api/runs`, {
      headers: { Authorization: `Bearer ${await token(page)}` },
    });
    expect((await r.json()).some((x: any) => (x.name || '').includes(`${TAG} D02 Regression`))).toBeTruthy();
  });

  // IMPZ-03 · Re-importing the same export is idempotent [P0]
  test('IMPZ-03: re-import skips duplicates (idempotent)', async ({ page }) => {
    const payload = zephyrExport('D03');

    await gotoImport(page);
    await dropFile(page, 'zephyr.json', payload);
    const [first] = await Promise.all([
      page.waitForResponse(r => r.url().includes('/api/import/execute')),
      page.click('button:has-text("Import")'),
    ]);
    expect((await first.json()).imported.tests).toBe(2);

    // Second identical import: tests matched by (provider, key), run by cycle.
    // Re-clicking the Import nav resets the view to a fresh dropzone.
    await gotoImport(page);
    await dropFile(page, 'zephyr.json', payload);
    const [second] = await Promise.all([
      page.waitForResponse(r => r.url().includes('/api/import/execute')),
      page.click('button:has-text("Import")'),
    ]);
    const body = await second.json();
    expect(body.imported.tests).toBe(0);
    expect(body.imported.runs).toBe(0);
    expect(body.imported.skipped).toBeGreaterThanOrEqual(2);
  });

  // IMPZ-04 · Same title in different folders both import (no collision) [P1]
  test('IMPZ-04: same-titled cases in different folders both persist', async ({ page }) => {
    const payload = JSON.stringify({
      values: [
        { key: 'D04-T1', name: `${TAG} D04 shared`, folder: '/ZephyrE2E/Web', objective: 'x' },
        { key: 'D04-T2', name: `${TAG} D04 shared`, folder: '/ZephyrE2E/Mobile' },
      ],
    });
    await gotoImport(page);
    await dropFile(page, 'zephyr.json', payload);
    const [exec] = await Promise.all([
      page.waitForResponse(r => r.url().includes('/api/import/execute')),
      page.click('button:has-text("Import")'),
    ]);
    expect((await exec.json()).imported.tests).toBe(2);

    const res = await page.request.fetch(
      `${BASE}/api/tests?search=${encodeURIComponent(`${TAG} D04 shared`)}`,
      { headers: { Authorization: `Bearer ${await token(page)}` } },
    );
    const matches = (await res.json()).filter((x: any) => x.title === `${TAG} D04 shared`);
    expect(matches.length).toBe(2);
  });
});
