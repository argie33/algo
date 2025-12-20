import { defineConfig, devices } from '@playwright/test';

/**
 * Firefox-specific Playwright Configuration
 * Test with Firefox browser engine
 */
export default defineConfig({
  testDir: './src/tests/e2e',
  fullyParallel: false,
  forbidOnly: !!process.env.CI,
  retries: 0,
  workers: 1,
  
  reporter: [
    ['line'],
    ['html', { outputFolder: 'playwright-report-firefox' }],
  ],
  
  timeout: 30000,
  expect: {
    timeout: 10000,
  },
  
  use: {
    baseURL: 'http://localhost:5001',
    trace: 'on',
    screenshot: 'on',
    video: 'on',
    actionTimeout: 15000,
    navigationTimeout: 30000,
  },

  projects: [
    {
      name: 'firefox-test',
      use: { 
        ...devices['Desktop Firefox'],
        launchOptions: {
          args: [
            '--no-sandbox',
            '--disable-dev-shm-usage',
          ],
          headless: true,
        }
      },
      testMatch: /simple-demo\.spec\.js/,
    }
  ],

  // Start dev server
  webServer: {
    command: 'npm run dev',
    url: 'http://localhost:5001',
    reuseExistingServer: !process.env.CI,
    timeout: 120000,
  },
});