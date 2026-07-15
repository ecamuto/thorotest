import { test, expect } from '@playwright/test';
import { loginAs } from '../fixtures/auth';

const BASE = 'http://localhost:8000';

test.describe('Suite 12 — Integrations, API Tokens, Webhooks', () => {

  async function getToken(page: any): Promise<string> {
    return await page.evaluate(() => localStorage.getItem('th_token') ?? '');
  }

  // INT-01 · Navigate to Integrations page [P1]
  test('INT-01: integrations page loads with all sections', async ({ page }) => {
    await loginAs(page, 'marco@acme.com');
    await page.goto('/#/integrations');
    await expect(page.locator('h1:has-text("Integrations")')).toBeVisible({ timeout: 10000 });
    await expect(page.locator('text=Connected integrations')).toBeVisible();
    await expect(page.locator('text=API tokens')).toBeVisible();
    await expect(page.locator('text=Webhooks')).toBeVisible();
  });

  // INT-02 · Add integration (2-step modal) [P1]
  test('INT-02: add integration via 2-step modal', async ({ page }) => {
    await loginAs(page, 'marco@acme.com');
    const token = await getToken(page);

    // Delete seed Slack integration so it appears in picker, cleanup stale e2e Jest integrations
    await page.request.delete(`${BASE}/api/integrations/int-slack`, { headers: { Authorization: `Bearer ${token}` } }).catch(() => {});
    const existingList = await page.request.get(`${BASE}/api/integrations`, { headers: { Authorization: `Bearer ${token}` } });
    const existingInts = await existingList.json();
    for (const i of existingInts.filter((x: any) => x.name === 'Slack' && x.id !== 'int-slack')) {
      await page.request.delete(`${BASE}/api/integrations/${i.id}`, { headers: { Authorization: `Bearer ${token}` } }).catch(() => {});
    }

    await page.goto('/#/integrations');
    await expect(page.locator('h1:has-text("Integrations")')).toBeVisible({ timeout: 10000 });

    await page.click('button:has-text("Add integration")');

    // Step 1: pick provider — choose Slack (now visible since int-slack was removed)
    await expect(page.locator('text=Add integration').first()).toBeVisible({ timeout: 5000 });
    await page.locator('button').filter({ hasText: 'Slack' }).first().click();

    // Step 2: configure
    await expect(page.locator('text=Configure Slack')).toBeVisible({ timeout: 5000 });
    await page.fill('input[placeholder*="org/repo"]', '#e2e-test-channel');
    const [intResponse] = await Promise.all([
      page.waitForResponse(r => r.url().includes('/api/integrations') && r.request().method() === 'POST'),
      page.click('button:has-text("Connect")'),
    ]);
    expect(intResponse.status()).toBe(201);

    // Integration appears in list (modal closed)
    await expect(page.locator('text=Configure Slack')).not.toBeVisible({ timeout: 5000 });
    await expect(page.locator('table td:has-text("Slack")')).toBeVisible({ timeout: 8000 });

    // Cleanup: delete the e2e Slack integration (leave seed to be re-added on next db-reset)
    const list = await page.request.get(`${BASE}/api/integrations`, { headers: { Authorization: `Bearer ${token}` } });
    const ints = await list.json();
    const created = ints.find((i: any) => i.name === 'Slack' && i.configured_by === '#e2e-test-channel');
    if (created) {
      await page.request.delete(`${BASE}/api/integrations/${created.id}`, { headers: { Authorization: `Bearer ${token}` } });
    }
  });

  // INT-03 · Edit integration [P1]
  test('INT-03: edit integration status and configured_by', async ({ page }) => {
    await loginAs(page, 'marco@acme.com');
    const token = await getToken(page);

    // Cleanup stale test integrations from previous runs
    const existing = await page.request.get(`${BASE}/api/integrations`, { headers: { Authorization: `Bearer ${token}` } });
    const allInts = await existing.json();
    for (const i of allInts.filter((x: any) => x.name === 'Test Edit Integration')) {
      await page.request.delete(`${BASE}/api/integrations/${i.id}`, { headers: { Authorization: `Bearer ${token}` } });
    }

    // Create integration via API
    const created = await page.request.post(`${BASE}/api/integrations`, {
      data: { id: `int-test-edit-${Date.now()}`, name: 'Test Edit Integration', type: 'ci', icon: 'plug', configured_by: 'original' },
      headers: { Authorization: `Bearer ${token}`, 'Content-Type': 'application/json' },
    });
    const integration = await created.json();

    await page.goto('/#/integrations');
    await expect(page.locator('text=Test Edit Integration').first()).toBeVisible({ timeout: 10000 });

    // Open the context menu for the integration
    const row = page.locator('tr').filter({ hasText: 'Test Edit Integration' }).first();
    await row.locator('button.btn.ghost.icon.sm').click(); // open 3-dot dropdown
    await row.locator('button').filter({ hasText: 'Edit' }).click(); // click Edit in dropdown

    // Edit modal
    await expect(page.locator('text="Edit integration"')).toBeVisible({ timeout: 5000 });
    await page.locator('label:has-text("Configured by") + input.login-input').fill('updated-config');
    await page.selectOption('select', 'disabled');
    // Wait for the PATCH to actually land before reading back the list — clicking
    // Save and immediately GET-ing the list races the write (the old flake).
    const [patchResponse] = await Promise.all([
      page.waitForResponse(r =>
        r.url().includes(`/api/integrations/${integration.id}`) && r.request().method() === 'PATCH'),
      page.click('button:has-text("Save")'),
    ]);
    expect(patchResponse.status()).toBe(200);
    // Modal closes on a successful save.
    await expect(page.locator('text="Edit integration"')).not.toBeVisible({ timeout: 5000 });

    // Verify update via list endpoint (no single-GET endpoint exists)
    const list = await page.request.get(`${BASE}/api/integrations`, {
      headers: { Authorization: `Bearer ${token}` },
    });
    expect(list.status()).toBe(200);
    const allAfter: any[] = await list.json();
    const updated = allAfter.find((i: any) => i.id === integration.id);
    expect(updated).toBeDefined();
    expect(updated.configured_by).toBe('updated-config');
    expect(updated.status).toBe('disabled');

    // Cleanup
    await page.request.delete(`${BASE}/api/integrations/${integration.id}`, {
      headers: { Authorization: `Bearer ${token}` },
    });
  });

  // INT-04 · Delete/disconnect integration [P1]
  test('INT-04: disconnect integration removes it from list', async ({ page }) => {
    await loginAs(page, 'marco@acme.com');
    const token = await getToken(page);

    // Create via API
    const id = `int-test-del-${Date.now()}`;
    await page.request.post(`${BASE}/api/integrations`, {
      data: { id, name: 'To Delete Integration', type: 'ci', icon: 'plug' },
      headers: { Authorization: `Bearer ${token}`, 'Content-Type': 'application/json' },
    });

    await page.goto('/#/integrations');
    await expect(page.locator('text=To Delete Integration')).toBeVisible({ timeout: 10000 });

    // Open menu → Disconnect
    const row = page.locator(`tr:has-text("To Delete Integration")`);
    await row.locator('button').click();

    page.on('dialog', async dialog => {
      expect(dialog.message()).toContain('Disconnect');
      await dialog.accept();
    });
    await page.click('text=Disconnect');

    // Integration disappears
    await expect(page.locator('text=To Delete Integration')).not.toBeVisible({ timeout: 8000 });

    // Verify via API
    const get = await page.request.get(`${BASE}/api/integrations/${id}`, {
      headers: { Authorization: `Bearer ${token}` },
    });
    expect(get.status()).toBe(404);
  });

  // INT-05 · API Tokens — genera token e mostra reveal modal [P1]
  test('INT-05: generate API token shows token reveal modal', async ({ page }) => {
    await loginAs(page, 'marco@acme.com');
    await page.goto('/#/integrations');
    await expect(page.locator('text=API tokens')).toBeVisible({ timeout: 10000 });

    await page.locator('.card').filter({ hasText: 'API tokens' }).locator('button:has-text("Generate")').click();

    // Fill token form
    await expect(page.locator('text=Generate API token')).toBeVisible({ timeout: 5000 });
    await page.fill('input[placeholder="e.g. ci-runner"]', 'e2e-test-token');
    await page.fill('input[placeholder*="report:write"]', 'runs:read');
    await page.locator('button.btn.primary:has-text("Generate")').click();

    // Reveal modal shows the token
    await expect(page.locator('text=Token created')).toBeVisible({ timeout: 8000 });
    await expect(page.locator('text=Copy this token now')).toBeVisible();
    await expect(page.locator('code')).toBeVisible();

    // Token value should be non-empty
    const tokenValue = await page.locator('code').textContent();
    expect(tokenValue?.length).toBeGreaterThan(10);

    // Close
    await page.click('button:has-text("Done")');
    await expect(page.locator('text=e2e-test-token')).toBeVisible({ timeout: 5000 });

    // Cleanup via API
    const userToken = await getToken(page);
    const list = await page.request.get(`${BASE}/api/tokens`, {
      headers: { Authorization: `Bearer ${userToken}` },
    });
    const tokens = await list.json();
    const created = tokens.find((t: any) => t.name === 'e2e-test-token');
    if (created) {
      await page.request.delete(`${BASE}/api/tokens/${created.id}`, {
        headers: { Authorization: `Bearer ${userToken}` },
      });
    }
  });

  // INT-06 · API Tokens — revoca token con confirm [P1]
  test('INT-06: revoke API token removes it from list', async ({ page }) => {
    await loginAs(page, 'marco@acme.com');
    const userToken = await getToken(page);

    // Cleanup stale e2e-revoke-test tokens from previous runs
    const existing = await page.request.get(`${BASE}/api/tokens`, { headers: { Authorization: `Bearer ${userToken}` } });
    const allToks = await existing.json();
    for (const t of allToks.filter((x: any) => x.name === 'e2e-revoke-test')) {
      await page.request.delete(`${BASE}/api/tokens/${t.id}`, { headers: { Authorization: `Bearer ${userToken}` } });
    }

    // Create token via API
    const created = await page.request.post(`${BASE}/api/tokens`, {
      data: { name: 'e2e-revoke-test', scope: '' },
      headers: { Authorization: `Bearer ${userToken}`, 'Content-Type': 'application/json' },
    });
    const tok = await created.json();

    await page.goto('/#/integrations');
    await expect(page.locator('text=e2e-revoke-test').first()).toBeVisible({ timeout: 10000 });

    // Revoke
    page.on('dialog', async dialog => dialog.accept());
    const revokeBtn = page.locator('xpath=//div[normalize-space(text())="e2e-revoke-test"]/ancestor::div[.//button[@title="Revoke"]][1]//button[@title="Revoke"]');
    await revokeBtn.click();

    await expect(page.locator('text=e2e-revoke-test')).not.toBeVisible({ timeout: 8000 });

    // Verify via API
    const get = await page.request.get(`${BASE}/api/tokens`, {
      headers: { Authorization: `Bearer ${userToken}` },
    });
    const tokens = await get.json();
    expect(tokens.some((t: any) => t.id === tok.id)).toBe(false);
  });

  // INT-07 · API Tokens — token name required [P2]
  test('INT-07: token generation requires name', async ({ page }) => {
    await loginAs(page, 'marco@acme.com');
    await page.goto('/#/integrations');

    await page.locator('.card').filter({ hasText: 'API tokens' }).locator('button:has-text("Generate")').click();
    await expect(page.locator('text=Generate API token')).toBeVisible({ timeout: 5000 });
    // Leave name empty
    await page.locator('button.btn.primary:has-text("Generate")').click();
    await expect(page.locator('text=Name is required')).toBeVisible({ timeout: 5000 });
  });

  // INT-08 · Webhooks — crea webhook [P1]
  test('INT-08: create webhook with URL and events', async ({ page }) => {
    await loginAs(page, 'marco@acme.com');
    await page.goto('/#/integrations');
    await expect(page.locator('text=Webhooks')).toBeVisible({ timeout: 10000 });

    await page.locator('.card').filter({ hasText: 'Webhooks & outbound' }).locator('button:has-text("Add")').click();

    // Fill webhook form
    await expect(page.locator('text=Add webhook').first()).toBeVisible({ timeout: 5000 });
    await page.fill('input[placeholder*="endpoint"]', 'https://example.com/hook-e2e');

    // Select events
    await page.check('input[type="checkbox"] + span:has-text("run.completed") ~ input, label:has-text("run.completed") input');
    // Alternative approach for checkboxes
    const checkboxes = page.locator('label').filter({ hasText: 'run.completed' }).locator('input[type="checkbox"]');
    if (await checkboxes.count() > 0) {
      await checkboxes.first().check();
    }

    await page.click('button:has-text("Add webhook")');

    // Webhook appears in list
    await expect(page.locator('text=https://example.com/hook-e2e')).toBeVisible({ timeout: 8000 });

    // Cleanup
    const token = await getToken(page);
    const list = await page.request.get(`${BASE}/api/webhooks`, {
      headers: { Authorization: `Bearer ${token}` },
    });
    const hooks = await list.json();
    const hook = hooks.find((h: any) => h.url === 'https://example.com/hook-e2e');
    if (hook) {
      await page.request.delete(`${BASE}/api/webhooks/${hook.id}`, {
        headers: { Authorization: `Bearer ${token}` },
      });
    }
  });

  // INT-09 · Webhooks — URL richiesta [P2]
  test('INT-09: webhook URL required validation', async ({ page }) => {
    await loginAs(page, 'marco@acme.com');
    await page.goto('/#/integrations');

    await page.locator('.card').filter({ hasText: 'Webhooks & outbound' }).locator('button:has-text("Add")').click();
    await expect(page.locator('text=Add webhook').first()).toBeVisible({ timeout: 5000 });
    // Leave URL empty
    await page.click('button:has-text("Add webhook")');
    await expect(page.locator('text=URL is required')).toBeVisible({ timeout: 5000 });
  });

  // INT-10 · Webhooks — test webhook (POST /api/webhooks/{id}/test) [P1]
  test('INT-10: test webhook endpoint shows status code result', async ({ page }) => {
    await loginAs(page, 'marco@acme.com');
    const token = await getToken(page);

    // Cleanup stale httpbin webhooks
    const existingWh = await page.request.get(`${BASE}/api/webhooks`, { headers: { Authorization: `Bearer ${token}` } });
    for (const w of (await existingWh.json()).filter((x: any) => x.url.includes('httpbin.org'))) {
      await page.request.delete(`${BASE}/api/webhooks/${w.id}`, { headers: { Authorization: `Bearer ${token}` } });
    }

    // Create webhook via API (using httpbin or a known URL)
    const created = await page.request.post(`${BASE}/api/webhooks`, {
      data: { url: 'https://httpbin.org/post', events: ['run.completed'] },
      headers: { Authorization: `Bearer ${token}`, 'Content-Type': 'application/json' },
    });
    const hook = await created.json();

    await page.goto('/#/integrations');
    await expect(page.locator('span.mono').filter({ hasText: 'httpbin.org' })).toBeVisible({ timeout: 10000 });

    // Click "Test" button for this webhook
    // Use innermost div containing the URL span (flex row with URL + action buttons)
    const hookRow = page.locator('div').filter({ has: page.locator('span.mono').filter({ hasText: 'httpbin.org' }) }).last();
    await hookRow.locator('button').filter({ hasText: 'Test' }).click();

    // Wait for result — status code or "OK" indicator appears
    await page.waitForTimeout(8000); // webhook test may take time
    // The status code badge should appear after test
    await expect(hookRow.locator('span.status')).toBeVisible({ timeout: 10000 });

    // Cleanup
    await page.request.delete(`${BASE}/api/webhooks/${hook.id}`, {
      headers: { Authorization: `Bearer ${token}` },
    });
  });

  // INT-11 · Webhooks — edit webhook [P1]
  test('INT-11: edit webhook URL', async ({ page }) => {
    await loginAs(page, 'marco@acme.com');
    const token = await getToken(page);

    // Cleanup stale webhooks
    const existingWh = await page.request.get(`${BASE}/api/webhooks`, { headers: { Authorization: `Bearer ${token}` } });
    for (const w of (await existingWh.json()).filter((x: any) => x.url.includes('original-hook') || x.url.includes('updated-hook'))) {
      await page.request.delete(`${BASE}/api/webhooks/${w.id}`, { headers: { Authorization: `Bearer ${token}` } });
    }

    // Create
    const created = await page.request.post(`${BASE}/api/webhooks`, {
      data: { url: 'https://example.com/original-hook', events: [] },
      headers: { Authorization: `Bearer ${token}`, 'Content-Type': 'application/json' },
    });
    const hook = await created.json();

    await page.goto('/#/integrations');
    await expect(page.locator('span.mono').filter({ hasText: 'original-hook' })).toBeVisible({ timeout: 10000 });

    // Click edit pencil
    const hookRow = page.locator('div').filter({ has: page.locator('span.mono').filter({ hasText: 'original-hook' }) }).last();
    await hookRow.locator('button[title="Edit"]').click();

    await expect(page.locator('text=Edit webhook')).toBeVisible({ timeout: 5000 });
    await page.fill('input[placeholder*="endpoint"]', 'https://example.com/updated-hook');
    await page.click('button:has-text("Save")');

    // Updated URL appears
    await expect(page.locator('span.mono').filter({ hasText: 'updated-hook' })).toBeVisible({ timeout: 8000 });

    // Cleanup
    await page.request.delete(`${BASE}/api/webhooks/${hook.id}`, {
      headers: { Authorization: `Bearer ${token}` },
    });
  });

  // INT-12 · Webhooks — delete webhook [P1]
  test('INT-12: delete webhook removes it from list', async ({ page }) => {
    await loginAs(page, 'marco@acme.com');
    const token = await getToken(page);

    // Cleanup stale webhooks
    const existingWh = await page.request.get(`${BASE}/api/webhooks`, { headers: { Authorization: `Bearer ${token}` } });
    for (const w of (await existingWh.json()).filter((x: any) => x.url.includes('to-delete-hook'))) {
      await page.request.delete(`${BASE}/api/webhooks/${w.id}`, { headers: { Authorization: `Bearer ${token}` } });
    }

    // Create
    const created = await page.request.post(`${BASE}/api/webhooks`, {
      data: { url: 'https://example.com/to-delete-hook', events: [] },
      headers: { Authorization: `Bearer ${token}`, 'Content-Type': 'application/json' },
    });
    const hook = await created.json();

    await page.goto('/#/integrations');
    await expect(page.locator('span.mono').filter({ hasText: 'to-delete-hook' })).toBeVisible({ timeout: 10000 });

    page.on('dialog', async dialog => dialog.accept());
    const hookRow = page.locator('div').filter({ has: page.locator('span.mono').filter({ hasText: 'to-delete-hook' }) }).last();
    await hookRow.locator('button[title="Delete"]').click();

    await expect(page.locator('text=to-delete-hook')).not.toBeVisible({ timeout: 8000 });

    // Verify gone via API
    const get = await page.request.get(`${BASE}/api/webhooks/${hook.id}`, {
      headers: { Authorization: `Bearer ${token}` },
    });
    expect(get.status()).toBe(404);
  });

  // INT-13 · Integrations — Escape chiude modal [P2]
  test('INT-13: Escape key closes integration modal', async ({ page }) => {
    await loginAs(page, 'marco@acme.com');
    await page.goto('/#/integrations');

    await page.click('button:has-text("Add integration")');
    await expect(page.locator('text=Add integration').first()).toBeVisible({ timeout: 5000 });

    await page.keyboard.press('Escape');
    await expect(page.locator('button:has-text("Add integration")')).toBeVisible({ timeout: 5000 });
  });

});
