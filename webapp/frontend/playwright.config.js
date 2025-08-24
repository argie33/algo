import { defineConfig, devices } from '@playwright/test';

/**
 * Comprehensive Playwright Configuration for Financial Dashboard
 * Covers: E2E, Visual Regression, Accessibility, Performance, Cross-browser
 */
export default defineConfig({
  testDir: './src/tests/e2e',
  fullyParallel: true,
  forbidOnly: !!process.env.CI,
  retries: process.env.CI ? 2 : 1,
  workers: process.env.CI ? 1 : undefined,
  
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
    baseURL: 'http://localhost:3000',
    trace: 'on-first-retry',
    screenshot: 'only-on-failure',
    video: 'retain-on-failure',
    actionTimeout: 30000, // Reduced from 120000
    navigationTimeout: 60000, // Reduced from 300000
  },

  projects: [
    // Setup project for authentication and database seeding
    {
      name: 'setup',
      testMatch: /.*\.setup\.js/,
    },

    // Desktop Chrome - Primary testing
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
            '--disable-features=VizDisplayCompositor'
          ]
        }
      },
      // dependencies: ['setup'], // Temporarily remove setup dependency
    },

    // Desktop Firefox - Cross-browser coverage
    {
      name: 'desktop-firefox',
      use: { 
        ...devices['Desktop Firefox'],
        viewport: { width: 1920, height: 1080 },
      },
      dependencies: ['setup'],
    },

    // Desktop Safari - WebKit engine
    {
      name: 'desktop-safari',
      use: { 
        ...devices['Desktop Safari'],
        viewport: { width: 1920, height: 1080 },
      },
      dependencies: ['setup'],
    },

    // Tablet testing
    {
      name: 'tablet-chrome',
      use: { 
        ...devices['iPad Pro'],
      },
      dependencies: ['setup'],
    },

    // Mobile Chrome - Responsive testing
    {
      name: 'mobile-chrome',
      use: { 
        ...devices['Pixel 5'],
      },
      dependencies: ['setup'],
    },

    // Mobile Safari - iOS testing
    {
      name: 'mobile-safari',
      use: { 
        ...devices['iPhone 12'],
      },
      dependencies: ['setup'],
    },

    // Visual regression testing
    {
      name: 'visual-desktop',
      use: {
        ...devices['Desktop Chrome'],
        viewport: { width: 1920, height: 1080 },
      },
      testMatch: /.*\.visual\.spec\.js/,
      dependencies: ['setup'],
    },

    // Performance testing
    {
      name: 'performance',
      use: {
        ...devices['Desktop Chrome'],
        viewport: { width: 1920, height: 1080 },
      },
      testMatch: /.*\.perf\.spec\.js/,
      dependencies: ['setup'],
    },

    // Accessibility testing
    {
      name: 'accessibility',
      use: {
        ...devices['Desktop Chrome'],
        viewport: { width: 1920, height: 1080 },
      },
      testMatch: /.*\.accessibility\.spec\.js/,
      dependencies: ['setup'],
    },
  ],

  // Start dev server for testing
  webServer: {
    command: 'npm run dev',
    url: 'http://localhost:3000',
    reuseExistingServer: !process.env.CI,
    timeout: 60000, // Reduced timeout
    stdout: 'pipe',
    stderr: 'pipe',
  },

  // Global test configuration
  globalSetup: './src/tests/e2e/global-setup.js',
  globalTeardown: './src/tests/e2e/global-teardown.js',
});
