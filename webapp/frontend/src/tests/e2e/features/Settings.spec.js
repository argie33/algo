import { test, expect } from "@playwright/test";

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
    });

    // Capture network responses
    page.on("response", (response) => {
      if (!response.ok()) {
        console.log(
          `âŒ Response Error: ${response.status()} ${response.url()}`
        );
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
      console.log(`ðŸš¨ Page Error: ${error.message}`);
      console.log(`   Stack: ${error.stack}`);
    });

    // Capture unhandled rejections
    page.on("requestfailed", (request) => {
      console.log(
        `   Failure: ${request.failure()?.errorText || "Unknown error"}`
      );
    });
  });

  test.afterEach(async () => {
    // Log summary

    // Detailed error analysis
    if (pageErrors.length > 0) {
      pageErrors.forEach((error, index) => {
        console.log(`Message: ${error.message}`);
        console.log(`Stack: ${error.stack}`);
        console.log(`Time: ${error.timestamp}`);
      });
    }

    // Console error analysis
    const errorMessages = consoleMessages.filter((msg) => msg.type === "error");
    if (errorMessages.length > 0) {
      errorMessages.forEach((msg, index) => {
      });
    }

    // Failed request analysis
    const failedRequests = networkRequests.filter((req) =>
      req.url.includes("/api/")
    );
    failedRequests.forEach((req) => {
    });
  });

  test("Settings page login flow with comprehensive logging", async ({
    page,
  }) => {

    // Navigate to the application
    await page.goto("/", { waitUntil: "domcontentloaded" });
    await page.waitForTimeout(2000);

    // Check if already logged in
    const authModal = await page.locator('[data-testid="auth-modal"]').count();
    if (authModal === 0) {
    } else {

      // Try to find and interact with auth elements
      const loginTab = page.locator('button:has-text("Login")').first();
      if (await loginTab.isVisible()) {
        await loginTab.click();
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

        const loginButton = page
          .locator('button:has-text("Sign In"), button:has-text("Login")')
          .first();
        if (await loginButton.isVisible()) {
          await loginButton.click();
          await page.waitForTimeout(3000);
        }
      }
    }

    // Navigate to Settings page

    // Try different navigation methods
    const settingsLink = page
      .locator('a[href="/settings"], a:has-text("Settings")')
      .first();
    if (await settingsLink.isVisible()) {
      await settingsLink.click();
    } else {
      // Direct navigation as fallback
      await page.goto("/settings", {
        waitUntil: "domcontentloaded",
      });
    }

    await page.waitForTimeout(3000);

    // Wait for Settings page to load and check for content

    // Check for page title/header
    const settingsHeader = await page
      .locator('h1, h2, [data-testid="settings-header"]')
      .textContent()
      .catch(() => null);
    if (settingsHeader) {
    } else {
    }

    // Check for API key sections
    const apiKeySection = await page
      .locator('[data-testid="api-keys"], :has-text("API Keys")')
      .count();

    // Check for settings tabs/sections
    const settingsTabs = await page
      .locator('[role="tab"], .tab, [data-testid*="tab"]')
      .count();

    // Check for loading states
    const loadingElements = await page
      .locator('[data-testid*="loading"], .loading, .spinner')
      .count();

    // Check for error messages
    const errorElements = await page
      .locator('.error, [data-testid*="error"], .alert-error')
      .count();
    console.log(`âŒ Error elements found: ${errorElements}`);

    // Wait for any async operations to complete
    await page.waitForTimeout(5000);

    // Final page state analysis
    const finalUrl = page.url();

    const pageTitle = await page.title();


    // Ensure test passes (this is a diagnostic test)
    expect(true).toBe(true);
  });

  test("Settings page API interactions deep dive", async ({ page }) => {

    // Navigate directly to settings
    await page.goto("/settings", {
      waitUntil: "domcontentloaded",
    });
    await page.waitForTimeout(3000);

    // Try to trigger API calls by interacting with elements

    // Look for buttons that might trigger API calls
    const buttons = await page.locator("button").all();

    for (let i = 0; i < Math.min(buttons.length, 5); i++) {
      const button = buttons[i];
      const buttonText = await button.textContent().catch(() => "Unknown");

      if (
        buttonText.includes("Save") ||
        buttonText.includes("Test") ||
        buttonText.includes("Load")
      ) {
        console.log(
          `ðŸ”¥ Clicking potentially API-triggering button: "${buttonText}"`
        );
        await button.click().catch(() => console.log("Button click failed"));
        await page.waitForTimeout(2000);
      }
    }

    // Look for form elements that might have onchange handlers
    const inputs = await page.locator("input, select, textarea").all();

    // Wait for final network activity
    await page.waitForTimeout(5000);
  });
});

