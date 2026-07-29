import { test, expect } from '@playwright/test';
import { loginAs } from '../fixtures/auth';

/**
 * Suite 20 — Keyboard and assistive-technology access.
 *
 * The UI renders most controls as styled <div>s and hand-rolled overlays. That
 * is fine for a mouse and invisible to everything else: before this suite
 * existed, dialogs had no role, never moved focus, could not be dismissed with
 * Escape, and let Tab walk into the page behind them.
 *
 * These are regression tests for behaviour that is easy to lose in a refactor —
 * nothing here is visible in a screenshot.
 */

const BACKDROP = 'div[aria-hidden="true"][style*="z-index: 99"]';

const countBackdrops = (page) =>
  page.evaluate((sel) => document.querySelectorAll(sel).length, BACKDROP);

const focusIsInsideDialog = (page) =>
  page.evaluate(() => {
    const d = document.querySelector('[role="dialog"]');
    return !!(d && d.contains(document.activeElement));
  });

test.describe('Suite 20 — Accessibility', () => {

  test.beforeEach(async ({ page }) => {
    await loginAs(page, 'marco@acme.com');
    await page.goto('/#/library');
    // Wait for the view to actually be interactive rather than a fixed sleep:
    // under parallel workers the server is slower and a sleep races the load.
    await expect(page.locator('button:has-text("New test")').first()).toBeVisible({ timeout: 15000 });
    await expect(page.locator('.tree-row').first()).toBeVisible({ timeout: 15000 });
  });

  /** Open the New-test dialog and wait until its contents have settled. */
  async function openNewTestDialog(page) {
    await page.locator('button:has-text("New test")').first().click();
    const dialog = page.locator('[role="dialog"]').first();
    await expect(dialog).toBeVisible({ timeout: 10000 });
    // The form loads custom-field definitions asynchronously; tabbing while
    // that resolves changes the focusable set mid-traversal.
    await page.waitForLoadState('networkidle');
    return dialog;
  }

  // A11Y-01 · Dialog semantics
  test('A11Y-01: modal exposes dialog role, aria-modal and a label', async ({ page }) => {
    const dialog = await openNewTestDialog(page);
    await expect(dialog).toHaveAttribute('aria-modal', 'true');
    await expect(dialog).toHaveAttribute('aria-labelledby', 'new-test-title');
  });

  // A11Y-02 · Focus enters the dialog, and returns to the trigger afterwards
  test('A11Y-02: modal moves focus in on open and restores it on close', async ({ page }) => {
    await openNewTestDialog(page);
    await expect.poll(() => focusIsInsideDialog(page), { timeout: 5000 }).toBe(true);

    await page.keyboard.press('Escape');
    await expect(page.locator('[role="dialog"]')).toHaveCount(0);

    // Focus must land back on the control that opened the dialog, or keyboard
    // position is lost and the user restarts from the top of the page.
    const backOnTrigger = await page.evaluate(() =>
      (document.activeElement?.textContent || '').includes('New test'));
    expect(backOnTrigger).toBe(true);
  });

  // A11Y-03 · Tab must not escape an open dialog
  test('A11Y-03: Tab is trapped inside the modal', async ({ page }) => {
    await openNewTestDialog(page);
    await expect.poll(() => focusIsInsideDialog(page), { timeout: 5000 }).toBe(true);

    for (let i = 0; i < 25; i++) {
      await page.keyboard.press('Tab');
      expect(await focusIsInsideDialog(page)).toBe(true);
    }
  });

  // A11Y-04 · Escape closes the dialog
  test('A11Y-04: Escape closes the modal', async ({ page }) => {
    await openNewTestDialog(page);
    await page.keyboard.press('Escape');
    await expect(page.locator('[role="dialog"]')).toHaveCount(0);
  });

  // A11Y-05 · A drag that starts inside the dialog must not dismiss it
  test('A11Y-05: text selection dragged onto the backdrop does not close the modal', async ({ page }) => {
    const dialog = await openNewTestDialog(page);

    const box = await dialog.boundingBox();
    await page.mouse.move(box!.x + 40, box!.y + 40);
    await page.mouse.down();
    await page.mouse.move(box!.x - 220, box!.y + 40);   // release over the backdrop
    await page.mouse.up();
    await expect(dialog).toBeVisible();

    // A genuine backdrop click still closes it.
    await page.mouse.click(box!.x - 220, box!.y + 40);
    await expect(page.locator('[role="dialog"]')).toHaveCount(0);
  });

  // A11Y-06 · Dropdowns are keyboard-dismissable
  test('A11Y-06: Escape closes a filter dropdown', async ({ page }) => {
    const chip = page.locator('.chip[role="button"]').first();
    await chip.click();
    expect(await countBackdrops(page)).toBe(1);

    await page.keyboard.press('Escape');
    expect(await countBackdrops(page)).toBe(0);
  });

  // A11Y-07 · The click-catching backdrop must stay out of the tab order
  test('A11Y-07: dropdown backdrop is aria-hidden and not focusable', async ({ page }) => {
    await page.locator('.chip[role="button"]').first().click();
    const info = await page.evaluate((sel) => {
      const d = document.querySelector(sel);
      return d ? { tabIndex: (d as HTMLElement).tabIndex, hasRole: d.hasAttribute('role') } : null;
    }, BACKDROP);
    expect(info).not.toBeNull();
    expect(info!.tabIndex).toBeLessThan(0);
    expect(info!.hasRole).toBe(false);
  });

  // A11Y-08 · Interactive rows and chips are reachable and operable
  test('A11Y-08: chips and tree rows expose button semantics', async ({ page }) => {
    const chip = page.locator('.chip[role="button"]').first();
    await expect(chip).toHaveAttribute('role', 'button');
    expect(await chip.evaluate((el: HTMLElement) => el.tabIndex)).toBe(0);

    const row = page.locator('.tree-row[role="button"]').first();
    await expect(row).toHaveAttribute('role', 'button');
    expect(await row.evaluate((el: HTMLElement) => el.tabIndex)).toBe(0);

    // Enter must activate it, the same as a click.
    await row.focus();
    await page.keyboard.press('Enter');
    await expect(page.locator('.tree-row.active')).toHaveCount(1, { timeout: 5000 });
  });

  // A11Y-09 · Skip link is the first stop and reaches the main landmark
  test('A11Y-09: skip link is the first tab stop and targets main content', async ({ page }) => {
    await page.goto('/#/overview');
    await expect(page.locator('main#main-content')).toBeVisible({ timeout: 10000 });
    await page.keyboard.press('Tab');

    const skip = await page.evaluate(() => {
      const el = document.activeElement as HTMLElement;
      return el ? { cls: el.className, href: el.getAttribute('href') } : null;
    });
    expect(skip?.cls).toContain('skip-link');
    expect(skip?.href).toBe('#main-content');
    await expect(page.locator('main#main-content')).toHaveCount(1);
  });
});
