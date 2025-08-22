/**
 * Playwright Configuration for E2E Testing
 * Financial Application - Production Ready Testing
 */

import { defineConfig, devices } from "@playwright/test";

export default defineConfig({
  // Test directory
  testDir: "./src/tests/e2e",

  // Run tests in files in parallel
  fullyParallel: true,

  // Fail the build on CI if you accidentally left test.only in the source code
  forbidOnly: !!process.env.CI,

  // Retry on CI only
  retries: process.env.CI ? 2 : 0,

  // Opt out of parallel tests on CI
  workers: process.env.CI ? 1 : undefined,

  // Reporter to use
  reporter: [
    ["html"],
    ["junit", { outputFile: "test-results/e2e-results.xml" }],
    ["json", { outputFile: "test-results/e2e-results.json" }],
  ],

  // Shared settings for all the projects below
  use: {
    // Base URL to use in actions like `await page.goto('/')`
    baseURL:
      process.env.PLAYWRIGHT_BASE_URL ||
      "https://d1copuy2oqlazx.cloudfront.net",

    // Collect trace when retrying the failed test
    trace: "on-first-retry",

    // Record video on failure
    video: "retain-on-failure",

    // Take screenshot on failure
    screenshot: "only-on-failure",

    // Global timeout for each test
    actionTimeout: 10000,
    navigationTimeout: 30000,
  },

  // Configure projects for major browsers
  projects: [
    {
      name: "chromium",
      use: { ...devices["Desktop Chrome"] },
    },

    {
      name: "firefox",
      use: { ...devices["Desktop Firefox"] },
    },

    {
      name: "webkit",
      use: { ...devices["Desktop Safari"] },
    },

    // Test against mobile viewports
    {
      name: "Mobile Chrome",
      use: { ...devices["Pixel 5"] },
    },
    {
      name: "Mobile Safari",
      use: { ...devices["iPhone 12"] },
    },

    // Test against branded browsers
    {
      name: "Microsoft Edge",
      use: { ...devices["Desktop Edge"], channel: "msedge" },
    },
    {
      name: "Google Chrome",
      use: { ...devices["Desktop Chrome"], channel: "chrome" },
    },
  ],

  // Run your local dev server before starting the tests
  webServer: process.env.CI
    ? undefined
    : {
        command: "npm run dev",
        url: "http://localhost:5173",
        reuseExistingServer: !process.env.CI,
        timeout: 120000,
      },

  // Global setup and teardown
  globalSetup: "./src/tests/e2e/global-setup.js",
  globalTeardown: "./src/tests/e2e/global-teardown.js",

  // Test timeout
  timeout: 60000,

  // Expect timeout
  expect: {
    timeout: 10000,
  },

  // Output directory for test artifacts
  outputDir: "test-results/e2e-artifacts",
});
