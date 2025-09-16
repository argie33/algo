import { defineConfig, devices } from '@playwright/test';

/**
 * Infrastructure Testing Configuration
 * Minimal config to test Playwright setup without full browser launch
 */
export default defineConfig({
  testDir: './src/tests/e2e',
  fullyParallel: false,
  forbidOnly: !!process.env.CI,
  retries: 0,
  workers: 1,
  
  reporter: [
    ['line'],
    ['html', { outputFolder: 'playwright-report-infra' }],
  ],
  
  timeout: 15000,
  expect: {
    timeout: 5000,
  },
  
  use: {
    baseURL: 'http://localhost:3001',
    trace: 'retain-on-failure',
    screenshot: 'only-on-failure',
    actionTimeout: 10000,
    navigationTimeout: 15000,
  },

  projects: [
    {
      name: 'infrastructure',
      use: { 
        ...devices['Desktop Chrome'],
        launchOptions: {
          args: ['--no-sandbox', '--disable-setuid-sandbox'],
          headless: true,
        }
      },
      testMatch: /infrastructure-test\.spec\.js/,
    }
  ],

  // Start dev server
  webServer: {
    command: 'npm run dev',
    url: 'http://localhost:3001',
    reuseExistingServer: !process.env.CI,
    timeout: 60000,
  },
});