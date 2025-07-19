/**
 * Comprehensive E2E Testing Configuration
 * Real environment testing with robust error handling
 * NO MOCKS - Tests real systems with fallback strategies
 */

const { defineConfig, devices } = require('@playwright/test');

module.exports = defineConfig({
  // Test directory structure
  testDir: './tests',
  
  // Run tests in files in parallel
  fullyParallel: false, // Sequential for real system testing
  
  // Fail the build on CI if you accidentally left test.only in the source code
  forbidOnly: !!process.env.CI,
  
  // Retry on CI only
  retries: process.env.CI ? 2 : 1,
  
  // Opt out of parallel tests on CI
  workers: process.env.CI ? 1 : 2,
  
  // Reporter configuration
  reporter: [
    ['html', { outputFolder: 'e2e-reports/html' }],
    ['json', { outputFile: 'e2e-reports/results.json' }],
    ['junit', { outputFile: 'e2e-reports/results.xml' }],
    ['list']
  ],
  
  // Global test configuration
  use: {
    // Base URL for testing
    baseURL: process.env.E2E_BASE_URL || 'https://d1zb7knau41vl9.cloudfront.net',
    
    // API URL for backend testing
    extraHTTPHeaders: {
      'X-Test-Environment': 'e2e-testing'
    },
    
    // Browser settings for comprehensive testing
    trace: 'retain-on-failure',
    screenshot: 'only-on-failure',
    video: 'retain-on-failure',
    
    // Timeout settings for real systems
    actionTimeout: 30000,
    navigationTimeout: 60000,
    
    // Ignore HTTPS errors in test environments
    ignoreHTTPSErrors: true,
    
    // Device settings
    viewport: { width: 1280, height: 720 },
    
    // Test metadata
    testIdAttribute: 'data-testid'
  },

  // Test timeout configuration
  timeout: 120000, // 2 minutes for real system tests
  
  // Global setup and teardown
  globalSetup: require.resolve('./global-setup.js'),
  globalTeardown: require.resolve('./global-teardown.js'),
  
  // Test environments and browsers
  projects: [
    {
      name: 'setup',
      testMatch: /.*\.setup\.js/,
      teardown: 'cleanup'
    },
    {
      name: 'cleanup', 
      testMatch: /.*\.cleanup\.js/
    },
    
    // Desktop browsers
    {
      name: 'chromium-desktop',
      use: { ...devices['Desktop Chrome'] },
      dependencies: ['setup']
    },
    {
      name: 'firefox-desktop',
      use: { ...devices['Desktop Firefox'] },
      dependencies: ['setup']
    },
    {
      name: 'webkit-desktop',
      use: { ...devices['Desktop Safari'] },
      dependencies: ['setup']
    },
    
    // Mobile devices
    {
      name: 'mobile-chrome',
      use: { ...devices['Pixel 5'] },
      dependencies: ['setup']
    },
    {
      name: 'mobile-safari',
      use: { ...devices['iPhone 12'] },
      dependencies: ['setup']
    },
    
    // Error recovery testing
    {
      name: 'error-recovery',
      testMatch: /.*error.*\.spec\.js/,
      use: {
        ...devices['Desktop Chrome'],
        // Aggressive timeout settings for error testing
        actionTimeout: 10000,
        navigationTimeout: 20000
      },
      dependencies: ['setup']
    },
    
    // Performance testing
    {
      name: 'performance',
      testMatch: /.*performance.*\.spec\.js/,
      use: {
        ...devices['Desktop Chrome'],
        // Performance monitoring
        trace: 'on',
        video: 'on'
      },
      dependencies: ['setup']
    },
    
    // Security testing
    {
      name: 'security',
      testMatch: /.*security.*\.spec\.js/,
      use: {
        ...devices['Desktop Chrome'],
        // Security-focused settings
        extraHTTPHeaders: {
          'X-Security-Test': 'enabled',
          'X-Test-Environment': 'security-testing'
        }
      },
      dependencies: ['setup']
    }
  ],

  // Web server for local testing
  webServer: process.env.E2E_START_SERVER ? {
    command: 'npm run dev',
    port: 3000,
    cwd: '../frontend',
    reuseExistingServer: !process.env.CI,
    timeout: 120000
  } : undefined,

  // Test environment variables
  env: {
    // API endpoints
    E2E_API_URL: process.env.E2E_API_URL || 'https://jh28jhdp01.execute-api.us-east-1.amazonaws.com/dev',
    E2E_WEBSOCKET_URL: process.env.E2E_WEBSOCKET_URL || 'wss://jh28jhdp01.execute-api.us-east-1.amazonaws.com/dev',
    
    // Test credentials (non-production)
    E2E_TEST_EMAIL: process.env.E2E_TEST_EMAIL || 'e2e-test@example.com',
    E2E_TEST_PASSWORD: process.env.E2E_TEST_PASSWORD || 'E2ETest123!',
    
    // Test API keys (paper trading only)
    E2E_ALPACA_KEY: process.env.E2E_ALPACA_KEY || 'PKTEST123',
    E2E_ALPACA_SECRET: process.env.E2E_ALPACA_SECRET || 'TEST123',
    E2E_POLYGON_KEY: process.env.E2E_POLYGON_KEY || 'TEST123',
    E2E_FINNHUB_KEY: process.env.E2E_FINNHUB_KEY || 'TEST123',
    
    // Database testing
    E2E_DB_TEST_MODE: 'true',
    
    // Error injection for testing
    E2E_ERROR_INJECTION: process.env.E2E_ERROR_INJECTION || 'false',
    
    // Performance testing
    E2E_LOAD_TEST_USERS: process.env.E2E_LOAD_TEST_USERS || '10',
    E2E_LOAD_TEST_DURATION: process.env.E2E_LOAD_TEST_DURATION || '60',
    
    // Security testing
    E2E_SECURITY_SCAN: process.env.E2E_SECURITY_SCAN || 'false'
  }
});