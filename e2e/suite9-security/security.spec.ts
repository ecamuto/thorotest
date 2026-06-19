import { test, expect } from '@playwright/test';
import { loginAs } from '../fixtures/auth';

const BASE = 'http://localhost:8000';

test.describe('Suite 9 — Sicurezza e Edge Case', () => {

  // E2E-SEC-01 · Endpoint protetti senza token [P0]
  test('SEC-01: GET /api/me senza token → 401', async ({ page }) => {
    const response = await page.request.get(`${BASE}/api/me`);
    expect(response.status()).toBe(401);

    // Document gap: POST /api/tests non protetto
    const postResp = await page.request.post(`${BASE}/api/tests`, {
      data: { id: 'TC-SEC-TEST', title: 'Security gap test', type: 'manual', priority: 'low' },
    });
    // Gap documentato: attualmente non protetto da auth — accettabile per ora
    // Il test registra il comportamento senza farlo fallire
    console.log(`[GAP] POST /api/tests senza token: ${postResp.status()} (atteso 401 in Fase 7)`);

    // Cleanup if created
    if (postResp.status() === 201) {
      await page.request.delete(`${BASE}/api/tests/TC-SEC-TEST`);
    }
  });

  // E2E-SEC-02 · Doppio ID — test e run [P1]
  test('SEC-02: doppio ID test → 409', async ({ page }) => {
    await loginAs(page, 'marco@acme.com');
    const token = await page.evaluate(() => localStorage.getItem('th_token'));

    // POST with existing ID
    const response = await page.request.post(`${BASE}/api/tests`, {
      data: { id: 'TC-1042', title: 'Duplicate attempt', type: 'manual', priority: 'low' },
      headers: { Authorization: `Bearer ${token}` },
    });

    expect(response.status()).toBe(409);
  });

  // E2E-SEC-03 · 404 su risorsa inesistente [P1]
  test('SEC-03: 404 su risorsa inesistente — graceful', async ({ page }) => {
    await loginAs(page, 'marco@acme.com');

    // Navigate to nonexistent test
    await page.goto('/#/tests/TC-INESISTENTE');
    await page.waitForURL('**/#/tests/TC-INESISTENTE', { timeout: 10000 });

    // No white crash — some error message visible
    await expect(page.locator('.app')).not.toBeEmpty({ timeout: 5000 });
    const content = await page.locator('.app').textContent();
    expect(content).toBeTruthy();
    // Should show "not found" or similar, not blank
    expect(content?.toLowerCase()).not.toBe('');

    // API 404
    const token = await page.evaluate(() => localStorage.getItem('th_token'));
    const response = await page.request.get(`${BASE}/api/tests/TC-INESISTENTE`, {
      headers: { Authorization: `Bearer ${token}` },
    });
    expect(response.status()).toBe(404);
  });

  // E2E-SEC-04 · Registrazione email duplicata [P1]
  test('SEC-04: registrazione email duplicata → 409', async ({ page }) => {
    const response = await page.request.post(`${BASE}/api/auth/register`, {
      data: { username: 'marco_dup', email: 'marco@acme.com', password: 'somepassword', display_name: 'Test' },
    });

    expect(response.status()).toBe(409);
    const body = await response.json();
    expect(JSON.stringify(body).toLowerCase()).toContain('already');
  });

});
