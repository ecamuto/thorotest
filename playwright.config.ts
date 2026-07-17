import { defineConfig, devices } from '@playwright/test';

export default defineConfig({
  testDir: './e2e',
  fullyParallel: false,
  forbidOnly: !!process.env.CI,
  retries: process.env.CI ? 1 : 0,
  workers: 2,
  reporter: [['list'], ['html', { outputFolder: 'playwright-report', open: 'never' }]],
  use: {
    baseURL: 'http://localhost:8000',
    headless: true,
    trace: 'on-first-retry',
    screenshot: 'only-on-failure',
    video: 'off',
  },
  projects: [
    {
      name: 'chromium',
      use: { ...devices['Desktop Chrome'] },
    },
  ],
  // Isolated backend for e2e: a dedicated SQLite DB (reset + demo-seeded on each
  // launch) and login rate-limiting disabled so the suite's intentional bad-login
  // and high-volume login tests don't self-throttle. reuseExistingServer lets a
  // manually-started `make dev` be reused locally; CI always boots a clean one.
  webServer: {
    command:
      'npm run build && ' +
      'rm -f e2e.db e2e.db-shm e2e.db-wal && ' +
      'venv/bin/python -m backend.seed && ' +
      'venv/bin/uvicorn backend.main:app --port 8000',
    url: 'http://localhost:8000',
    reuseExistingServer: !process.env.CI,
    timeout: 60_000,
    env: {
      DATABASE_URL: 'sqlite:///./e2e.db',
      LOGIN_RATELIMIT_DISABLED: '1',
      // e2e webhook tests point at a local target; allow private hosts for the
      // SSRF guard in this environment only (never in production).
      WEBHOOK_ALLOW_PRIVATE_HOSTS: '1',
      PYTHONUNBUFFERED: '1',
    },
  },
});
