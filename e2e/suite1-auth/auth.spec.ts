import { test, expect } from '@playwright/test';
import { loginAs } from '../fixtures/auth';

const BASE = 'http://localhost:8000';

test.describe('Suite 1 — Autenticazione', () => {

  // E2E-AUTH-01 · Login con credenziali valide [P0]
  test('AUTH-01: login con credenziali valide', async ({ page }) => {
    // Ensure no token
    await page.goto('/');
    await page.evaluate(() => localStorage.removeItem('th_token'));
    await page.goto('/');

    // LoginPage must appear
    await expect(page.locator('.login-page')).toBeVisible({ timeout: 10000 });

    // Fill and submit
    await page.fill('input[type="email"]', 'marco@acme.com');
    await page.fill('input[type="password"]', 'demo123');
    await page.click('button[type="submit"]');

    // Redirect to overview
    await page.waitForURL('**/#/overview', { timeout: 10000 });

    // Sidebar footer shows "Marco Rossi"
    const footer = page.locator('.sidebar-footer .user-name');
    await expect(footer).toContainText('Marco Rossi', { timeout: 5000 });

    // localStorage token present
    const token = await page.evaluate(() => localStorage.getItem('th_token'));
    expect(token).toBeTruthy();

    // GET /api/me returns 200
    const response = await page.request.get(`${BASE}/api/me`, {
      headers: { Authorization: `Bearer ${token}` },
    });
    expect(response.status()).toBe(200);
  });

  // E2E-AUTH-02 · Login con credenziali errate [P0]
  test('AUTH-02: login con credenziali errate', async ({ page }) => {
    await page.goto('/');
    await page.evaluate(() => localStorage.removeItem('th_token'));
    await page.goto('/');

    await expect(page.locator('.login-page')).toBeVisible({ timeout: 10000 });

    await page.fill('input[type="email"]', 'marco@acme.com');
    await page.fill('input[type="password"]', 'sbagliata');
    await page.click('button[type="submit"]');

    // Error message inline, no redirect
    await expect(page.locator('.login-error')).toBeVisible({ timeout: 5000 });
    await expect(page.locator('.login-page')).toBeVisible();

    // Token absent
    const token = await page.evaluate(() => localStorage.getItem('th_token'));
    expect(token).toBeNull();
  });

  // E2E-AUTH-03 · Selezione rapida utente demo [P1]
  test('AUTH-03: selezione rapida utente demo Lisa Park', async ({ page }) => {
    await page.goto('/');
    await page.evaluate(() => localStorage.removeItem('th_token'));
    await page.goto('/');

    await expect(page.locator('.login-page')).toBeVisible({ timeout: 10000 });

    // Click demo card for Lisa Park
    await page.click('.login-demo-row:has-text("Lisa Park")');

    // Fields populated with lisa@acme.com
    await expect(page.locator('input[type="email"]')).toHaveValue('lisa@acme.com');

    // Sign in
    await page.click('button[type="submit"]');
    await page.waitForURL('**/#/overview', { timeout: 10000 });

    // Authenticated as Lisa Park
    const footer = page.locator('.sidebar-footer .user-name');
    await expect(footer).toContainText('Lisa Park', { timeout: 5000 });
  });

  // E2E-AUTH-04 · Logout [P0]
  test('AUTH-04: logout', async ({ page }) => {
    await loginAs(page, 'marco@acme.com');

    // Click logout button in sidebar footer
    await page.click('.sidebar-footer button[title="Sign out"]');

    // LoginPage appears
    await expect(page.locator('.login-page')).toBeVisible({ timeout: 10000 });

    // Token absent
    const token = await page.evaluate(() => localStorage.getItem('th_token'));
    expect(token).toBeNull();
  });

  // E2E-AUTH-05 · Token scaduto/invalido [P1]
  test('AUTH-05: token invalido → redirect a LoginPage', async ({ page }) => {
    await page.goto('/');
    // Set invalid token
    await page.evaluate(() => localStorage.setItem('th_token', 'token_invalido'));

    // Reload
    await page.reload();

    // Should show LoginPage (not blank)
    await expect(page.locator('.login-page')).toBeVisible({ timeout: 10000 });

    // Token removed
    const token = await page.evaluate(() => localStorage.getItem('th_token'));
    expect(token).toBeNull();
  });

  // E2E-AUTH-06 · Link diretto senza auth → login → deep link [P1]
  test('AUTH-06: link diretto senza auth poi login porta alla view', async ({ page }) => {
    // Navigate directly without token
    await page.goto('/');
    await page.evaluate(() => localStorage.removeItem('th_token'));
    await page.goto('/#/tests/TC-1042');

    // LoginPage appears
    await expect(page.locator('.login-page')).toBeVisible({ timeout: 10000 });

    // Login
    await page.fill('input[type="email"]', 'marco@acme.com');
    await page.fill('input[type="password"]', 'demo123');
    await page.click('button[type="submit"]');

    // After login, TestDetail for TC-1042 loads
    await page.waitForURL('**/#/tests/TC-1042', { timeout: 15000 });
    await expect(page.locator('.test-detail, [data-screen-label="test-detail"]')).toBeVisible({ timeout: 10000 });
  });

});
