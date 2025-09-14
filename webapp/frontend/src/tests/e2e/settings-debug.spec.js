import { test } from "@playwright/test";

/**
 * Settings Page Debug Test
 * Comprehensive logging of browser console messages, network requests, and errors
 */

test.describe("Settings Page Debug Analysis", () => {
  let consoleMessages = [];
  let networkRequests = [];
  let pageErrors = [];

  test.beforeEach(async ({ page }) => {
    // Clear previous test data
    consoleMessages = [];
    networkRequests = [];
    pageErrors = [];

    // Capture console messages
    page.on("console", (msg) => {
      const messageData = {
        type: msg.type(),
        text: msg.text(),
        location: msg.location(),
        timestamp: new Date().toISOString(),
      };
      consoleMessages.push(messageData);
      console.log(`🔍 Console ${msg.type()}: ${msg.text()}`);
    });

    // Capture network requests
    page.on("request", (request) => {
      const requestData = {
        method: request.method(),
        url: request.url(),
        headers: request.headers(),
        timestamp: new Date().toISOString(),
      };
      networkRequests.push(requestData);
      console.log(`📡 Request: ${request.method()} ${request.url()}`);
    });

    // Capture network responses
    page.on("response", (response) => {
      if (!response.ok()) {
        console.log(
          `❌ Response Error: ${response.status()} ${response.url()}`
        );
        console.log(`   Status Text: ${response.statusText()}`);
      }
    });

    // Capture page errors
    page.on("pageerror", (error) => {
      const errorData = {
        message: error.message,
        stack: error.stack,
        timestamp: new Date().toISOString(),
      };
      pageErrors.push(errorData);
      console.log(`🚨 Page Error: ${error.message}`);
      console.log(`   Stack: ${error.stack}`);
    });

    // Capture unhandled rejections
    page.on("requestfailed", (request) => {
      console.log(`🔥 Request Failed: ${request.url()}`);
      console.log(
        `   Failure: ${request.failure()?.errorText || "Unknown error"}`
      );
    });
  });

  test.afterEach(async () => {
    // Log summary
    console.log("\n📊 TEST SUMMARY:");
    console.log(`   Console Messages: ${consoleMessages.length}`);
    console.log(`   Network Requests: ${networkRequests.length}`);
    console.log(`   Page Errors: ${pageErrors.length}`);

    // Detailed error analysis
    if (pageErrors.length > 0) {
      console.log("\n🚨 PAGE ERRORS DETAILS:");
      pageErrors.forEach((error, index) => {
        console.log(`\nError ${index + 1}:`);
        console.log(`Message: ${error.message}`);
        console.log(`Stack: ${error.stack}`);
        console.log(`Time: ${error.timestamp}`);
      });
    }

    // Console error analysis
    const errorMessages = consoleMessages.filter((msg) => msg.type === "error");
    if (errorMessages.length > 0) {
      console.log("\n❌ CONSOLE ERRORS:");
      errorMessages.forEach((msg, index) => {
        console.log(`\nConsole Error ${index + 1}:`);
        console.log(`Text: ${msg.text}`);
        console.log(`Location: ${JSON.stringify(msg.location)}`);
        console.log(`Time: ${msg.timestamp}`);
      });
    }

    // Failed request analysis
    const failedRequests = networkRequests.filter((req) =>
      req.url.includes("/api/")
    );
    console.log("\n📡 API REQUESTS:");
    failedRequests.forEach((req) => {
      console.log(`${req.method} ${req.url}`);
    });
  });

  test("Settings page login flow with comprehensive logging", async ({
    page,
  }) => {
    console.log("\n🎬 Starting Settings page debug test...");

    // Navigate to the application
    console.log("\n📍 Step 1: Navigate to application");
    await page.goto("http://localhost:3000", { waitUntil: "networkidle" });
    await page.waitForTimeout(2000);

    // Check if already logged in
    const authModal = await page.locator('[data-testid="auth-modal"]').count();
    if (authModal === 0) {
      console.log("✅ Already authenticated or no auth modal found");
    } else {
      console.log("\n🔐 Step 2: Handle authentication");

      // Try to find and interact with auth elements
      const loginTab = page.locator('button:has-text("Login")').first();
      if (await loginTab.isVisible()) {
        await loginTab.click();
        console.log("Clicked Login tab");
      }

      // Fill in test credentials
      const emailInput = page
        .locator(
          'input[type="email"], input[name="email"], input[placeholder*="email"]'
        )
        .first();
      const passwordInput = page
        .locator('input[type="password"], input[name="password"]')
        .first();

      if ((await emailInput.isVisible()) && (await passwordInput.isVisible())) {
        await emailInput.fill("test@example.com");
        await passwordInput.fill("testpassword123");
        console.log("Filled login credentials");

        const loginButton = page
          .locator('button:has-text("Sign In"), button:has-text("Login")')
          .first();
        if (await loginButton.isVisible()) {
          await loginButton.click();
          console.log("Clicked login button");
          await page.waitForTimeout(3000);
        }
      }
    }

    // Navigate to Settings page
    console.log("\n⚙️ Step 3: Navigate to Settings page");

    // Try different navigation methods
    const settingsLink = page
      .locator('a[href="/settings"], a:has-text("Settings")')
      .first();
    if (await settingsLink.isVisible()) {
      await settingsLink.click();
      console.log("Clicked Settings link in navigation");
    } else {
      // Direct navigation as fallback
      await page.goto("http://localhost:3000/settings", {
        waitUntil: "networkidle",
      });
      console.log("Direct navigation to /settings");
    }

    await page.waitForTimeout(3000);

    // Wait for Settings page to load and check for content
    console.log("\n🔍 Step 4: Analyze Settings page content");

    // Check for page title/header
    const settingsHeader = await page
      .locator('h1, h2, [data-testid="settings-header"]')
      .textContent()
      .catch(() => null);
    if (settingsHeader) {
      console.log(`✅ Settings page header found: "${settingsHeader}"`);
    } else {
      console.log("❌ No settings page header found");
    }

    // Check for API key sections
    const apiKeySection = await page
      .locator('[data-testid="api-keys"], :has-text("API Keys")')
      .count();
    console.log(`🔑 API Key sections found: ${apiKeySection}`);

    // Check for settings tabs/sections
    const settingsTabs = await page
      .locator('[role="tab"], .tab, [data-testid*="tab"]')
      .count();
    console.log(`📑 Settings tabs found: ${settingsTabs}`);

    // Check for loading states
    const loadingElements = await page
      .locator('[data-testid*="loading"], .loading, .spinner')
      .count();
    console.log(`⏳ Loading elements found: ${loadingElements}`);

    // Check for error messages
    const errorElements = await page
      .locator('.error, [data-testid*="error"], .alert-error')
      .count();
    console.log(`❌ Error elements found: ${errorElements}`);

    // Wait for any async operations to complete
    await page.waitForTimeout(5000);

    // Final page state analysis
    const finalUrl = page.url();
    console.log(`📍 Final URL: ${finalUrl}`);

    const pageTitle = await page.title();
    console.log(`📄 Page Title: ${pageTitle}`);

    console.log("\n✅ Settings page debug test completed");
  });

  test("Settings page API interactions deep dive", async ({ page }) => {
    console.log("\n🔬 Deep dive API interaction test...");

    // Navigate directly to settings
    await page.goto("http://localhost:3000/settings", {
      waitUntil: "networkidle",
    });
    await page.waitForTimeout(3000);

    // Try to trigger API calls by interacting with elements
    console.log("\n🎯 Triggering API interactions...");

    // Look for buttons that might trigger API calls
    const buttons = await page.locator("button").all();
    console.log(`Found ${buttons.length} buttons on settings page`);

    for (let i = 0; i < Math.min(buttons.length, 5); i++) {
      const button = buttons[i];
      const buttonText = await button.textContent().catch(() => "Unknown");
      console.log(`Button ${i + 1}: "${buttonText}"`);

      if (
        buttonText.includes("Save") ||
        buttonText.includes("Test") ||
        buttonText.includes("Load")
      ) {
        console.log(
          `🔥 Clicking potentially API-triggering button: "${buttonText}"`
        );
        await button.click().catch(() => console.log("Button click failed"));
        await page.waitForTimeout(2000);
      }
    }

    // Look for form elements that might have onchange handlers
    const inputs = await page.locator("input, select, textarea").all();
    console.log(`Found ${inputs.length} form elements`);

    // Wait for final network activity
    await page.waitForTimeout(5000);
  });
});
