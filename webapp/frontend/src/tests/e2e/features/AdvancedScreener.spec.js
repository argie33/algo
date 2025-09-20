import { test, expect } from "@playwright/test";

test.describe("Advanced Screener Page E2E Tests", () => {
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

  test("should load Advanced Screener page without errors", async ({ page }) => {
    // Monitor console errors
    const consoleErrors = [];
    page.on("console", (msg) => {
      if (msg.type() === "error") {
        consoleErrors.push(msg.text());
      }
    });

    console.log("🧪 Testing Advanced Screener at /screener-advanced...");

    // Navigate to Advanced Screener page
    try {
      await page.goto("/screener-advanced", {
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
        `📊 Advanced Screener: ${consoleErrors.length} total errors, ${muiTabsErrors.length} MUI Tabs errors`
      );

      if (muiTabsErrors.length > 0) {
        console.log("❌ MUI Tabs errors on Advanced Screener:");
        muiTabsErrors.forEach((error) => console.log(`   - ${error}`));
      }

      // Should not have MUI Tabs errors on Advanced Screener page
      expect(
        muiTabsErrors.length,
        "Advanced Screener should not have MUI Tabs errors"
      ).toBe(0);

      // Verify page loaded successfully
      const body = page.locator("body");
      await expect(body).toBeVisible();

      // Check for screener content
      const hasScreenerContent = await page.locator("body *").count();
      expect(hasScreenerContent).toBeGreaterThan(0);

    } catch (error) {
      console.log("⚠️ Advanced Screener failed to load:", error.message);
      await page.screenshot({ path: 'debug-advanced-screener.png' });
      throw error;
    }
  });

  test("should display advanced screener elements", async ({ page }) => {
    await page.goto("/screener-advanced", {
      waitUntil: "domcontentloaded",
      timeout: 15000,
    });
    await page.waitForSelector("#root", { timeout: 10000 });
    await page.waitForTimeout(2000);

    // Look for common advanced screener elements
    const screenerSelectors = [
      '[data-testid*="screener"]',
      '[class*="screener"]',
      '[class*="filter"]',
      '[class*="search"]',
      'input[type="text"]', // Search inputs
      'select', // Filter dropdowns
      'table', // Results table
      '.MuiCard-root', // Card components
    ];

    let hasScreenerElements = false;
    for (const selector of screenerSelectors) {
      const elements = page.locator(selector);
      const count = await elements.count();
      if (count > 0) {
        hasScreenerElements = true;
        break;
      }
    }

    // Page should have some advanced screener UI elements
    expect(hasScreenerElements).toBe(true);
  });
});