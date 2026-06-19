import { test as base, Page } from '@playwright/test';

async function loginAs(page: Page, email: string, password = 'demo123') {
  await page.goto('/');
  await page.waitForSelector('.login-page', { timeout: 10000 });
  await page.fill('input[type="email"]', email);
  await page.fill('input[type="password"]', password);
  await page.click('button[type="submit"]');
  await page.waitForURL('**/#/overview', { timeout: 10000 });
}

export const test = base.extend<{ authenticatedPage: Page }>({
  authenticatedPage: async ({ page }, use) => {
    await loginAs(page, 'marco@acme.com');
    await use(page);
  },
});

export { loginAs };
export { expect } from '@playwright/test';
