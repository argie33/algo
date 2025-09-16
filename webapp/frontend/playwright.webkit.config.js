import { defineConfig, devices } from '@playwright/test';

/**
 * WebKit-specific Playwright Configuration
 * Test with WebKit browser engine (Safari)
 */
export default defineConfig({
  testDir: './src/tests/e2e',
  fullyParallel: false,
  forbidOnly: !!process.env.CI,
  retries: 0,
  workers: 1,
  
  reporter: [
    ['line'],
    ['html', { outputFolder: 'playwright-report-webkit' }],
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
      name: 'webkit-test',
      use: { 
        ...devices['Desktop Safari'],
        launchOptions: {
          headless: true,
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
});