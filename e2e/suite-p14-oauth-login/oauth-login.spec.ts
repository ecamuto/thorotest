import { test, expect, Page } from '@playwright/test';
import { loginAs } from '../fixtures/auth';

// Suite P14 — OAuth login (SSO-01..04, frontend behaviors)
//
// The full Authorization Code flow needs live GitHub/Google credentials and a
// real browser redirect, which cannot run headless in CI. These tests cover
// every frontend behavior that does NOT require a live provider:
//   - login-page OAuth buttons + divider render
//   - clicking a button redirects the browser to the backend redirect endpoint
//   - the SPA's hash-param landing logic (#token / #oauth-confirm / #oauth-error)
// The provider redirect endpoints are intercepted so no real credentials run.

async function getToken(page: Page): Promise<string> {
  return page.evaluate(() => localStorage.getItem('th_token') || '');
}

async function clearToken(page: Page): Promise<void> {
  await page.evaluate(() => localStorage.removeItem('th_token'));
}

test.describe('Suite P14 — OAuth Login UI', () => {

  // OAUTH-UI-01 · Login page shows divider + branded provider buttons [P0]
  test('OAUTH-UI-01: "or continue with" divider and GitHub/Google buttons render below the form', async ({ page }) => {
    await page.goto('/');
    await page.waitForSelector('.login-page', { timeout: 10000 });

    await expect(page.getByText('or continue with')).toBeVisible();
    await expect(page.getByRole('button', { name: 'Continue with GitHub' })).toBeVisible();
    await expect(page.getByRole('button', { name: 'Continue with Google' })).toBeVisible();

    // Buttons live in the dedicated OAuth block, after the password form
    await expect(page.locator('.login-oauth-buttons .login-oauth-btn')).toHaveCount(2);
  });

  // OAUTH-UI-02 · GitHub button redirects browser to the backend redirect endpoint [P0]
  test('OAUTH-UI-02: clicking "Continue with GitHub" navigates to /api/auth/oauth/github/redirect', async ({ page }) => {
    await page.goto('/');
    await page.waitForSelector('.login-page', { timeout: 10000 });

    // Intercept the redirect endpoint so no live provider credentials are needed
    await page.route('**/api/auth/oauth/github/redirect', route =>
      route.fulfill({ status: 200, contentType: 'text/html', body: '<html><body>github</body></html>' }),
    );

    const navPromise = page.waitForRequest('**/api/auth/oauth/github/redirect', { timeout: 5000 });
    await page.getByRole('button', { name: 'Continue with GitHub' }).click();
    const req = await navPromise;
    expect(req.url()).toContain('/api/auth/oauth/github/redirect');
  });

  // OAUTH-UI-03 · Google button redirects browser to the backend redirect endpoint [P1]
  test('OAUTH-UI-03: clicking "Continue with Google" navigates to /api/auth/oauth/google/redirect', async ({ page }) => {
    await page.goto('/');
    await page.waitForSelector('.login-page', { timeout: 10000 });

    await page.route('**/api/auth/oauth/google/redirect', route =>
      route.fulfill({ status: 200, contentType: 'text/html', body: '<html><body>google</body></html>' }),
    );

    const navPromise = page.waitForRequest('**/api/auth/oauth/google/redirect', { timeout: 5000 });
    await page.getByRole('button', { name: 'Continue with Google' }).click();
    const req = await navPromise;
    expect(req.url()).toContain('/api/auth/oauth/google/redirect');
  });

  // OAUTH-UI-04 · #token=<jwt> landing stores the token and lands the user in the app [P0]
  test('OAUTH-UI-04: landing on #token=<jwt> stores the JWT, cleans the URL, and enters the app', async ({ page }) => {
    // Mint a real JWT via normal login, then simulate the OAuth callback landing
    await loginAs(page, 'marco@acme.com');
    const jwt = await getToken(page);
    expect(jwt.length).toBeGreaterThan(0);

    // Wipe session, then land exactly as the backend callback redirect would.
    // The query string forces a full document load (a hash-only goto is a
    // same-document navigation and would not remount AuthRoot's token parser).
    await clearToken(page);
    await page.goto(`/?oauth=callback#token=${jwt}`);

    // SPA picks up the token, redirects to overview, and /api/me succeeds.
    // Regex (not glob) because the ?oauth= query sits between host and #hash.
    await page.waitForURL(/#\/overview$/, { timeout: 10000 });
    expect(await getToken(page)).toBe(jwt);

    // The raw #token fragment is cleaned away (no token left in the URL)
    expect(page.url()).not.toContain('token=');
    // Authenticated chrome present (login form gone)
    await expect(page.locator('.login-page')).toHaveCount(0);
  });

  // OAUTH-UI-05 · #oauth-confirm=<token> landing shows the password confirmation screen [P0]
  test('OAUTH-UI-05: landing on #oauth-confirm=<token> renders the link-account confirmation screen', async ({ page }) => {
    await page.goto('/#oauth-confirm=fake-pending-token-123');

    // Confirmation screen, NOT the login form
    await expect(page.getByText('An account with this email exists.')).toBeVisible({ timeout: 10000 });
    await expect(page.getByRole('button', { name: 'Link account' })).toBeVisible();
    await expect(page.getByRole('button', { name: 'Cancel' })).toBeVisible();
    // Email/password login form is not shown
    await expect(page.getByRole('button', { name: 'Continue with GitHub' })).toHaveCount(0);
  });

  // OAUTH-UI-06 · Cancel on the confirm screen returns to login with nothing linked [P1]
  test('OAUTH-UI-06: Cancel on the confirm screen returns to the login form, no session issued', async ({ page }) => {
    await page.goto('/#oauth-confirm=fake-pending-token-123');

    await expect(page.getByText('An account with this email exists.')).toBeVisible({ timeout: 10000 });
    await page.getByRole('button', { name: 'Cancel' }).click();

    // Back to the standard login page with the OAuth buttons
    await expect(page.locator('.login-page')).toBeVisible({ timeout: 5000 });
    await expect(page.getByRole('button', { name: 'Continue with GitHub' })).toBeVisible();
    // No token was stored
    expect(await getToken(page)).toBe('');
  });

  // OAUTH-UI-07 · #oauth-error=cancelled shows a dismissible provider-specific notice [P1]
  test('OAUTH-UI-07: #oauth-error=cancelled&provider=github shows a dismissible cancellation notice', async ({ page }) => {
    await page.goto('/#oauth-error=cancelled&provider=github');

    await page.waitForSelector('.login-page', { timeout: 10000 });
    const notice = page.locator('.login-error', { hasText: 'Github sign-in was cancelled.' });
    await expect(notice).toBeVisible({ timeout: 5000 });

    // Dismiss clears the notice
    await notice.getByRole('button', { name: 'Dismiss' }).click();
    await expect(page.locator('.login-error', { hasText: 'sign-in was cancelled.' })).toHaveCount(0);
  });

  // OAUTH-UI-08 · #oauth-error=failed shows the generic failure notice [P1]
  test('OAUTH-UI-08: #oauth-error=failed shows the generic "Sign-in failed" notice', async ({ page }) => {
    await page.goto('/#oauth-error=failed');

    await page.waitForSelector('.login-page', { timeout: 10000 });
    await expect(page.locator('.login-error', { hasText: 'Sign-in failed, please try again.' }))
      .toBeVisible({ timeout: 5000 });
  });
});
