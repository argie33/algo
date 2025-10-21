import { test, expect } from "@playwright/test";

test.describe("Trading Signals Page E2E Tests", () => {
  test.setTimeout(30000);

  test.beforeEach(async ({ page }) => {
    // Set up auth like in the main tests
    await page.addInitScript(() => {
      localStorage.setItem("financial_auth_token", "e2e-test-token");
      localStorage.setItem(
        "api_keys_status",
        JSON.stringify({
          alpaca: { configured: true, valid: true },
          polygon: { configured: true, valid: true },
          finnhub: { configured: true, valid: true },
        })
      );
    });
  });

  test("should load Trading Signals page without errors", async ({ page }) => {
    // Monitor console errors
    const consoleErrors = [];
    page.on("console", (msg) => {
      if (msg.type() === "error") {
        consoleErrors.push(msg.text());
      }
    });

    console.log("🧪 Testing Trading Signals at /trading...");

    // Navigate to Trading Signals page
    try {
      await page.goto("/trading", {
        waitUntil: "domcontentloaded",
        timeout: 15000,
      });
      await page.waitForSelector("#root", {
        state: "attached",
        timeout: 10000,
      });
      await page.waitForTimeout(3000);

      // Check for MUI Tabs errors specifically
      const muiTabsErrors = consoleErrors.filter(
        (error) =>
          error.includes("MUI:") &&
          error.includes("Tabs") &&
          error.includes("value")
      );

      console.log(
        `📊 Trading Signals: ${consoleErrors.length} total errors, ${muiTabsErrors.length} MUI Tabs errors`
      );

      if (muiTabsErrors.length > 0) {
        console.log("❌ MUI Tabs errors on Trading Signals:");
        muiTabsErrors.forEach((error) => console.log(`   - ${error}`));
      }

      // Should not have MUI Tabs errors on Trading Signals page
      expect(
        muiTabsErrors.length,
        "Trading Signals should not have MUI Tabs errors"
      ).toBe(0);

      // Verify page loaded successfully
      const body = page.locator("#root");
      await expect(body).toBeVisible();

      // Check for trading signals content
      const hasTradingContent = await page.locator("#root *").count();
      expect(hasTradingContent).toBeGreaterThan(0);

    } catch (error) {
      console.log("⚠️ Trading Signals failed to load:", error.message);
      await page.screenshot({ path: 'debug-trading-signals.png' });
      throw error;
    }
  });

  test("should display trading signals elements", async ({ page }) => {
    await page.goto("/trading", {
      waitUntil: "domcontentloaded",
      timeout: 15000,
    });
    await page.waitForTimeout(2000);

    // Look for common trading signals elements
    const tradingSelectors = [
      '[data-testid*="trading"]',
      '[data-testid*="signal"]',
      '[class*="trading"]',
      '[class*="signal"]',
      '[class*="buy"]',
      '[class*="sell"]',
      'table', // Signals table
      'button', // Action buttons
      '.MuiCard-root', // Card components
    ];

    let hasTradingElements = false;
    for (const selector of tradingSelectors) {
      const elements = page.locator(selector);
      const count = await elements.count();
      if (count > 0) {
        hasTradingElements = true;
        break;
      }
    }

    // Page should have some trading signals UI elements
    expect(hasTradingElements).toBe(true);
  });
});