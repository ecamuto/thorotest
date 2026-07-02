import { test, expect } from '@playwright/test';

const BASE = 'http://localhost:8000';

// Full token round-trip (email interception) is covered by pytest
// (backend/tests/test_password_reset.py). This suite covers the UI plumbing:
// forms render, API is wired, errors surface, no user enumeration.
test.describe('Suite P17 — Password reset', () => {

  // PWRESET-01 · Forgot-password link on login page opens the email form [P1]
  test('PWRESET-01: forgot link opens email form and submits', async ({ page }) => {
    await page.goto('/');
    await page.waitForSelector('.login-page', { timeout: 10000 });

    await page.click('button:has-text("Forgot password?")');
    await expect(page.locator('button:has-text("Send reset link")')).toBeVisible();

    await page.fill('input[type="email"]', 'marco@acme.com');
    const [response] = await Promise.all([
      page.waitForResponse(r => r.url().includes('/api/auth/forgot-password')),
      page.click('button:has-text("Send reset link")'),
    ]);
    expect(response.status()).toBe(202);

    // Generic confirmation (no user enumeration)
    await expect(page.locator('.login-page')).toContainText('If that email exists');
  });

  // PWRESET-02 · Unknown email gets the same generic response [P1]
  test('PWRESET-02: unknown email returns same 202 + generic message', async ({ page }) => {
    const res = await page.request.post(`${BASE}/api/auth/forgot-password`, {
      data: { email: 'ghost@nowhere.example' },
      headers: { 'Content-Type': 'application/json' },
    });
    expect(res.status()).toBe(202);
    const body = await res.json();
    expect(body.detail).toContain('If that email exists');
  });

  // PWRESET-03 · Reset link route renders the new-password form [P1]
  test('PWRESET-03: #/reset-password/<token> shows reset form', async ({ page }) => {
    await page.goto('/#/reset-password/some-token-value');
    await page.waitForSelector('.login-page', { timeout: 10000 });
    await expect(page.locator('button:has-text("Set new password")')).toBeVisible();
  });

  // PWRESET-04 · Bogus token → API 400 surfaces in the form [P1]
  test('PWRESET-04: invalid token shows error', async ({ page }) => {
    await page.goto('/#/reset-password/bogus-token');
    await page.waitForSelector('.login-page', { timeout: 10000 });

    await page.fill('input[type="password"]', 'newpassword1');
    const [response] = await Promise.all([
      page.waitForResponse(r => r.url().includes('/api/auth/reset-password')),
      page.click('button:has-text("Set new password")'),
    ]);
    expect(response.status()).toBe(400);
    await expect(page.locator('.login-error')).toContainText(/invalid or expired/i);
  });

  // PWRESET-05 · Back to sign in returns to the login form [P2]
  test('PWRESET-05: back link returns to login form', async ({ page }) => {
    await page.goto('/');
    await page.waitForSelector('.login-page', { timeout: 10000 });
    await page.click('button:has-text("Forgot password?")');
    await page.click('button:has-text("Back to sign in")');
    await expect(page.locator('button[type="submit"]')).toContainText(/sign in/i);
  });
});
