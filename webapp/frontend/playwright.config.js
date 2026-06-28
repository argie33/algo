import { defineConfig, devices } from '@playwright/test';

/**
 * Comprehensive Playwright Configuration for Financial Dashboard
 * Covers: E2E, Visual Regression, Accessibility, Performance, Cross-browser
 */
export default defineConfig({
  testDir: './src/tests/e2e',
  fullyParallel: false,
  forbidOnly: !!process.env.CI,
  retries: process.env.CI ? 0 : 0,
  workers: 1,
  
  reporter: [
    ['html', { outputFolder: 'playwright-report' }],
    ['json', { outputFile: 'test-results/results.json' }],
    process.env.CI ? ['github'] : ['list'],
  ],
  
  timeout: 300000,
  expect: {
    timeout: 60000,
  },
  
  use: {
    baseURL: 'http://localhost:5173',
    trace: 'on-first-retry',
    screenshot: 'only-on-failure',
    video: 'retain-on-failure',
    actionTimeout: 30000, // Reduced from 120000
    navigationTimeout: 60000, // Reduced from 300000
  },

  projects: [
    // Desktop Chrome - Primary testing with enhanced stability
    {
      name: 'desktop-chrome',
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
            '--disable-default-apps',
            '--disable-background-timer-throttling',
            '--disable-backgrounding-occluded-windows',
            '--disable-renderer-backgrounding'
          ]
        }
      },
    },

    // Desktop Firefox - Enhanced for better compatibility
    {
      name: 'desktop-firefox',
      use: {
        ...devices['Desktop Firefox'],
        viewport: { width: 1920, height: 1080 },
        launchOptions: {
          firefoxUserPrefs: {
            'media.navigator.streams.fake': true,
            'media.navigator.permission.disabled': true,
            'dom.webnotifications.enabled': false,
            'dom.push.enabled': false
          }
        }
      },
    },

    // Desktop Safari - Skip if system deps missing
    ...(process.env.PLAYWRIGHT_SKIP_VALIDATE_HOST_REQUIREMENTS ? [] : [{
      name: 'desktop-safari',
      use: {
        ...devices['Desktop Safari'],
        viewport: { width: 1920, height: 1080 },
      },
    }]),

    // Tablet testing
    {
      name: 'tablet-chrome',
      use: {
        ...devices['iPad Pro'],
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

    // Mobile Chrome - Responsive testing
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

    // Mobile Safari - Skip if system deps missing
    ...(process.env.PLAYWRIGHT_SKIP_VALIDATE_HOST_REQUIREMENTS ? [] : [{
      name: 'mobile-safari',
      use: {
        ...devices['iPhone 12'],
      },
    }]),

    // Visual regression testing
    {
      name: 'visual-desktop',
      use: {
        ...devices['Desktop Chrome'],
        viewport: { width: 1920, height: 1080 },
      },
      testMatch: /.*\.visual\.spec\.js/,
      // dependencies: ['setup'], // Temporarily disabled
    },

    // Performance testing
    {
      name: 'performance',
      use: {
        ...devices['Desktop Chrome'],
        viewport: { width: 1920, height: 1080 },
      },
      testMatch: /.*\.perf\.spec\.js/,
      // dependencies: ['setup'], // Temporarily disabled
    },

    // Accessibility testing
    {
      name: 'accessibility',
      use: {
        ...devices['Desktop Chrome'],
        viewport: { width: 1920, height: 1080 },
      },
      testMatch: /.*\.accessibility\.spec\.js/,
      // dependencies: ['setup'], // Temporarily disabled
    },
  ],

  // Start dev server for testing
  webServer: {
    command: process.env.CI ? 'npm run dev' : 'npm run dev',
    url: 'http://localhost:5173',
    reuseExistingServer: !process.env.CI,
    timeout: 120000,
    stdout: 'pipe',
    stderr: 'pipe',
  },

  // Global test configuration - temporarily disabled for debugging
  // globalSetup: './src/tests/e2e/global-setup.js',
  // globalTeardown: './src/tests/e2e/global-teardown.js',
});
