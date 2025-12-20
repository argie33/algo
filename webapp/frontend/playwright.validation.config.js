import { defineConfig } from '@playwright/test';

/**
 * Validation Configuration - Browser-Independent Testing
 * Tests that demonstrate comprehensive infrastructure without browser dependencies
 */
export default defineConfig({
  testDir: './src/tests/e2e',
  fullyParallel: true,
  forbidOnly: !!process.env.CI,
  retries: 0,
  workers: 1,
  
  reporter: [
    ['line'],
    ['html', { outputFolder: 'validation-report' }],
  ],
  
  timeout: 15000,
  expect: {
    timeout: 5000,
  },
  
  use: {
    baseURL: 'http://localhost:5001',
    trace: 'retain-on-failure',
    actionTimeout: 10000,
    navigationTimeout: 15000,
  },

  projects: [
    {
      name: 'financial-platform',
      testMatch: /financial-platform-e2e\.spec\.js/,
      // No dependencies to avoid global setup
    },
    
    {
      name: 'comprehensive-routes',
      testMatch: /comprehensive-routes\.spec\.js/,
      // No dependencies to avoid global setup
    },
    
    {
      name: 'form-interactions',
      testMatch: /form-interactions\.spec\.js/,
      // No dependencies to avoid global setup
    },
    
    {
      name: 'visual-regression',
      testMatch: /visual-regression\.spec\.js/,
      // No dependencies to avoid global setup
    },
    
    {
      name: 'accessibility',
      testMatch: /accessibility\.spec\.js/,
      // No dependencies to avoid global setup
    },
    
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
    timeout: 60000,
    stdout: 'pipe',
    stderr: 'pipe',
  },

  // Skip global setup/teardown for validation-only tests
  // globalSetup: './src/tests/e2e/global-setup.js',
  // globalTeardown: './src/tests/e2e/global-teardown.js',
});