import { defineConfig } from '@playwright/test';

// Emit a JUnit report so the GitLab pipeline's test_report (and ThoroTest's
// import) picks up the e2e results alongside the pytest ones.
export default defineConfig({
  testDir: './e2e',
  reporter: [
    ['list'],
    ['junit', { outputFile: 'e2e-report.xml' }],
  ],
});
