import { test, expect, Page } from '@playwright/test';
import { loginAs } from '../fixtures/auth';

const BASE = 'http://localhost:8000';

async function getToken(page: Page): Promise<string> {
  return page.evaluate(() => localStorage.getItem('th_token') || '');
}

async function api(page: Page, method: string, path: string, body?: unknown): Promise<any> {
  const token = await getToken(page);
  const res = await page.request.fetch(`${BASE}${path}`, {
    method,
    headers: {
      'Authorization': `Bearer ${token}`,
      'Content-Type': 'application/json',
    },
    data: body !== undefined ? JSON.stringify(body) : undefined,
  });
  if (!res.ok()) throw new Error(`API ${method} ${path} → ${res.status()}: ${await res.text()}`);
  return res.json().catch(() => null);
}

test.describe('Suite P1 — Steps & Attachments', () => {

  test.beforeEach(async ({ page }) => {
    await loginAs(page, 'marco@acme.com');
  });

  // ─── FLOW 1: Step editor in TestDetail (Definition tab) ──────────────────

  // P1-STEPS-01 · Aggiunge due step, salva, verifica persistenza
  test('STEPS-01: add two steps via Definition tab and save', async ({ page }) => {
    // Reset any existing steps
    await api(page, 'PATCH', '/api/tests/TC-2301/steps', []);

    await page.goto('/#/tests/TC-2301');
    await page.waitForURL('**/#/tests/TC-2301', { timeout: 10000 });
    await expect(page.locator('.app')).toHaveAttribute('data-screen-label', 'test-detail');
    await expect(page.locator('.card-title:has-text("Steps")')).toBeVisible({ timeout: 5000 });

    // Add step 1
    await page.click('.btn.sm.ghost:has-text("Add step")');
    await page.fill('input.input[placeholder="Action (e.g. Click Submit)"]', 'Navigate to checkout page');
    await page.fill('input.input[placeholder="Expected result (optional)"]', 'Checkout form is displayed');
    await page.click('.btn.sm.ghost:has-text("Done")');

    // Add step 2
    await page.click('.btn.sm.ghost:has-text("Add step")');
    await page.locator('input.input[placeholder="Action (e.g. Click Submit)"]').last().fill('Enter card number 4242 4242 4242 4242');
    await page.locator('input.input[placeholder="Expected result (optional)"]').last().fill('Card field accepts input without error');
    await page.click('.btn.sm.ghost:has-text("Done")');

    // Save
    const [response] = await Promise.all([
      page.waitForResponse(r => r.url().includes('/api/tests/TC-2301/steps') && r.request().method() === 'PATCH'),
      page.click('.btn.sm.accent:has-text("Save steps")'),
    ]);
    expect(response.status()).toBe(200);
    const saved = await response.json();
    expect(saved).toHaveLength(2);
    expect(saved[0].action).toBe('Navigate to checkout page');
    expect(saved[1].action).toBe('Enter card number 4242 4242 4242 4242');

    // Steps appear in UI
    await expect(page.locator('.step-text')).toHaveCount(2, { timeout: 5000 });
    await expect(page.locator('.step-text').first()).toContainText('Navigate to checkout page');
    await expect(page.locator('.step-text').last()).toContainText('Enter card number');

    // Step count badge updated
    await expect(page.locator('.card-sub').first()).toContainText('2 steps', { timeout: 3000 });

    // Cleanup
    await api(page, 'PATCH', '/api/tests/TC-2301/steps', []);
  });

  // P1-STEPS-02 · Elimina uno step inline, salva, verifica rimosso
  test('STEPS-02: delete a step inline and save', async ({ page }) => {
    // Setup
    await api(page, 'PATCH', '/api/tests/TC-2301/steps', [
      { action: 'Step to keep', expected_result: 'Should survive delete' },
      { action: 'Step to delete', expected_result: null },
    ]);

    await page.goto('/#/tests/TC-2301');
    await page.waitForURL('**/#/tests/TC-2301', { timeout: 10000 });
    await expect(page.locator('.step-text')).toHaveCount(2, { timeout: 8000 });

    // Click second step text to enter edit mode
    await page.locator('.step-text').last().click();

    // Delete button appears in edit mode
    await page.click('.btn.sm.ghost:has-text("Delete")');

    // 1 step remains
    await expect(page.locator('.step-text')).toHaveCount(1, { timeout: 3000 });

    // Save
    const [response] = await Promise.all([
      page.waitForResponse(r => r.url().includes('/api/tests/TC-2301/steps') && r.request().method() === 'PATCH'),
      page.click('.btn.sm.accent:has-text("Save steps")'),
    ]);
    expect(response.status()).toBe(200);
    const saved = await response.json();
    expect(saved).toHaveLength(1);
    expect(saved[0].action).toBe('Step to keep');

    // Cleanup
    await api(page, 'PATCH', '/api/tests/TC-2301/steps', []);
  });

  // ─── FLOW 2: Step runner in RunDetail ────────────────────────────────────

  // P1-STEPS-03 · Mark step pass poi fail, verifica contatore e stato visivo
  test('STEPS-03: mark steps pass and fail in RunDetail step runner', async ({ page }) => {
    // Setup: add steps to TC-2301
    const stepsData = await api(page, 'PATCH', '/api/tests/TC-2301/steps', [
      { action: 'Open login page', expected_result: 'Login form visible' },
      { action: 'Submit empty form', expected_result: 'Validation errors displayed' },
    ]);
    expect(stepsData).toHaveLength(2);

    // Create a fresh running run
    const runId = `R-E2E-SR-${Date.now()}`;
    await api(page, 'POST', '/api/runs', {
      id: runId,
      name: 'E2E step runner test',
      status: 'running',
      test_ids: ['TC-2301'],
      owner: 'marco@acme.com',
      env: 'staging',
      branch: 'test/e2e',
    });

    await page.goto(`/#/runs/${runId}`);
    await page.waitForURL(`**/#/runs/${runId}`, { timeout: 10000 });
    await expect(page.locator('.app')).toHaveAttribute('data-screen-label', 'run-detail');

    // Steps card loads with 2 steps
    await expect(page.locator('.card-title:has-text("Steps")')).toBeVisible({ timeout: 5000 });
    await expect(page.locator('.step')).toHaveCount(2, { timeout: 10000 });

    // Initial count: 0 / 2 done
    await expect(page.locator('text=/0 \\/ 2 done/')).toBeVisible({ timeout: 5000 });

    // Mark step 1 pass
    const passBtn = page.locator('.btn.ghost.sm[title="Pass (P)"]').first();
    await expect(passBtn).toBeVisible({ timeout: 5000 });
    const [patchResp1] = await Promise.all([
      page.waitForResponse(r => r.url().includes('/steps/') && r.request().method() === 'PATCH'),
      passBtn.click(),
    ]);
    expect(patchResp1.status()).toBe(200);
    const sr1 = await patchResp1.json();
    expect(sr1.status).toBe('pass');

    // Counter: 1 / 2 done, step 1 shows PASS
    await expect(page.locator('text=/1 \\/ 2 done/')).toBeVisible({ timeout: 5000 });
    await expect(page.locator('.step.pass')).toHaveCount(1, { timeout: 3000 });

    // Mark step 2 fail
    const failBtn = page.locator('.btn.ghost.sm[title="Fail (F)"]').first();
    await expect(failBtn).toBeVisible({ timeout: 5000 });
    const [patchResp2] = await Promise.all([
      page.waitForResponse(r => r.url().includes('/steps/') && r.request().method() === 'PATCH'),
      failBtn.click(),
    ]);
    expect(patchResp2.status()).toBe(200);
    const sr2 = await patchResp2.json();
    expect(sr2.status).toBe('fail');

    // Counter: 2 / 2 done
    await expect(page.locator('text=/2 \\/ 2 done/')).toBeVisible({ timeout: 5000 });
    await expect(page.locator('.step.fail')).toHaveCount(1, { timeout: 3000 });

    // Cleanup steps
    await api(page, 'PATCH', '/api/tests/TC-2301/steps', []);
  });

  // ─── FLOW 3: File upload in Evidence panel ───────────────────────────────

  // P1-STEPS-04 · Upload screenshot via FileDropZone, verifica card allegato
  test('STEPS-04: upload evidence file via FileDropZone in RunDetail', async ({ page }) => {
    // Create a run (no steps needed — Evidence panel always visible)
    const runId = `R-E2E-ATT-${Date.now()}`;
    await api(page, 'POST', '/api/runs', {
      id: runId,
      name: 'E2E attachment test',
      status: 'running',
      test_ids: ['TC-2301'],
      owner: 'marco@acme.com',
      env: 'staging',
      branch: 'test/e2e',
    });

    await page.goto(`/#/runs/${runId}`);
    await page.waitForURL(`**/#/runs/${runId}`, { timeout: 10000 });
    await expect(page.locator('.app')).toHaveAttribute('data-screen-label', 'run-detail');

    // Evidence card visible
    await expect(page.locator('.card-title:has-text("Evidence")')).toBeVisible({ timeout: 5000 });

    // Upload file via hidden input inside browse label
    const fileInput = page.locator('label:has-text("browse") input[type="file"]');
    await expect(fileInput).toBeAttached({ timeout: 5000 });

    const [uploadResp] = await Promise.all([
      page.waitForResponse(r => r.url().includes('/api/attachments') && r.request().method() === 'POST'),
      fileInput.setInputFiles({
        name: 'evidence-screenshot.txt',
        mimeType: 'text/plain',
        buffer: Buffer.from('E2E test evidence content'),
      }),
    ]);

    expect(uploadResp.status()).toBe(201);
    const att = await uploadResp.json();
    expect(att.id).toBeTruthy();
    expect(att.filename).toContain('evidence-screenshot');

    // Attachment card appears with filename link
    await expect(page.locator(`a.mono:has-text("evidence-screenshot")`)).toBeVisible({ timeout: 8000 });

    // Delete button on attachment works
    const deleteBtn = page.locator('.btn.ghost.icon.sm[title="Delete attachment"]');
    await expect(deleteBtn).toBeVisible({ timeout: 3000 });
    const [deleteResp] = await Promise.all([
      page.waitForResponse(r => r.url().includes(`/api/attachments/${att.id}`) && r.request().method() === 'DELETE'),
      deleteBtn.click(),
    ]);
    expect(deleteResp.status()).toBe(204);

    // Card removed from UI
    await expect(page.locator(`a.mono:has-text("evidence-screenshot")`)).toHaveCount(0, { timeout: 5000 });
  });

});
