import { defineConfig, devices } from '@playwright/test';

export default defineConfig({
  testDir: './src/tests/e2e',
  fullyParallel: true,
  forbidOnly: !!process.env.CI,
  retries: process.env.CI ? 2 : 0,
  workers: process.env.CI ? 1 : undefined,
  reporter: [
    ['html', { outputFolder: 'playwright-report' }],
    ['json', { outputFile: 'test-results/playwright-results.json' }],
    ['junit', { outputFile: 'test-results/playwright-junit.xml' }],
    ['github']
  ],
  use: {
    baseURL: 'http://localhost:4173',
    trace: 'on-first-retry',
    screenshot: 'only-on-failure',
    video: 'retain-on-failure',
    actionTimeout: 30000,
    navigationTimeout: 60000,
    headless: true
  },
  projects: [
    {
      name: 'chromium',
      use: { ...devices['Desktop Chrome'] },
    },
    {
      name: 'firefox',
      use: { ...devices['Desktop Firefox'] },
    },
    {
      name: 'webkit',
      use: { ...devices['Desktop Safari'] },
    },
    // Mobile testing
    {
      name: 'Mobile Chrome',
      use: { ...devices['Pixel 5'] },
    },
    {
      name: 'Mobile Safari',
      use: { ...devices['iPhone 12'] },
    },
  ],
  // Run local dev server before starting tests
  webServer: {
    command: 'npm run preview',
    port: 4173,
    reuseExistingServer: !process.env.CI,
    timeout: 120000
  },
  // Global test setup
  globalSetup: './src/tests/global-setup.js',
  // Test timeout
  timeout: 60000,
  // Expect timeout
  expect: {
    timeout: 10000
  },
  // Output directory
  outputDir: 'test-results/',
  // Maximum failures
  maxFailures: process.env.CI ? 10 : undefined,
});