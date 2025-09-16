import { defineConfig, devices } from '@playwright/test';

/**
 * Cross-Browser Testing Configuration
 * Tests across Chrome, Firefox, and Safari for comprehensive compatibility
 */
export default defineConfig({
  testDir: './src/tests/e2e',
  fullyParallel: true,
  forbidOnly: !!process.env.CI,
  retries: 0,
  workers: 2, // Run 2 browsers in parallel
  
  reporter: [
    ['line'],
    ['html', { outputFolder: 'cross-browser-report' }],
  ],
  
  timeout: 20000,
  expect: {
    timeout: 8000,
  },
  
  use: {
    baseURL: 'http://localhost:3001',
    trace: 'retain-on-failure',
    actionTimeout: 15000,
    navigationTimeout: 20000,
    screenshot: 'only-on-failure',
  },

  projects: [
    {
      name: 'chromium',
      use: { 
        ...devices['Desktop Chrome'],
        viewport: { width: 1280, height: 720 },
      },
      testMatch: /financial-platform-e2e\.spec\.js/,
    },
    
    {
      name: 'firefox',
      use: { 
        ...devices['Desktop Firefox'],
        viewport: { width: 1280, height: 720 },
      },
      testMatch: /financial-platform-e2e\.spec\.js/,
    },

    {
      name: 'webkit',
      use: { 
        ...devices['Desktop Safari'],
        viewport: { width: 1280, height: 720 },
      },
      testMatch: /financial-platform-e2e\.spec\.js/,
    },

    // Mobile testing
    {
      name: 'mobile-chrome',
      use: { 
        ...devices['Pixel 5'],
      },
      testMatch: /financial-platform-e2e\.spec\.js/,
    },

    {
      name: 'mobile-safari',
      use: { 
        ...devices['iPhone 12'],
      },
      testMatch: /financial-platform-e2e\.spec\.js/,
    },
  ],

  // Start dev server for testing
  webServer: {
    command: 'npm run dev',
    url: 'http://localhost:3001',
    reuseExistingServer: !process.env.CI,
    timeout: 60000,
    stdout: 'pipe',
    stderr: 'pipe',
  },
});