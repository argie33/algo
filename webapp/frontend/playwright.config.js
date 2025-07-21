import { defineConfig, devices } from '@playwright/test';
import { fileURLToPath } from 'url';
import { dirname } from 'path';

const __filename = fileURLToPath(import.meta.url);
// eslint-disable-next-line no-unused-vars
const __dirname = dirname(__filename);

export default defineConfig({
  testDir: './src/tests',
  
  // Global test configuration for comprehensive integration testing
  timeout: 90000, // Extended timeout for complex integration tests
  expect: {
    timeout: 15000
  },
  
  // Fail on the first test failure in CI
  fullyParallel: !process.env.CI,
  forbidOnly: !!process.env.CI,
  retries: process.env.CI ? 2 : 1,
  workers: process.env.CI ? 2 : 4,
  
  // Reporter configuration for comprehensive reporting
  reporter: [
    ['html', { outputFolder: 'test-results/html-report' }],
    ['json', { outputFile: 'test-results/test-results.json' }],
    ['junit', { outputFile: 'test-results/junit.xml' }],
    ['list'],
    ['github']
  ],
  
  // Global setup and teardown (temporarily disabled for testing)
  // globalSetup: join(__dirname, 'src/tests/setup/global-setup.js'),
  // globalTeardown: join(__dirname, 'src/tests/setup/global-teardown.js'),
  
  use: {
    // Base URL for all tests - use actual deployment URL
    baseURL: process.env.E2E_BASE_URL || 'https://d1zb7knau41vl9.cloudfront.net',
    
    // Browser context options
    ignoreHTTPSErrors: true, // Important for SSL testing
    viewport: { width: 1280, height: 720 },
    
    // Trace collection for debugging
    trace: 'retain-on-failure',
    video: 'retain-on-failure',
    screenshot: 'only-on-failure',
    
    // Network options for real integration testing
    extraHTTPHeaders: {
      'Accept': 'application/json',
      'User-Agent': 'Playwright/Integration-Tests'
    },
    
    // Extended timeouts for complex operations
    actionTimeout: 30000,
    navigationTimeout: 45000,
    headless: true
  },
  // Test projects configuration for comprehensive integration testing
  projects: [
    // Setup project to run before all tests
    {
      name: 'setup',
      testMatch: /.*\.setup\.js/,
      use: {
        ...devices['Desktop Chrome']
      }
    },
    
    // Comprehensive Integration Tests
    {
      name: 'integration-comprehensive',
      testMatch: /integration\/.*comprehensive.*\.test\.js/,
      dependencies: ['setup'],
      use: {
        ...devices['Desktop Chrome'],
        trace: 'on',
        video: 'on'
      }
    },
    
    // Trading Workflow Tests
    {
      name: 'trading-integration',
      testMatch: /integration\/trading\/.*\.test\.js/,
      dependencies: ['setup'],
      use: {
        ...devices['Desktop Chrome'],
        trace: 'on'
      }
    },
    
    // Portfolio Management Tests
    {
      name: 'portfolio-integration',
      testMatch: /integration\/portfolio\/.*\.test\.js/,
      dependencies: ['setup'],
      use: {
        ...devices['Desktop Chrome'],
        trace: 'on'
      }
    },
    
    // Security and Authentication Tests
    {
      name: 'security-integration',
      testMatch: /integration\/security\/.*\.test\.js/,
      dependencies: ['setup'],
      use: {
        ...devices['Desktop Chrome'],
        trace: 'on',
        video: 'on' // Important for security test evidence
      }
    },
    
    // Database and Data Loading Tests
    {
      name: 'database-integration',
      testMatch: /integration\/data-loading\/.*\.test\.js/,
      dependencies: ['setup'],
      use: {
        ...devices['Desktop Chrome'],
        trace: 'on',
        timeout: 120000 // Extended timeout for database operations
      }
    },
    
    // External API Services Tests
    {
      name: 'api-services-integration',
      testMatch: /integration\/api-services\/.*\.test\.js/,
      dependencies: ['setup'],
      use: {
        ...devices['Desktop Chrome'],
        trace: 'on'
      }
    },
    
    // Error Handling and Recovery Tests
    {
      name: 'error-handling-integration',
      testMatch: /integration\/error-handling\/.*\.test\.js/,
      dependencies: ['setup'],
      use: {
        ...devices['Desktop Chrome'],
        trace: 'on',
        video: 'on'
      }
    },
    
    // Real-time Data Tests
    {
      name: 'realtime-integration',
      testMatch: /integration\/realtime\/.*\.test\.js/,
      dependencies: ['setup'],
      use: {
        ...devices['Desktop Chrome'],
        trace: 'on',
        timeout: 120000 // Extended timeout for real-time operations
      }
    },
    
    // Component Integration Tests
    {
      name: 'component-integration',
      testMatch: /integration\/component-integration\.test\.js/,
      dependencies: ['setup'],
      use: {
        ...devices['Desktop Chrome']
      }
    },
    
    // API Integration Tests
    {
      name: 'api-integration',
      testMatch: /integration\/api\/.*\.test\.js/,
      dependencies: ['setup'],
      use: {
        ...devices['Desktop Chrome']
      }
    },
    
    // End-to-End User Journey Tests
    {
      name: 'e2e-journeys',
      testMatch: /e2e\/workflows\/.*\.test\.js/,
      dependencies: ['setup'],
      use: {
        ...devices['Desktop Chrome'],
        trace: 'on',
        video: 'on'
      }
    },
    
    // Cross-browser testing for critical flows (existing projects)
    {
      name: 'firefox-critical',
      testMatch: /integration\/.*comprehensive.*\.test\.js/,
      dependencies: ['setup'],
      use: {
        ...devices['Desktop Firefox'],
        trace: 'retain-on-failure'
      }
    },
    
    {
      name: 'webkit-critical',
      testMatch: /integration\/.*comprehensive.*\.test\.js/,
      dependencies: ['setup'],
      use: {
        ...devices['Desktop Safari'],
        trace: 'retain-on-failure'
      }
    }
  ],
  // Output directories
  outputDir: 'test-results/artifacts',
  
  // Web server configuration for local testing only
  webServer: process.env.CI ? undefined : {
    command: 'npm run dev',
    port: 5173,
    reuseExistingServer: !process.env.CI,
    timeout: 120000
  },
  
  // Maximum failures
  maxFailures: process.env.CI ? 10 : undefined,
});