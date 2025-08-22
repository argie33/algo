/**
 * Global Setup for E2E Tests
 * Prepares test environment before running Playwright tests
 */

import { chromium } from "@playwright/test";

async function globalSetup() {
  console.log("🚀 Starting E2E test environment setup...");

  // Test environment configuration
  const testConfig = {
    baseURL:
      process.env.PLAYWRIGHT_BASE_URL ||
      "https://d1copuy2oqlazx.cloudfront.net",
    apiURL:
      process.env.VITE_API_URL ||
      "https://jh28jhdp01.execute-api.us-east-1.amazonaws.com/dev",
    timeout: 30000,
  };

  // Launch browser for health checks
  const browser = await chromium.launch();
  const page = await browser.newPage();

  try {
    console.log("🏥 Checking application health...");

    // Check frontend availability
    await page.goto(testConfig.baseURL, { timeout: testConfig.timeout });
    await page.waitForLoadState("networkidle", { timeout: testConfig.timeout });
    console.log("✅ Frontend application is accessible");

    // Check API health endpoint
    const apiHealthResponse = await page.request.get(
      `${testConfig.apiURL}/health`,
      {
        timeout: testConfig.timeout,
      }
    );

    if (apiHealthResponse.ok()) {
      const healthData = await apiHealthResponse.json();
      console.log(
        "✅ API health check passed:",
        healthData.status || "healthy"
      );
    } else {
      console.log("⚠️ API health check failed, but continuing with tests");
    }

    // Verify authentication endpoints
    try {
      const authResponse = await page.request.get(
        `${testConfig.apiURL}/auth/status`
      );
      if (authResponse.ok()) {
        console.log("✅ Authentication service is available");
      }
    } catch (error) {
      console.log("⚠️ Authentication endpoint check skipped");
    }

    // Setup test data if needed
    console.log("📋 Test environment configuration:");
    console.log(`   Frontend: ${testConfig.baseURL}`);
    console.log(`   API: ${testConfig.apiURL}`);
    console.log(`   Environment: ${process.env.NODE_ENV || "test"}`);

    // Create test results directory
    const fs = await import("fs");
    const path = await import("path");

    const resultsDir = path.join(process.cwd(), "test-results");
    if (!fs.existsSync(resultsDir)) {
      fs.mkdirSync(resultsDir, { recursive: true });
      console.log("📁 Created test results directory");
    }

    console.log("🎯 E2E test environment setup completed successfully");
  } catch (error) {
    console.error("❌ Global setup failed:", error.message);

    // Log more details for debugging
    console.log("🔍 Setup failure details:");
    console.log(`   URL: ${testConfig.baseURL}`);
    console.log(`   API: ${testConfig.apiURL}`);
    console.log(`   Error: ${error.stack}`);

    // Don't fail the setup - let individual tests handle failures
    console.log("⚠️ Continuing with tests despite setup issues...");
  }

  await browser.close();
}

export default globalSetup;
