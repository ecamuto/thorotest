import { test, expect, Page } from '@playwright/test';
import { loginAs } from '../fixtures/auth';

// Suite P15 — TOTP 2FA (TOTP-01..05, frontend behaviors)
//
// Live TOTP codes require a real authenticator and device clock.
// These tests cover every deterministic frontend behavior via page.route stubs:
//   - enrollment QR/secret render (Step 1) and recovery-ack gate (Step 3)
//   - TwoFAStep screen appears after password for a 2FA user (no token stored)
//   - invalid-code error and rate-limit countdown UX on TwoFAStep
//   - recovery-code login: success stub lands user in app with token set

async function getToken(page: Page): Promise<string> {
  return page.evaluate(() => localStorage.getItem('th_token') || '');
}

async function clearToken(page: Page): Promise<void> {
  await page.evaluate(() => localStorage.removeItem('th_token'));
}

// Navigate to Settings -> Security tab (requires being logged in)
async function openSecurityTab(page: Page): Promise<void> {
  await page.goto('/#/settings');
  await page.waitForSelector('.nav-item', { timeout: 10000 });
  await page.getByRole('button', { name: 'Security' }).click();
  await page.waitForSelector('text=Two-factor authentication', { timeout: 8000 });
}

test.describe('Suite P15 — TOTP 2FA UI', () => {

  // P15-01 · Enrollment Step 1 shows QR and copyable secret [P0]
  test('P15-01: Enable dialog shows QR image and copyable secret in Step 1', async ({ page }) => {
    // Stub the setup endpoint so we get deterministic data
    await page.route('**/api/me/2fa/setup', route =>
      route.fulfill({
        status: 200,
        contentType: 'application/json',
        body: JSON.stringify({
          secret: 'JBSWY3DPEHPK3PXP',
          qr_data_uri: 'data:image/png;base64,iVBORw0KGgoAAAANSUhEUgAAAAEAAAABCAYAAAAfFcSJAAAADUlEQVR42mNk+M9QDwADhgGAWjR9awAAAABJRU5ErkJggg==',
        }),
      })
    );

    // Stub count endpoint so SecurityTab renders inactive state
    await page.route('**/api/me/2fa/recovery-codes/count', route =>
      route.fulfill({
        status: 200,
        contentType: 'application/json',
        body: JSON.stringify({ remaining: 0, enabled: false }),
      })
    );

    await loginAs(page, 'marco@acme.com');
    await openSecurityTab(page);

    // Inactive state: Enable button is present
    await expect(page.getByRole('button', { name: 'Enable two-factor authentication' })).toBeVisible();

    // Click Enable -> enrollment dialog Step 1
    await page.getByRole('button', { name: 'Enable two-factor authentication' }).click();
    await page.waitForSelector('text=Set up authenticator app', { timeout: 5000 });

    // QR image renders
    const qrImg = page.locator('img[alt="TOTP QR code"]');
    await expect(qrImg).toBeVisible();
    const src = await qrImg.getAttribute('src');
    expect(src).toMatch(/^data:image/);

    // Copyable secret input renders with the secret value
    const secretInput = page.locator('[data-testid="totp-secret"]');
    await expect(secretInput).toBeVisible();
    const val = await secretInput.inputValue();
    expect(val).toBe('JBSWY3DPEHPK3PXP');
  });

  // P15-02 · Recovery-code acknowledgment gate (Finish disabled until checkbox) [P0]
  test('P15-02: Finish button is disabled until "I have saved my codes" checkbox is ticked', async ({ page }) => {
    const fakeCodes = Array.from({ length: 10 }, (_, i) => `ab${i}c-defg`);

    await page.route('**/api/me/2fa/setup', route =>
      route.fulfill({
        status: 200,
        contentType: 'application/json',
        body: JSON.stringify({
          secret: 'JBSWY3DPEHPK3PXP',
          qr_data_uri: 'data:image/png;base64,iVBORw0KGgoAAAANSUhEUgAAAAEAAAABCAYAAAAfFcSJAAAADUlEQVR42mNk+M9QDwADhgGAWjR9awAAAABJRU5ErkJggg==',
        }),
      })
    );

    await page.route('**/api/me/2fa/enable', route =>
      route.fulfill({
        status: 200,
        contentType: 'application/json',
        body: JSON.stringify({ recovery_codes: fakeCodes }),
      })
    );

    await page.route('**/api/me/2fa/recovery-codes/count', route =>
      route.fulfill({
        status: 200,
        contentType: 'application/json',
        body: JSON.stringify({ remaining: 0, enabled: false }),
      })
    );

    await loginAs(page, 'marco@acme.com');
    await openSecurityTab(page);
    await page.getByRole('button', { name: 'Enable two-factor authentication' }).click();
    await page.waitForSelector('text=Set up authenticator app', { timeout: 5000 });

    // Step 1 -> Next
    await page.getByRole('button', { name: 'Next' }).click();
    await page.waitForSelector('text=Verify your authenticator', { timeout: 5000 });

    // Step 2: submit any code (stub accepts it)
    await page.fill('input[placeholder="000000"]', '123456');
    await page.getByRole('button', { name: 'Verify' }).click();

    // Step 3: recovery codes should render
    await page.waitForSelector('text=Save your recovery codes', { timeout: 5000 });

    // Finish button disabled before ack
    const finishBtn = page.locator('[data-testid="finish-btn"]');
    await expect(finishBtn).toBeDisabled();

    // Tick the checkbox
    await page.locator('[data-testid="ack-checkbox"]').check();

    // Finish button now enabled
    await expect(finishBtn).toBeEnabled();
  });

  // P15-03 · 2FA login prompt: TwoFAStep shown, no token in localStorage [P0]
  test('P15-03: 2FA user sees TwoFAStep after password; no JWT stored in localStorage', async ({ page }) => {
    await page.route('**/api/auth/login', route =>
      route.fulfill({
        status: 200,
        contentType: 'application/json',
        body: JSON.stringify({ status: '2fa_required', partial_token: 'fake-partial-token' }),
      })
    );

    await page.goto('/');
    await page.waitForSelector('.login-page', { timeout: 10000 });

    await page.fill('input[type="email"]', 'marco@acme.com');
    await page.fill('input[type="password"]', 'demo123');
    await page.click('button[type="submit"]');

    // TwoFAStep screen should appear
    await page.waitForSelector('text=Two-factor authentication', { timeout: 8000 });
    await expect(page.getByText('Enter the 6-digit code from your authenticator app, or a recovery code.')).toBeVisible();

    // CRITICAL: no JWT stored in localStorage
    const token = await getToken(page);
    expect(token).toBe('');
  });

  // P15-04a · Invalid code: generic error shown [P0]
  test('P15-04a: Invalid code (400) shows generic "Invalid code" error on TwoFAStep', async ({ page }) => {
    await page.route('**/api/auth/login', route =>
      route.fulfill({
        status: 200,
        contentType: 'application/json',
        body: JSON.stringify({ status: '2fa_required', partial_token: 'fake-partial-token' }),
      })
    );

    await page.route('**/api/auth/login/2fa', route =>
      route.fulfill({
        status: 400,
        contentType: 'application/json',
        body: JSON.stringify({ detail: 'Invalid code' }),
      })
    );

    await page.goto('/');
    await page.waitForSelector('.login-page', { timeout: 10000 });
    await page.fill('input[type="email"]', 'marco@acme.com');
    await page.fill('input[type="password"]', 'demo123');
    await page.click('button[type="submit"]');

    await page.waitForSelector('text=Two-factor authentication', { timeout: 8000 });

    // Submit a wrong code
    await page.fill('input[placeholder="000000 or xxxx-xxxx"]', '000000');
    await page.getByRole('button', { name: 'Verify' }).click();

    // Generic error shown (no TOTP vs recovery leakage)
    await expect(page.locator('.login-error', { hasText: 'Invalid code' })).toBeVisible({ timeout: 5000 });
    // No mention of "totp" or "recovery" in the error
    const errorText = await page.locator('.login-error').textContent();
    expect(errorText?.toLowerCase()).not.toContain('totp');
    expect(errorText?.toLowerCase()).not.toContain('recovery');
  });

  // P15-04b · Rate limit (429): countdown shown, no factor-specific text [P0]
  test('P15-04b: Rate limit (429) shows "Try again in Ns" countdown on TwoFAStep', async ({ page }) => {
    await page.route('**/api/auth/login', route =>
      route.fulfill({
        status: 200,
        contentType: 'application/json',
        body: JSON.stringify({ status: '2fa_required', partial_token: 'fake-partial-token' }),
      })
    );

    await page.route('**/api/auth/login/2fa', route =>
      route.fulfill({
        status: 429,
        contentType: 'application/json',
        body: JSON.stringify({ detail: 'Too many attempts. Try again in 25s' }),
      })
    );

    await page.goto('/');
    await page.waitForSelector('.login-page', { timeout: 10000 });
    await page.fill('input[type="email"]', 'marco@acme.com');
    await page.fill('input[type="password"]', 'demo123');
    await page.click('button[type="submit"]');

    await page.waitForSelector('text=Two-factor authentication', { timeout: 8000 });

    await page.fill('input[placeholder="000000 or xxxx-xxxx"]', '000000');
    await page.getByRole('button', { name: 'Verify' }).click();

    // Countdown message appears
    await expect(page.locator('.login-error', { hasText: 'Try again in' })).toBeVisible({ timeout: 5000 });

    // Submit button disabled while countdown is active
    await expect(page.getByRole('button', { name: 'Verify' })).toBeDisabled();

    // No factor-specific text in the countdown message
    const countdownText = await page.locator('.login-error').last().textContent();
    expect(countdownText?.toLowerCase()).not.toContain('totp');
    expect(countdownText?.toLowerCase()).not.toContain('recovery');
  });

  // P15-05 · Recovery-code login: success stub lands user in app [P0]
  test('P15-05: Valid code (success stub) on TwoFAStep lands user in app at #/overview with token set', async ({ page }) => {
    const fakeJwt = 'eyJhbGciOiJIUzI1NiIsInR5cCI6IkpXVCJ9.fake.sig';

    await page.route('**/api/auth/login', route =>
      route.fulfill({
        status: 200,
        contentType: 'application/json',
        body: JSON.stringify({ status: '2fa_required', partial_token: 'fake-partial-token' }),
      })
    );

    await page.route('**/api/auth/login/2fa', route =>
      route.fulfill({
        status: 200,
        contentType: 'application/json',
        body: JSON.stringify({
          access_token: fakeJwt,
          token_type: 'bearer',
          user: {
            id: 1, email: 'marco@acme.com', username: 'marco',
            display_name: 'Marco Rossi', role: 'admin', language: 'en',
            totp_enabled: true,
          },
        }),
      })
    );

    // Stub /api/me so AuthRoot re-check succeeds after token is set
    await page.route('**/api/me', route =>
      route.fulfill({
        status: 200,
        contentType: 'application/json',
        body: JSON.stringify({
          id: 1, email: 'marco@acme.com', username: 'marco',
          display_name: 'Marco Rossi', role: 'admin', language: 'en',
          totp_enabled: true,
        }),
      })
    );

    // Stub initial-data so TH_API.init() doesn't fail
    await page.route('**/api/initial-data', route =>
      route.fulfill({ status: 200, contentType: 'application/json', body: '{}' })
    );

    await page.goto('/');
    await page.waitForSelector('.login-page', { timeout: 10000 });
    await page.fill('input[type="email"]', 'marco@acme.com');
    await page.fill('input[type="password"]', 'demo123');
    await page.click('button[type="submit"]');

    await page.waitForSelector('text=Two-factor authentication', { timeout: 8000 });

    // Enter a recovery-format code (8 alphanumeric + dash = longer than TOTP)
    await page.fill('input[placeholder="000000 or xxxx-xxxx"]', 'ab3f-k2m8');
    await page.getByRole('button', { name: 'Verify' }).click();

    // Lands in the app at #/overview
    await page.waitForURL(/#\/overview$/, { timeout: 10000 });

    // Token is stored in localStorage
    const token = await getToken(page);
    expect(token).toBe(fakeJwt);

    // Login form is gone
    await expect(page.locator('.login-page')).toHaveCount(0);
  });

  // P15-06 · Back button on TwoFAStep returns to login form [P1]
  test('P15-06: Back button on TwoFAStep returns to the login page, no session', async ({ page }) => {
    await page.route('**/api/auth/login', route =>
      route.fulfill({
        status: 200,
        contentType: 'application/json',
        body: JSON.stringify({ status: '2fa_required', partial_token: 'fake-partial-token' }),
      })
    );

    await page.goto('/');
    await page.waitForSelector('.login-page', { timeout: 10000 });
    await page.fill('input[type="email"]', 'marco@acme.com');
    await page.fill('input[type="password"]', 'demo123');
    await page.click('button[type="submit"]');

    await page.waitForSelector('text=Two-factor authentication', { timeout: 8000 });

    // Click Back
    await page.getByRole('button', { name: 'Back' }).click();

    // Should return to the login page
    await expect(page.locator('.login-page')).toBeVisible({ timeout: 5000 });
    await expect(page.getByRole('button', { name: /sign in/i })).toBeVisible();

    // No token stored
    expect(await getToken(page)).toBe('');
  });
});
