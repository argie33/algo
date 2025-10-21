import { test, expect } from "@playwright/test";

test.describe("Stock Explorer Page E2E Tests", () => {
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

  test("should load Stock Explorer page without errors", async ({ page }) => {
    // Monitor console errors
    const consoleErrors = [];
    page.on("console", (msg) => {
      if (msg.type() === "error") {
        consoleErrors.push(msg.text());
      }
    });

    console.log("🧪 Testing Stock Explorer at /stocks...");

    // Navigate to Stock Explorer page
    try {
      await page.goto("/stocks", {
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
        `📊 Stock Explorer: ${consoleErrors.length} total errors, ${muiTabsErrors.length} MUI Tabs errors`
      );

      if (muiTabsErrors.length > 0) {
        console.log("❌ MUI Tabs errors on Stock Explorer:");
        muiTabsErrors.forEach((error) => console.log(`   - ${error}`));
      }

      // Should not have MUI Tabs errors on Stock Explorer page
      expect(
        muiTabsErrors.length,
        "Stock Explorer should not have MUI Tabs errors"
      ).toBe(0);

      // Verify page loaded successfully
      const body = page.locator("#root");
      await expect(body).toBeVisible();

      // Check for stock explorer content
      const hasStockExplorerContent = await page.locator("#root *").count();
      expect(hasStockExplorerContent).toBeGreaterThan(0);

    } catch (error) {
      console.log("⚠️ Stock Explorer failed to load:", error.message);
      await page.screenshot({ path: 'debug-stock-explorer.png' });
      throw error;
    }
  });

  test("should display stock explorer elements", async ({ page }) => {
    await page.goto("/stocks", {
      waitUntil: "domcontentloaded",
      timeout: 15000,
    });
    await page.waitForTimeout(2000);

    // Look for common stock explorer elements
    const stockExplorerSelectors = [
      '[data-testid*="stock"]',
      '[class*="stock"]',
      '[class*="explorer"]',
      '[class*="search"]',
      'input[type="text"]', // Search inputs
      'table', // Stock list table
      '.MuiCard-root', // Card components
    ];

    let hasStockExplorerElements = false;
    for (const selector of stockExplorerSelectors) {
      const elements = page.locator(selector);
      const count = await elements.count();
      if (count > 0) {
        hasStockExplorerElements = true;
        break;
      }
    }

    // Page should have some stock explorer UI elements
    expect(hasStockExplorerElements).toBe(true);
  });
});