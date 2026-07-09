import { test, expect } from '@playwright/test';

// Pure-assertion e2e demo (no app/browser needed) so the pipeline is fast and
// deterministic. One test fails on purpose → the playwright job goes red while
// the pytest job stays green.
//
// The [TC-GL-…] tokens in the titles are the correlation ids: they match the
// `id:` of the YAML schede under tests/. When the pipeline result is imported,
// ThoroTest links each case to its scheda (no duplicate) and updates the
// scheda's status to the real run result — so status lives here, not in the
// hand-written YAML.
test.describe('checkout', () => {
  test('login with valid credentials [TC-GL-100]', async () => {
    expect(200).toBe(200);
  });

  test('guest checkout succeeds', async () => {
    expect(200).toBe(200);
  });

  test('promo code applies discount [TC-GL-101]', async () => {
    const total = 100 * (1 - 0.1);
    expect(total).toBeCloseTo(90);
  });

  test('apple pay sheet opens on Safari iOS', async () => {
    // Intentional failure — demonstrates a red e2e result flowing into ThoroTest.
    const sheet = 'closed';
    expect(sheet).toBe('opened');
  });
});
