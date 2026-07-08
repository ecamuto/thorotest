import { test, expect } from '@playwright/test';
import { loginAs } from '../fixtures/auth';

const BASE = 'http://localhost:8000';
const REPO = 'https://github.com/acme/web-e2e-ghs';

test.describe('Suite P16 — Tests as Code (GitHub sync)', () => {

  async function getToken(page: any): Promise<string> {
    return await page.evaluate(() => localStorage.getItem('th_token') ?? '');
  }

  async function cleanupGithub(page: any, token: string) {
    const list = await page.request.get(`${BASE}/api/integrations`, { headers: { Authorization: `Bearer ${token}` } });
    for (const i of (await list.json()).filter((x: any) => (x.config?.repo_url || '').includes('e2e-ghs') || x.id.startsWith('int-e2e-ghs'))) {
      await page.request.delete(`${BASE}/api/integrations/${i.id}`, { headers: { Authorization: `Bearer ${token}` } }).catch(() => {});
    }
  }

  // GHS-01 · Add GitHub integration with repo config via 2-step modal [P1]
  test('GHS-01: add github integration with config shows Sync button', async ({ page }) => {
    await loginAs(page, 'marco@acme.com');
    const token = await getToken(page);

    // Remove seeded int-github so GitHub appears in the provider picker
    await page.request.delete(`${BASE}/api/integrations/int-github`, { headers: { Authorization: `Bearer ${token}` } }).catch(() => {});
    await cleanupGithub(page, token);

    await page.goto('/#/integrations');
    await expect(page.locator('h1:has-text("Integrations")')).toBeVisible({ timeout: 10000 });

    await page.click('button:has-text("Add integration")');
    await expect(page.locator('text=Add integration').first()).toBeVisible({ timeout: 5000 });
    await page.locator('button').filter({ hasText: 'GitHub' }).first().click();

    // Configure step — github config fields are rendered
    await expect(page.locator('text=Configure GitHub')).toBeVisible({ timeout: 5000 });
    await page.fill('input[placeholder*="github.com/org/repo"]', REPO);
    await page.fill('input[placeholder="main"]', 'main');
    await page.fill('input[placeholder="tests/"]', 'tests/');
    await page.fill('input[placeholder="ghp_…"]', 'ghp_e2e_secret_token');

    const [resp] = await Promise.all([
      page.waitForResponse(r => r.url().includes('/api/integrations') && r.request().method() === 'POST'),
      page.click('button:has-text("Connect")'),
    ]);
    expect(resp.status()).toBe(201);

    // The created github row (config.repo_url set) renders a Sync button
    const row = page.locator('tr')
      .filter({ hasText: 'GitHub' })
      .filter({ has: page.locator('button:has-text("Sync")') });
    await expect(row.first()).toBeVisible({ timeout: 8000 });

    await cleanupGithub(page, token);
  });

  // GHS-02 · PAT is never returned to the client (redacted) [P1]
  test('GHS-02: stored token is redacted in API response', async ({ page }) => {
    await loginAs(page, 'marco@acme.com');
    const token = await getToken(page);
    await cleanupGithub(page, token);

    const id = `int-e2e-ghs-redact-${Date.now()}`;
    await page.request.post(`${BASE}/api/integrations`, {
      data: { id, name: 'GitHub', type: 'vcs_ci', icon: 'github',
              config: { repo_url: REPO, branch: 'main', path: 'tests/', token: 'ghp_supersecret' } },
      headers: { Authorization: `Bearer ${token}`, 'Content-Type': 'application/json' },
    });

    const list = await page.request.get(`${BASE}/api/integrations`, { headers: { Authorization: `Bearer ${token}` } });
    const intg = (await list.json()).find((i: any) => i.id === id);
    expect(intg).toBeDefined();
    expect(intg.config.token).toBe('');          // never leaked
    expect(intg.config.token_set).toBe(true);     // but UI knows one is set

    await cleanupGithub(page, token);
  });

  // GHS-03 · Editing config with a blank token preserves the stored one [P1]
  test('GHS-03: blank token on update does not wipe the stored token', async ({ page }) => {
    await loginAs(page, 'marco@acme.com');
    const token = await getToken(page);
    await cleanupGithub(page, token);

    const id = `int-e2e-ghs-keep-${Date.now()}`;
    await page.request.post(`${BASE}/api/integrations`, {
      data: { id, name: 'GitHub', type: 'vcs_ci', icon: 'github',
              config: { repo_url: REPO, branch: 'main', path: '', token: 'ghp_keepme' } },
      headers: { Authorization: `Bearer ${token}`, 'Content-Type': 'application/json' },
    });

    // PATCH with blank token, as the redacted edit form would send
    const patch = await page.request.patch(`${BASE}/api/integrations/${id}`, {
      data: { config: { repo_url: REPO, branch: 'dev', path: '', token: '' } },
      headers: { Authorization: `Bearer ${token}`, 'Content-Type': 'application/json' },
    });
    expect(patch.status()).toBe(200);
    const updated = await patch.json();
    expect(updated.config.branch).toBe('dev');
    expect(updated.config.token).toBe('');         // still redacted in response
    expect(updated.config.token_set).toBe(true);   // and still set server-side

    await cleanupGithub(page, token);
  });

  // GHS-04 · Sync against a non-github repo surfaces an error in the UI [P1]
  test('GHS-04: sync of a non-github repo shows an error message', async ({ page }) => {
    await loginAs(page, 'marco@acme.com');
    const token = await getToken(page);
    await cleanupGithub(page, token);

    const id = `int-e2e-ghs-gl-${Date.now()}`;
    await page.request.post(`${BASE}/api/integrations`, {
      data: { id, name: 'GitHub', type: 'vcs_ci', icon: 'github',
              config: { repo_url: 'https://gitlab.com/acme/web-e2e-ghs', branch: 'main', path: '' } },
      headers: { Authorization: `Bearer ${token}`, 'Content-Type': 'application/json' },
    });

    // API contract: non-github repo → 400
    const apiSync = await page.request.post(`${BASE}/api/integrations/${id}/sync`, { headers: { Authorization: `Bearer ${token}` } });
    expect(apiSync.status()).toBe(400);

    // UI: clicking Sync surfaces the error text in the row
    await page.goto('/#/integrations');
    const row = page.locator('tr').filter({ hasText: 'GitHub' }).filter({ has: page.locator('button:has-text("Sync")') }).first();
    await row.locator('button:has-text("Sync")').click();
    await expect(row.locator('text=/github repo url/i')).toBeVisible({ timeout: 8000 });

    await cleanupGithub(page, token);
  });

  // GHS-05 · Live sync reaches GitHub and returns a stats payload [P2]
  // Network-dependent (api.github.com). Tolerates unauthenticated rate-limit.
  test('GHS-05: live sync against a public repo returns commit + stats', async ({ page }) => {
    await loginAs(page, 'marco@acme.com');
    const token = await getToken(page);
    await cleanupGithub(page, token);

    const id = `int-e2e-ghs-live-${Date.now()}`;
    await page.request.post(`${BASE}/api/integrations`, {
      data: { id, name: 'GitHub', type: 'vcs_ci', icon: 'github',
              config: { repo_url: 'https://github.com/octocat/Hello-World', branch: 'master', path: '' } },
      headers: { Authorization: `Bearer ${token}`, 'Content-Type': 'application/json' },
    });

    const resp = await page.request.post(`${BASE}/api/integrations/${id}/sync`, { headers: { Authorization: `Bearer ${token}` } });
    // 502 only if GitHub rate-limited/unreachable — skip rather than flake.
    test.skip(resp.status() === 502, 'GitHub unreachable or rate-limited');
    expect(resp.status()).toBe(200);
    const body = await resp.json();
    expect(typeof body.commit).toBe('string');
    expect(body.commit.length).toBeGreaterThan(0);
    expect(typeof body.created).toBe('number');
    expect(typeof body.files).toBe('number');   // Hello-World has no YAML → 0

    await cleanupGithub(page, token);
  });

});
