import { test, expect } from '@playwright/test';
import { loginAs } from '../fixtures/auth';

const BASE = 'http://localhost:8000';

test.describe('Suite 10 — Settings', () => {

  async function goToSettings(page: any, tab: string = 'profile') {
    await loginAs(page, 'marco@acme.com');
    await page.goto('/#/settings');
    await expect(page.locator('.app')).toBeVisible({ timeout: 8000 });
    // Click the tab button
    await page.click(`button:has-text("${tab.charAt(0).toUpperCase() + tab.slice(1)}")`);
  }

  // SETT-01 · Navigazione a Settings [P1]
  test('SETT-01: navigate to settings page', async ({ page }) => {
    await loginAs(page, 'marco@acme.com');
    await page.goto('/#/settings');
    // Settings sidebar visible
    await expect(page.locator('text=Profile').first()).toBeVisible({ timeout: 8000 });
    await expect(page.locator('text=Password').first()).toBeVisible();
    await expect(page.locator('text=Projects').first()).toBeVisible();
    await expect(page.locator('text=Categories').first()).toBeVisible();
    await expect(page.locator('text=Folders').first()).toBeVisible();
    // URL updated
    expect(page.url()).toContain('#/settings');
  });

  // SETT-02 · Aggiorna display name [P1]
  test('SETT-02: update display name in profile tab', async ({ page }) => {
    await loginAs(page, 'marco@acme.com');
    await page.goto('/#/settings');
    await expect(page.locator('input[placeholder="Your name"]')).toBeVisible({ timeout: 8000 });

    // Change display name
    const nameInput = page.locator('input[placeholder="Your name"]');
    await nameInput.triple_click ? page.locator('input[placeholder="Your name"]').fill('Marco Rossi Updated') : await nameInput.fill('');
    await page.fill('input[placeholder="Your name"]', 'Marco Rossi Updated');
    await page.click('button:has-text("Save changes")');

    // Assert PUT /api/me was called — verify "Saved." appears
    await expect(page.locator('text=Saved.')).toBeVisible({ timeout: 8000 });

    // Restore original name
    await page.fill('input[placeholder="Your name"]', 'Marco Rossi');
    await page.click('button:has-text("Save changes")');
    await expect(page.locator('text=Saved.')).toBeVisible({ timeout: 5000 });
  });

  // SETT-03 · Email conflict [P1]
  test('SETT-03: update email to existing email shows conflict error', async ({ page }) => {
    await loginAs(page, 'marco@acme.com');
    await page.goto('/#/settings');
    await expect(page.locator('input[placeholder="you@example.com"]')).toBeVisible({ timeout: 8000 });

    // Try to set email to lisa's (already registered)
    await page.fill('input[placeholder="you@example.com"]', 'lisa@acme.com');
    await page.click('button:has-text("Save changes")');

    // Error message shown
    await expect(page.locator('text=/Email already|in use/i')).toBeVisible({ timeout: 8000 });

    // Also verify via API directly
    const token = await page.evaluate(() => localStorage.getItem('th_token'));
    const res = await page.request.put(`${BASE}/api/me`, {
      data: { email: 'lisa@acme.com' },
      headers: { Authorization: `Bearer ${token}`, 'Content-Type': 'application/json' },
    });
    expect(res.status()).toBe(409);

    // Restore
    await page.fill('input[placeholder="you@example.com"]', 'marco@acme.com');
    await page.click('button:has-text("Save changes")');
    await page.waitForTimeout(500);
  });

  // SETT-04 · Cambio password — successo [P1]
  test('SETT-04: change password success', async ({ page }) => {
    await loginAs(page, 'marco@acme.com');
    await page.goto('/#/settings');
    await page.click('button:has-text("Password")');

    await expect(page.locator('input[placeholder="••••••••"]').first()).toBeVisible({ timeout: 8000 });

    const inputs = page.locator('input[type="password"]');
    await inputs.nth(0).fill('demo123');
    await inputs.nth(1).fill('newpass123');
    await inputs.nth(2).fill('newpass123');
    await page.click('button:has-text("Update password")');

    await expect(page.locator('text=Saved.')).toBeVisible({ timeout: 8000 });

    // Restore original password
    await inputs.nth(0).fill('newpass123');
    await inputs.nth(1).fill('demo123');
    await inputs.nth(2).fill('demo123');
    await page.click('button:has-text("Update password")');
    await expect(page.locator('text=Saved.')).toBeVisible({ timeout: 5000 });
  });

  // SETT-05 · Cambio password — mismatch [P1]
  test('SETT-05: password change mismatch shows error', async ({ page }) => {
    await loginAs(page, 'marco@acme.com');
    await page.goto('/#/settings');
    await page.click('button:has-text("Password")');

    await expect(page.locator('input[type="password"]').first()).toBeVisible({ timeout: 8000 });

    const inputs = page.locator('input[type="password"]');
    await inputs.nth(0).fill('demo123');
    await inputs.nth(1).fill('newpass123');
    await inputs.nth(2).fill('different456');
    await page.click('button:has-text("Update password")');

    await expect(page.locator("text=don't match")).toBeVisible({ timeout: 5000 });
    // Saved. should NOT appear
    await expect(page.locator('text=Saved.')).not.toBeVisible();
  });

  // SETT-06 · Cambio password — troppo corta [P2]
  test('SETT-06: password too short shows error', async ({ page }) => {
    await loginAs(page, 'marco@acme.com');
    await page.goto('/#/settings');
    await page.click('button:has-text("Password")');

    await expect(page.locator('input[type="password"]').first()).toBeVisible({ timeout: 8000 });

    const inputs = page.locator('input[type="password"]');
    await inputs.nth(0).fill('demo123');
    await inputs.nth(1).fill('abc');
    await inputs.nth(2).fill('abc');
    await page.click('button:has-text("Update password")');

    await expect(page.locator('text=/at least 6/i').first()).toBeVisible({ timeout: 5000 });
  });

  // SETT-07 · Cambio password — password attuale errata [P1]
  test('SETT-07: wrong current password shows error', async ({ page }) => {
    await loginAs(page, 'marco@acme.com');
    await page.goto('/#/settings');
    await page.click('button:has-text("Password")');

    await expect(page.locator('input[type="password"]').first()).toBeVisible({ timeout: 8000 });

    const inputs = page.locator('input[type="password"]');
    await inputs.nth(0).fill('wrongpassword');
    await inputs.nth(1).fill('newpass123');
    await inputs.nth(2).fill('newpass123');
    await page.click('button:has-text("Update password")');

    await expect(page.locator('text=/incorrect|wrong/i')).toBeVisible({ timeout: 8000 });
  });

  // SETT-08 · Projects — crea progetto [P1]
  test('SETT-08: create a new project', async ({ page }) => {
    await loginAs(page, 'marco@acme.com');
    await page.goto('/#/settings');
    await page.click('button:has-text("Projects")');

    await expect(page.locator('button:has-text("New project")')).toBeVisible({ timeout: 8000 });
    await page.click('button:has-text("New project")');

    // Fill form
    await page.fill('input[placeholder="e.g. Web App"]', 'E2E Test Project');
    await page.fill('input[placeholder="Optional description"]', 'Created by E2E test');
    await page.click('button.btn.primary:has-text("Save")');

    // Project appears in list
    await expect(page.locator('text=E2E Test Project').first()).toBeVisible({ timeout: 8000 });

    // Verify POST /api/projects was called
    const token = await page.evaluate(() => localStorage.getItem('th_token'));
    const list = await page.request.get(`${BASE}/api/projects`, {
      headers: { Authorization: `Bearer ${token}` },
    });
    const projects = await list.json();
    expect(projects.some((p: any) => p.name === 'E2E Test Project')).toBe(true);

    // Cleanup: delete via API
    const proj = projects.find((p: any) => p.name === 'E2E Test Project');
    if (proj) {
      await page.request.delete(`${BASE}/api/projects/${proj.id}`, {
        headers: { Authorization: `Bearer ${token}` },
      });
    }
  });

  // SETT-09 · Projects — validazione nome vuoto [P2]
  test('SETT-09: project name required validation', async ({ page }) => {
    await loginAs(page, 'marco@acme.com');
    await page.goto('/#/settings');
    await page.click('button:has-text("Projects")');

    await page.click('button:has-text("New project")');
    // Leave name empty
    await page.click('button.btn.primary:has-text("Save")');

    await expect(page.locator('text=Name is required')).toBeVisible({ timeout: 5000 });
  });

  // SETT-10 · Categories — crea categoria con colore [P1]
  test('SETT-10: create a new category with color', async ({ page }) => {
    await loginAs(page, 'marco@acme.com');
    await page.goto('/#/settings');
    await page.click('button:has-text("Categories")');

    await expect(page.locator('button:has-text("New category")')).toBeVisible({ timeout: 8000 });
    await page.click('button:has-text("New category")');

    await page.fill('input[placeholder="e.g. Smoke, Regression"]', 'E2E Smoke');

    // Select a color (click the second color circle)
    const colorButtons = page.locator('button[style*="border-radius: 50%"]');
    await colorButtons.nth(1).click();

    await page.click('button.btn.primary:has-text("Save")');

    await expect(page.locator('text=E2E Smoke')).toBeVisible({ timeout: 8000 });

    // Cleanup
    const token = await page.evaluate(() => localStorage.getItem('th_token'));
    const list = await page.request.get(`${BASE}/api/categories`, {
      headers: { Authorization: `Bearer ${token}` },
    });
    const cats = await list.json();
    const cat = cats.find((c: any) => c.name === 'E2E Smoke');
    if (cat) {
      await page.request.delete(`${BASE}/api/categories/${cat.id}`, {
        headers: { Authorization: `Bearer ${token}` },
      });
    }
  });

  // SETT-11 · Categories — validazione nome vuoto [P2]
  test('SETT-11: category name required validation', async ({ page }) => {
    await loginAs(page, 'marco@acme.com');
    await page.goto('/#/settings');
    await page.click('button:has-text("Categories")');

    await page.click('button:has-text("New category")');
    await page.click('button.btn.primary:has-text("Save")');

    await expect(page.locator('text=Name is required')).toBeVisible({ timeout: 5000 });
  });

  // SETT-12 · Folders — crea root folder [P1]
  test('SETT-12: create a root folder', async ({ page }) => {
    await loginAs(page, 'marco@acme.com');
    await page.goto('/#/settings');
    await page.click('button:has-text("Folders")');

    await expect(page.locator('button:has-text("New root folder")')).toBeVisible({ timeout: 8000 });
    await page.click('button:has-text("New root folder")');

    await page.fill('input[placeholder="Folder name"]', 'E2E Root Folder');
    await page.click('button.btn.primary:has-text("Save")');

    await expect(page.locator('text=E2E Root Folder')).toBeVisible({ timeout: 8000 });

    // Cleanup via API
    const token = await page.evaluate(() => localStorage.getItem('th_token'));
    const list = await page.request.get(`${BASE}/api/folders`, {
      headers: { Authorization: `Bearer ${token}` },
    });
    const folders = await list.json();
    const folder = folders.find((f: any) => f.name === 'E2E Root Folder');
    if (folder) {
      await page.request.delete(`${BASE}/api/folders/${folder.id}`, {
        headers: { Authorization: `Bearer ${token}` },
      });
    }
  });

  // SETT-13 · Folders — validazione nome vuoto [P2]
  test('SETT-13: folder name required validation', async ({ page }) => {
    await loginAs(page, 'marco@acme.com');
    await page.goto('/#/settings');
    await page.click('button:has-text("Folders")');

    await page.click('button:has-text("New root folder")');
    // Leave name empty, press Save
    await page.click('button.btn.primary:has-text("Save")');

    await expect(page.locator('text=Name is required')).toBeVisible({ timeout: 5000 });
  });

  // SETT-14 · Settings — navigation via sidebar link [P2]
  test('SETT-14: settings accessible via sidebar navigation', async ({ page }) => {
    await loginAs(page, 'marco@acme.com');
    // Find Settings link in sidebar
    await page.click('text=Settings');
    await page.waitForURL('**/#/settings', { timeout: 8000 });
    await expect(page.locator('text=Profile').first()).toBeVisible({ timeout: 5000 });
  });

});
