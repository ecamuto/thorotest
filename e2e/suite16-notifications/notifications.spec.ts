import { test, expect, request as pwRequest } from '@playwright/test';
import { loginAs } from '../fixtures/auth';

const BASE = 'http://localhost:8000';

async function authedContext() {
  const ctx0 = await pwRequest.newContext();
  const res = await ctx0.post(`${BASE}/api/auth/login`, {
    data: { email: 'marco@acme.com', password: 'demo123' },
  });
  const token = (await res.json()).access_token;
  await ctx0.dispose();
  return pwRequest.newContext({ extraHTTPHeaders: { Authorization: `Bearer ${token}` } });
}

test.describe('Suite 16 — Notifications', () => {

  // NOTIF-01 · Bell renders and opens an (empty) dropdown [P1]
  test('NOTIF-01: notification bell opens dropdown with empty state', async ({ page }) => {
    await loginAs(page, 'marco@acme.com');
    const bell = page.locator('button[aria-label="Notifications"]');
    await expect(bell).toBeVisible({ timeout: 8000 });

    await bell.click();
    // Dropdown header + empty state (seed creates no notifications)
    await expect(page.locator('text=No notifications')).toBeVisible({ timeout: 5000 });
  });

  // NOTIF-02 · API: list returns an array, requires auth [P1]
  test('NOTIF-02: notifications list API returns array and requires auth', async () => {
    const ctx = await authedContext();
    const res = await ctx.get(`${BASE}/api/notifications?limit=20`);
    expect(res.status()).toBe(200);
    expect(Array.isArray(await res.json())).toBeTruthy();
    await ctx.dispose();

    const anon = await pwRequest.newContext();
    const unauth = await anon.get(`${BASE}/api/notifications`);
    expect(unauth.status()).toBe(401);
    await anon.dispose();
  });

  // NOTIF-03 · API: config GET defaults, PUT round-trip [P1]
  test('NOTIF-03: notification config GET/PUT round-trip', async () => {
    const ctx = await authedContext();

    // Defaults
    const def = await (await ctx.get(`${BASE}/api/notifications/config`)).json();
    expect(def.notify_run_complete).toBe(true);
    expect(def.consecutive_fail_threshold).toBe(3);

    // Update
    const updated = await (await ctx.put(`${BASE}/api/notifications/config`, {
      data: { ...def, consecutive_fail_threshold: 5, slack_enabled: true },
    })).json();
    expect(updated.consecutive_fail_threshold).toBe(5);
    expect(updated.slack_enabled).toBe(true);

    // Persisted on re-GET
    const reread = await (await ctx.get(`${BASE}/api/notifications/config`)).json();
    expect(reread.consecutive_fail_threshold).toBe(5);

    // Restore defaults (idempotent)
    await ctx.put(`${BASE}/api/notifications/config`, {
      data: { ...def, consecutive_fail_threshold: 3, slack_enabled: false },
    });
    await ctx.dispose();
  });

  // NOTIF-04 · API: mark-all-read succeeds, rejects unauthenticated [P2]
  test('NOTIF-04: mark-all-read endpoint works and is protected', async () => {
    const ctx = await authedContext();
    const res = await ctx.post(`${BASE}/api/notifications/mark-all-read`);
    expect(res.status()).toBe(200);
    expect((await res.json()).ok).toBe(true);
    await ctx.dispose();

    const anon = await pwRequest.newContext();
    const unauth = await anon.post(`${BASE}/api/notifications/mark-all-read`);
    expect(unauth.status()).toBe(401);
    await anon.dispose();
  });
});
