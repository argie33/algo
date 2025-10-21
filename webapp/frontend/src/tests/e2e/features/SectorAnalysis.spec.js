import { test, expect } from "@playwright/test";

test.describe("Sector Analysis Page E2E Tests", () => {
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

  test("should load Sector Analysis page without errors", async ({ page }) => {
    // Monitor console errors
    const consoleErrors = [];
    page.on("console", (msg) => {
      if (msg.type() === "error") {
        consoleErrors.push(msg.text());
      }
    });

    console.log("🧪 Testing Sector Analysis at /sectors...");

    // Navigate to Sector Analysis page
    try {
      await page.goto("/sectors", {
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
        `📊 Sector Analysis: ${consoleErrors.length} total errors, ${muiTabsErrors.length} MUI Tabs errors`
      );

      if (muiTabsErrors.length > 0) {
        console.log("❌ MUI Tabs errors on Sector Analysis:");
        muiTabsErrors.forEach((error) => console.log(`   - ${error}`));
      }

      // Should not have MUI Tabs errors on Sector Analysis page
      expect(
        muiTabsErrors.length,
        "Sector Analysis should not have MUI Tabs errors"
      ).toBe(0);

      // Verify page loaded successfully
      const body = page.locator("#root");
      await expect(body).toBeVisible();

      // Check for sector analysis content
      const hasSectorContent = await page.locator("#root *").count();
      expect(hasSectorContent).toBeGreaterThan(0);

    } catch (error) {
      console.log("⚠️ Sector Analysis failed to load:", error.message);
      await page.screenshot({ path: 'debug-sector-analysis.png' });
      throw error;
    }
  });

  test("should display sector analysis elements", async ({ page }) => {
    await page.goto("/sectors", {
      waitUntil: "domcontentloaded",
      timeout: 15000,
    });
    await page.waitForTimeout(2000);

    // Look for common sector analysis elements
    const sectorSelectors = [
      '[data-testid*="sector"]',
      '[class*="sector"]',
      '[class*="analysis"]',
      'table', // Sector data table
      'canvas', // Charts
      'svg', // SVG charts
      '.MuiCard-root', // Card components
    ];

    let hasSectorElements = false;
    for (const selector of sectorSelectors) {
      const elements = page.locator(selector);
      const count = await elements.count();
      if (count > 0) {
        hasSectorElements = true;
        break;
      }
    }

    // Page should have some sector analysis UI elements
    expect(hasSectorElements).toBe(true);
  });
});