import { defineConfig, devices } from '@playwright/test';

/**
 * Demo Playwright Configuration
 * Simplified config to show browser launch without global setup
 */
export default defineConfig({
  testDir: './src/tests/e2e',
  fullyParallel: false,
  forbidOnly: !!process.env.CI,
  retries: 0,
  workers: 1,
  
  reporter: [
    ['line'],
    ['html', { outputFolder: 'playwright-report-demo' }],
  ],
  
  timeout: 30000,
  expect: {
    timeout: 10000,
  },
  
  use: {
    baseURL: 'http://localhost:3001',
    trace: 'on',
    screenshot: 'on',
    video: 'on',
    actionTimeout: 15000,
    navigationTimeout: 30000,
  },

  projects: [
    {
      name: 'demo-chrome',
      use: { 
        ...devices['Desktop Chrome'],
        launchOptions: {
          args: [
            '--no-sandbox',
            '--disable-setuid-sandbox',
            '--disable-dev-shm-usage',
            '--disable-gpu',
            '--no-first-run',
            '--no-zygote',
            '--single-process',
          ],
          // Try headed mode to see browser window
          headless: false,
        }
      },
      testMatch: /simple-demo\.spec\.js/,
    }
  ],

  // Start dev server
  webServer: {
    command: 'npm run dev',
    url: 'http://localhost:3001',
    reuseExistingServer: !process.env.CI,
    timeout: 120000,
  },

  // Skip global setup to avoid dependency issues
});