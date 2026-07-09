import { test, expect } from '@playwright/test';

// Pure-assertion e2e demo (no app/browser needed) so the pipeline is fast and
// deterministic. One test fails on purpose → the playwright job goes red while
// the pytest job stays green.
test.describe('checkout', () => {
  test('guest checkout succeeds', async () => {
    expect(200).toBe(200);
  });

  test('promo code applies discount', async () => {
    const total = 100 * (1 - 0.1);
    expect(total).toBeCloseTo(90);
  });

  test('apple pay sheet opens on Safari iOS', async () => {
    // Intentional failure — demonstrates a red e2e result flowing into ThoroTest.
    const sheet = 'closed';
    expect(sheet).toBe('opened');
  });
});
