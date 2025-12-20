import { defineConfig } from '@playwright/test';

/**
 * CI-compatible Playwright Configuration
 * For environments without browser dependencies installed
 */
export default defineConfig({
  testDir: './src/tests/e2e',
  fullyParallel: true,
  forbidOnly: !!process.env.CI,
  retries: process.env.CI ? 2 : 0,
  workers: 1,
  
  reporter: [
    ['html', { outputFolder: 'playwright-report' }],
    ['json', { outputFile: 'test-results/results.json' }],
    ['line'],
  ],
  
  timeout: 30000,
  expect: {
    timeout: 10000,
  },
  
  use: {
    baseURL: 'http://localhost:5001',
    trace: 'on-first-retry',
    screenshot: 'only-on-failure',
    video: 'retain-on-failure',
    actionTimeout: 15000,
    navigationTimeout: 30000,
  },

  projects: [
    // Basic validation tests that don't require browser launch
    {
      name: 'validation',
      testMatch: /.*validation\.test\.js/,
      // No dependencies to avoid global setup
    },
    
    // API validation tests
    {
      name: 'api-validation',
      testMatch: /api-validation\.test\.js/,
      // No dependencies to avoid global setup
    }
  ],

  // Start dev server for testing
  webServer: {
    command: 'npm run dev',
    url: 'http://localhost:5001',
    reuseExistingServer: !process.env.CI,
    timeout: 120000,
    stdout: 'pipe',
    stderr: 'pipe',
  },

  // Skip global setup/teardown for basic validation
  // globalSetup: './src/tests/e2e/global-setup.js',
  // globalTeardown: './src/tests/e2e/global-teardown.js',
});