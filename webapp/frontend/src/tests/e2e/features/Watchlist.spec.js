import { test, expect } from "@playwright/test";

test.describe("Watchlist Page E2E Tests", () => {
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

  test("should load Watchlist page without errors", async ({ page }) => {
    // Monitor console errors
    const consoleErrors = [];
    page.on("console", (msg) => {
      if (msg.type() === "error") {
        consoleErrors.push(msg.text());
      }
    });

    console.log("🧪 Testing Watchlist at /watchlist...");

    // Navigate to Watchlist page
    try {
      await page.goto("/watchlist", {
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
        `📊 Watchlist: ${consoleErrors.length} total errors, ${muiTabsErrors.length} MUI Tabs errors`
      );

      if (muiTabsErrors.length > 0) {
        console.log("❌ MUI Tabs errors on Watchlist:");
        muiTabsErrors.forEach((error) => console.log(`   - ${error}`));
      }

      // Should not have MUI Tabs errors on Watchlist page
      expect(
        muiTabsErrors.length,
        "Watchlist should not have MUI Tabs errors"
      ).toBe(0);

      // Verify page loaded successfully
      const body = page.locator("body");
      await expect(body).toBeVisible();

      // Check for watchlist content
      const hasWatchlistContent = await page.locator("body *").count();
      expect(hasWatchlistContent).toBeGreaterThan(0);

    } catch (error) {
      console.log("⚠️ Watchlist failed to load:", error.message);
      await page.screenshot({ path: 'debug-watchlist.png' });
      throw error;
    }
  });

  test("should display watchlist elements", async ({ page }) => {
    await page.goto("/watchlist", {
      waitUntil: "domcontentloaded",
      timeout: 15000,
    });
    await page.waitForSelector("#root", { timeout: 10000 });
    await page.waitForTimeout(2000);

    // Look for common watchlist elements
    const watchlistSelectors = [
      '[data-testid*="watchlist"]',
      '[class*="watchlist"]',
      '[class*="stock"]',
      '[class*="symbol"]',
      'table', // Stock list table
      '.MuiCard-root', // Card components
      'button', // Add/remove buttons
    ];

    let hasWatchlistElements = false;
    for (const selector of watchlistSelectors) {
      const elements = page.locator(selector);
      const count = await elements.count();
      if (count > 0) {
        hasWatchlistElements = true;
        break;
      }
    }

    // Page should have some watchlist UI elements
    expect(hasWatchlistElements).toBe(true);
  });
});