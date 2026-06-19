import { test, expect } from '@playwright/test';
import { loginAs } from '../fixtures/auth';

const BASE = 'http://localhost:8000';

test.describe('Suite P10 — Auth Header Fix', () => {

  // P10-01: POST /api/tests from Library NewTestModal (INT-01, site 5)
  test('P10-01: Create test via NewTestModal returns 201', async ({ page }) => {
    await loginAs(page, 'marco@acme.com');
    const token = await page.evaluate(() => localStorage.getItem('th_token'));

    await page.goto('/#/library');
    // Wait for library to fully load
    await page.waitForSelector('.toolbar', { timeout: 10000 });

    const uniqueId = `TC-P10-01-${Date.now()}`;

    // Set up response interception before triggering the action
    const [response] = await Promise.all([
      page.waitForResponse(
        resp => resp.url().includes('/api/tests') && resp.request().method() === 'POST' && !resp.url().includes('/bulk'),
        { timeout: 15000 }
      ),
      (async () => {
        // Click "New test" button in toolbar
        await page.click('button.btn.accent.sm:has-text("New test")');
        // Wait for modal to appear
        await page.waitForSelector('h2:has-text("New test case")', { timeout: 5000 });
        // Fill ID field
        await page.fill('input[placeholder="TC-2400"]', uniqueId);
        // Fill Title field
        await page.fill('input[placeholder="Describe what this test verifies"]', 'P10 create regression test');
        // Click Create test button
        await page.click('button.btn.accent:has-text("Create test")');
      })(),
    ]);

    expect(response.status()).toBe(201);
  });

  // P10-02: DELETE /api/tests/{id} from Library confirmDelete (INT-01, site 1)
  test('P10-02: Delete test from Library confirmDelete returns 204 or 200', async ({ page }) => {
    await loginAs(page, 'marco@acme.com');
    const token = await page.evaluate(() => localStorage.getItem('th_token'));

    // Create a test to delete via API
    const uniqueId = `TC-P10-02-${Date.now()}`;
    const createRes = await page.request.post(`${BASE}/api/tests`, {
      data: { id: uniqueId, title: 'P10 delete from library test', status: 'pending', type: 'manual' },
      headers: { Authorization: `Bearer ${token}`, 'Content-Type': 'application/json' },
    });
    expect(createRes.status()).toBe(201);

    // Navigate to Library
    await page.goto('/#/library');
    await page.waitForSelector('.toolbar', { timeout: 10000 });
    // Wait for test list to load
    await page.waitForTimeout(1500);

    // Search for the specific test to find it reliably
    await page.fill('input[placeholder="Search tests…"]', uniqueId);
    await page.waitForTimeout(600);

    // Click the delete icon button on the test row
    const [response] = await Promise.all([
      page.waitForResponse(
        resp => resp.url().includes(`/api/tests/${uniqueId}`) && resp.request().method() === 'DELETE',
        { timeout: 15000 }
      ),
      (async () => {
        // Find and click the delete icon for our test row
        await page.click(`tr:has-text("${uniqueId}") button[title="Delete test"]`);
        // Confirm deletion in the dialog
        await page.waitForSelector('text=will be permanently deleted', { timeout: 5000 });
        await page.click('button:has-text("Delete"):not(.btn.ghost)');
      })(),
    ]);

    expect([200, 204]).toContain(response.status());
  });

  // P10-03: POST /api/tests/bulk delete via Library (INT-01, sites 2-4)
  test('P10-03: Bulk delete via Library returns 200', async ({ page }) => {
    await loginAs(page, 'marco@acme.com');
    const token = await page.evaluate(() => localStorage.getItem('th_token'));

    // Create 2 tests to bulk delete via API
    const ts = Date.now();
    const id1 = `TC-P10-03A-${ts}`;
    const id2 = `TC-P10-03B-${ts}`;

    for (const [id, title] of [[id1, 'P10 bulk test A'], [id2, 'P10 bulk test B']]) {
      const res = await page.request.post(`${BASE}/api/tests`, {
        data: { id, title, status: 'pending', type: 'manual' },
        headers: { Authorization: `Bearer ${token}`, 'Content-Type': 'application/json' },
      });
      expect(res.status()).toBe(201);
    }

    // Navigate to Library and search for first test to isolate test data
    await page.goto('/#/library');
    await page.waitForSelector('.toolbar', { timeout: 10000 });
    await page.waitForTimeout(1500);

    // Search for the first test ID prefix to find both tests
    await page.fill('input[placeholder="Search tests…"]', `TC-P10-03`);
    await page.waitForTimeout(600);

    // Select both checkboxes
    const rows = page.locator('tbody tr');
    const count = await rows.count();
    // Select all matching rows via checkboxes
    for (let i = 0; i < count; i++) {
      const row = rows.nth(i);
      const rowText = await row.textContent();
      if (rowText && (rowText.includes(id1) || rowText.includes(id2))) {
        await row.locator('input[type="checkbox"]').click();
      }
    }

    // Trigger bulk delete and intercept the /api/tests/bulk POST request
    const [response] = await Promise.all([
      page.waitForResponse(
        resp => resp.url().includes('/api/tests/bulk') && resp.request().method() === 'POST',
        { timeout: 15000 }
      ),
      (async () => {
        // Click the "Delete" button in the bulk actions toolbar (red text)
        await page.click('.btn.sm:has-text("Delete"):not(.btn.ghost)');
        // Confirm in the dialog
        await page.waitForSelector('text=will be permanently deleted', { timeout: 5000 });
        await page.click('button:has-text("Delete"):not(.btn.ghost):not(.btn.sm)');
      })(),
    ]);

    expect(response.status()).toBe(200);
  });

  // P10-04: PATCH /api/tests/{id} title save from TestDetail (INT-02, site 1)
  test('P10-04: Title save PATCH from TestDetail returns 200', async ({ page }) => {
    await loginAs(page, 'marco@acme.com');
    const token = await page.evaluate(() => localStorage.getItem('th_token'));

    // Create a test to edit via API
    const uniqueId = `TC-P10-04-${Date.now()}`;
    const createRes = await page.request.post(`${BASE}/api/tests`, {
      data: { id: uniqueId, title: 'P10 title save original', status: 'pending', type: 'manual' },
      headers: { Authorization: `Bearer ${token}`, 'Content-Type': 'application/json' },
    });
    expect(createRes.status()).toBe(201);
    const created = await createRes.json();

    // Navigate to TestDetail for the created test
    await page.goto(`/#/tests/${created.id}`);
    // Wait for test detail to load — title h1 should appear
    await page.waitForSelector('h1', { timeout: 10000 });
    await page.waitForTimeout(1000);

    // Click on the h1 title to enter edit mode (cursor: text)
    await page.click('h1[title="Click to edit title"]');
    // Wait for a "Save" button to appear — indicates edit mode is active
    const saveBtn = page.locator('button:has-text("Save")').first();
    await saveBtn.waitFor({ timeout: 5000 });

    // Select all text in the focused input and type new title
    await page.keyboard.press('Control+a');
    await page.keyboard.type('P10 title save updated');

    // Intercept the PATCH response while triggering save
    const [response] = await Promise.all([
      page.waitForResponse(
        resp => resp.url().includes(`/api/tests/${created.id}`) && resp.request().method() === 'PATCH',
        { timeout: 15000 }
      ),
      saveBtn.click(),
    ]);

    expect(response.status()).toBe(200);
  });

  // P10-05: DELETE /api/tests/{id} from TestDetail handleDelete (INT-02, site 2)
  test('P10-05: Delete from TestDetail returns 204 or 200', async ({ page }) => {
    await loginAs(page, 'marco@acme.com');
    const token = await page.evaluate(() => localStorage.getItem('th_token'));

    // Create a test to delete via API
    const uniqueId = `TC-P10-05-${Date.now()}`;
    const createRes = await page.request.post(`${BASE}/api/tests`, {
      data: { id: uniqueId, title: 'P10 delete from detail test', status: 'pending', type: 'manual' },
      headers: { Authorization: `Bearer ${token}`, 'Content-Type': 'application/json' },
    });
    expect(createRes.status()).toBe(201);
    const created = await createRes.json();

    // Navigate to TestDetail for the created test
    await page.goto(`/#/tests/${created.id}`);
    // Wait for test detail header to load
    await page.waitForSelector('h1', { timeout: 10000 });
    await page.waitForTimeout(1000);

    // Set up response interception BEFORE any clicks to avoid race with navigation
    const responsePromise = page.waitForResponse(
      resp => resp.url().includes(`/api/tests/${created.id}`) && resp.request().method() === 'DELETE',
      { timeout: 15000 }
    );

    // Click the Delete button in the header
    await page.click('button:has-text("Delete")');
    // Wait for confirmation dialog to appear
    await page.waitForSelector(`text=Delete ${created.id}?`, { timeout: 5000 });
    // Click the red Delete confirmation button (last "Delete" button on page — in the dialog)
    await page.locator('button:has-text("Delete")').last().click();

    // Await the response (registered before all clicks)
    const response = await responsePromise;

    expect([200, 204]).toContain(response.status());
  });

});
