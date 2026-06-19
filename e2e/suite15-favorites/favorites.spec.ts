import { test, expect, request as pwRequest } from '@playwright/test';
import { loginAs } from '../fixtures/auth';

const BASE = 'http://localhost:8000';

// Helper: obtain a bearer token via the login API (mirrors fixtures/auth login).
async function apiToken(): Promise<string> {
  const ctx = await pwRequest.newContext();
  const res = await ctx.post(`${BASE}/api/auth/login`, {
    data: { email: 'marco@acme.com', password: 'demo123' },
  });
  const body = await res.json();
  await ctx.dispose();
  return body.access_token;
}

test.describe('Suite 15 — Folder Favorites', () => {

  test.beforeEach(async ({ page }) => {
    await loginAs(page, 'marco@acme.com');
    await page.click('.nav-item:has-text("Test library")');
    await page.waitForURL('**/#/library', { timeout: 5000 });
  });

  // FAV-01 · Toggle a folder favorite on, persists across reload, toggle off [P1]
  test('FAV-01: toggle favorite on/off and persist across reload', async ({ page }) => {
    // First top-level folder star starts un-favorited (seed creates no favorites).
    const star = page.locator('[title="Add to favorites"]').first();
    await expect(star).toBeVisible({ timeout: 8000 });
    await expect(star).toHaveText('☆');

    // Toggle ON
    await star.click();
    const starOn = page.locator('[title="Remove from favorites"]').first();
    await expect(starOn).toBeVisible({ timeout: 5000 });
    await expect(starOn).toHaveText('★');

    // Persist across reload (favorite is stored server-side per user)
    await page.reload();
    await page.waitForURL('**/#/library', { timeout: 5000 });
    await expect(page.locator('[title="Remove from favorites"]').first()).toBeVisible({ timeout: 8000 });

    // Toggle OFF — cleanup so the test is idempotent
    await page.locator('[title="Remove from favorites"]').first().click();
    await expect(page.locator('[title="Add to favorites"]').first()).toBeVisible({ timeout: 5000 });
  });

  // FAV-02 · API: add → list → remove round-trip [P1]
  test('FAV-02: favorites API add/list/remove round-trip', async () => {
    const token = await apiToken();
    const ctx = await pwRequest.newContext({
      extraHTTPHeaders: { Authorization: `Bearer ${token}` },
    });

    // Pick a real folder id from initial-data
    const initial = await (await ctx.get(`${BASE}/api/initial-data`)).json();
    const folderId = initial.folders[0].id;

    // Add
    const addRes = await ctx.post(`${BASE}/api/favorites`, { data: { folder_id: folderId } });
    expect(addRes.status()).toBe(201);
    expect((await addRes.json()).folder_id).toBe(folderId);

    // List contains it
    const listed = await (await ctx.get(`${BASE}/api/favorites`)).json();
    expect(listed.some((f: any) => f.folder_id === folderId)).toBeTruthy();

    // Remove
    const delRes = await ctx.delete(`${BASE}/api/favorites/${folderId}`);
    expect(delRes.status()).toBe(204);

    // No longer listed
    const after = await (await ctx.get(`${BASE}/api/favorites`)).json();
    expect(after.some((f: any) => f.folder_id === folderId)).toBeFalsy();

    await ctx.dispose();
  });

  // FAV-03 · API: unknown folder returns 404; unauthenticated returns 401 [P2]
  test('FAV-03: favorites API rejects unknown folder and unauthenticated calls', async () => {
    const token = await apiToken();
    const authed = await pwRequest.newContext({
      extraHTTPHeaders: { Authorization: `Bearer ${token}` },
    });
    const bad = await authed.post(`${BASE}/api/favorites`, { data: { folder_id: 'does-not-exist' } });
    expect(bad.status()).toBe(404);
    await authed.dispose();

    const anon = await pwRequest.newContext();
    const unauth = await anon.get(`${BASE}/api/favorites`);
    expect(unauth.status()).toBe(401);
    await anon.dispose();
  });
});
