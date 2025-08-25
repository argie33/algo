import { defineConfig, devices } from '@playwright/test';

/**
 * Playwright Visual Regression Testing Configuration
 * 
 * Optimized configuration for visual testing with multiple browsers,
 * viewports, and screenshot comparison settings.
 */

export default defineConfig({
  testDir: './webapp/frontend/src/tests/visual',
  
  // Run tests in files with visual regression patterns
  testMatch: '**/*visual*.test.js',
  
  // Timeout for individual tests (visual tests need more time)
  timeout: 60000,
  
  // Retry failed tests (visual tests can be flaky)
  retries: process.env.CI ? 2 : 1,
  
  // Parallel execution
  workers: process.env.CI ? 2 : 4,
  
  // Reporter configuration
  reporter: [
    ['html', { outputFolder: 'test-results/visual-report' }],
    ['junit', { outputFile: 'test-results/visual-results.xml' }],
    ['line']
  ],
  
  // Global test settings
  use: {
    // Base URL for testing
    baseURL: process.env.VITE_APP_URL || 'http://localhost:3000',
    
    // Screenshot settings
    screenshot: 'only-on-failure',
    video: 'retain-on-failure',
    trace: 'retain-on-failure',
    
    // Visual comparison settings
    expect: {
      // Threshold for screenshot comparison (0.2 = 20% difference allowed)
      threshold: 0.2,
      
      // Animation handling
      toHaveScreenshot: {
        animations: 'disabled',
        caret: 'hide'
      }
    }
  },

  // Visual regression specific project configurations
  projects: [
    // Desktop browsers
    {
      name: 'desktop-chromium',
      use: {
        ...devices['Desktop Chrome'],
        viewport: { width: 1920, height: 1080 }
      }
    },
    {
      name: 'desktop-firefox',
      use: {
        ...devices['Desktop Firefox'],
        viewport: { width: 1920, height: 1080 }
      }
    },
    {
      name: 'desktop-webkit',
      use: {
        ...devices['Desktop Safari'],
        viewport: { width: 1920, height: 1080 }
      }
    },
    
    // Tablet devices
    {
      name: 'tablet-chromium',
      use: {
        ...devices['iPad Pro'],
        viewport: { width: 1024, height: 768 }
      }
    },
    {
      name: 'tablet-firefox',
      use: {
        ...devices['iPad Pro'],
        channel: 'firefox',
        viewport: { width: 1024, height: 768 }
      }
    },
    
    // Mobile devices
    {
      name: 'mobile-chromium',
      use: {
        ...devices['iPhone 13'],
        viewport: { width: 375, height: 667 }
      }
    },
    {
      name: 'mobile-safari',
      use: {
        ...devices['iPhone 13'],
        viewport: { width: 375, height: 667 }
      }
    },
    
    // High DPI testing
    {
      name: 'desktop-high-dpi',
      use: {
        ...devices['Desktop Chrome HiDPI'],
        viewport: { width: 1920, height: 1080 },
        deviceScaleFactor: 2
      }
    }
  ],

  // Development server setup for testing
  webServer: process.env.CI ? undefined : {
    command: 'npm run dev',
    port: 3000,
    cwd: './webapp/frontend',
    reuseExistingServer: !process.env.CI,
    timeout: 120000
  },

  // Output directories
  outputDir: 'test-results/visual-artifacts',
  
  // Screenshot storage
  expect: {
    toHaveScreenshot: {
      // Threshold for image comparison
      threshold: 0.2,
      
      // Max allowed pixel difference
      maxDiffPixels: 1000,
      
      // Animation handling
      animations: 'disabled',
      
      // Font rendering consistency
      fontFamily: 'Arial, sans-serif',
      
      // Screenshot modes
      mode: 'default', // 'default' | 'ci' | 'local'
      
      // Update snapshots
      updateSnapshots: process.env.UPDATE_SNAPSHOTS === 'true' ? 'all' : 'missing'
    }
  },
  
  // Global setup and teardown
  globalSetup: './webapp/frontend/src/tests/visual/global-visual-setup.js',
  globalTeardown: './webapp/frontend/src/tests/visual/global-visual-teardown.js'
});