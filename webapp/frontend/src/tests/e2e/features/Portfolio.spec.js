import { test, expect } from "@playwright/test";

test.describe("Portfolio Page E2E Tests", () => {
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

  test("should load Portfolio page without errors", async ({ page }) => {
    // Monitor console errors
    const consoleErrors = [];
    page.on("console", (msg) => {
      if (msg.type() === "error") {
        consoleErrors.push(msg.text());
      }
    });

    console.log("🧪 Testing Portfolio at /portfolio...");

    // Navigate to Portfolio page
    try {
      await page.goto("/portfolio", {
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
        `📊 Portfolio: ${consoleErrors.length} total errors, ${muiTabsErrors.length} MUI Tabs errors`
      );

      if (muiTabsErrors.length > 0) {
        console.log("❌ MUI Tabs errors on Portfolio:");
        muiTabsErrors.forEach((error) => console.log(`   - ${error}`));
      }

      // Should not have MUI Tabs errors on Portfolio page
      expect(
        muiTabsErrors.length,
        "Portfolio should not have MUI Tabs errors"
      ).toBe(0);

      // Verify page loaded successfully
      const body = page.locator("#root");
      await expect(body).toBeVisible();

      // Check for portfolio content
      const hasPortfolioContent = await page.locator("#root *").count();
      expect(hasPortfolioContent).toBeGreaterThan(0);

    } catch (error) {
      console.log("⚠️ Portfolio failed to load:", error.message);
      await page.screenshot({ path: 'debug-portfolio.png' });
      throw error;
    }
  });

  test("should display portfolio elements", async ({ page }) => {
    await page.goto("/portfolio", {
      waitUntil: "domcontentloaded",
      timeout: 15000,
    });
    await page.waitForTimeout(2000);

    // Look for common portfolio elements
    const portfolioSelectors = [
      '[data-testid*="portfolio"]',
      '[class*="portfolio"]',
      '[class*="holding"]',
      '[class*="position"]',
      'table', // Holdings table
      'canvas', // Charts
      'svg', // SVG charts
      '.MuiCard-root', // Card components
    ];

    let hasPortfolioElements = false;
    for (const selector of portfolioSelectors) {
      const elements = page.locator(selector);
      const count = await elements.count();
      if (count > 0) {
        hasPortfolioElements = true;
        break;
      }
    }

    // Page should have some portfolio UI elements
    expect(hasPortfolioElements).toBe(true);
  });
});