import { defineConfig, devices } from '@playwright/test';

/**
 * Simplified Playwright Configuration for CI/Production Testing
 * Focuses on Chrome with fallback strategies
 */
export default defineConfig({
  testDir: './src/tests/e2e',
  fullyParallel: false, // Disable parallel for stability
  forbidOnly: !!process.env.CI,
  retries: process.env.CI ? 3 : 2,
  workers: 1, // Single worker for stability

  reporter: [
    ['html', { outputFolder: 'playwright-report' }],
    ['list'],
  ],

  timeout: 60000, // Reduced timeout
  expect: {
    timeout: 30000,
  },

  use: {
    baseURL: 'http://localhost:5173',
    trace: 'on-first-retry',
    screenshot: 'only-on-failure',
    video: 'retain-on-failure',
    actionTimeout: 15000,
    navigationTimeout: 30000,
  },

  projects: [
    // Primary Chrome testing only
    {
      name: 'chrome',
      use: {
        ...devices['Desktop Chrome'],
        viewport: { width: 1920, height: 1080 },
        launchOptions: {
          args: [
            '--no-sandbox',
            '--disable-setuid-sandbox',
            '--disable-dev-shm-usage',
            '--disable-web-security',
            '--disable-features=VizDisplayCompositor',
            '--headless=new',
            '--disable-gpu',
            '--disable-extensions',
            '--no-first-run',
            '--disable-default-apps'
          ]
        }
      },
    },

    // Mobile Chrome - Essential responsive testing
    {
      name: 'mobile-chrome',
      use: {
        ...devices['Pixel 5'],
        launchOptions: {
          args: [
            '--no-sandbox',
            '--disable-setuid-sandbox',
            '--disable-dev-shm-usage',
            '--headless=new',
            '--disable-gpu'
          ]
        }
      },
    },

    // Firefox with enhanced configuration
    {
      name: 'firefox',
      use: {
        ...devices['Desktop Firefox'],
        viewport: { width: 1920, height: 1080 },
        launchOptions: {
          firefoxUserPrefs: {
            'media.navigator.streams.fake': true,
            'media.navigator.permission.disabled': true,
          }
        }
      },
    },
  ],

  // Start dev server for testing
  webServer: {
    command: 'npm run dev',
    url: 'http://localhost:5173',
    reuseExistingServer: !process.env.CI,
    timeout: 60000,
    stdout: 'pipe',
    stderr: 'pipe',
  },
});