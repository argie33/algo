import { defineConfig, devices } from '@playwright/test';

// MANUAL TESTING ONLY - NOT FOR CI/CD
export default defineConfig({
  testDir: './src/tests/e2e',
  fullyParallel: false,
  forbidOnly: false, // Allow .only() for manual testing
  retries: 1,
  workers: 1, // Single worker for local testing
  reporter: [
    ['list'],
    ['html', { outputFolder: 'playwright-report' }]
  ],
  timeout: 120000,
  
  use: {
    baseURL: 'http://localhost:3001', // Manual testing assumes dev server running
    trace: 'retain-on-failure',
    screenshot: 'only-on-failure',
    video: 'retain-on-failure',
    viewport: { width: 1280, height: 720 },
    actionTimeout: 15000,
    navigationTimeout: 30000,
  },

  projects: [
    {
      name: 'chromium',
      use: { 
        ...devices['Desktop Chrome'],
        launchOptions: {
          args: [
            '--no-sandbox',
            '--disable-setuid-sandbox', 
            '--disable-dev-shm-usage',
            '--disable-web-security'
          ]
        }
      },
    },
  ],

  // NO web server - manual testing requires dev server to be running
  webServer: undefined,
});
