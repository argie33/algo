import { test, expect } from "@playwright/test";

test.describe("Technical Analysis Page E2E Tests", () => {
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

  test("should load Technical Analysis page without errors", async ({ page }) => {
    // Monitor console errors
    const consoleErrors = [];
    page.on("console", (msg) => {
      if (msg.type() === "error") {
        consoleErrors.push(msg.text());
      }
    });

    console.log("🧪 Testing Technical Analysis at /technical...");

    // Navigate to Technical Analysis page
    try {
      await page.goto("/technical", {
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
        `📊 Technical Analysis: ${consoleErrors.length} total errors, ${muiTabsErrors.length} MUI Tabs errors`
      );

      if (muiTabsErrors.length > 0) {
        console.log("❌ MUI Tabs errors on Technical Analysis:");
        muiTabsErrors.forEach((error) => console.log(`   - ${error}`));
      }

      // Should not have MUI Tabs errors on Technical Analysis page
      expect(
        muiTabsErrors.length,
        "Technical Analysis should not have MUI Tabs errors"
      ).toBe(0);

      // Verify page loaded successfully
      const body = page.locator("body");
      await expect(body).toBeVisible();

      // Check for technical analysis content
      const hasTechnicalContent = await page.locator("body *").count();
      expect(hasTechnicalContent).toBeGreaterThan(0);

    } catch (error) {
      console.log("⚠️ Technical Analysis failed to load:", error.message);
      await page.screenshot({ path: 'debug-technical-analysis.png' });
      throw error;
    }
  });

  test("should display technical analysis elements", async ({ page }) => {
    await page.goto("/technical", {
      waitUntil: "domcontentloaded",
      timeout: 15000,
    });
    await page.waitForSelector("#root", { timeout: 10000 });
    await page.waitForTimeout(2000);

    // Look for common technical analysis elements
    const technicalSelectors = [
      '[data-testid*="technical"]',
      '[class*="technical"]',
      '[class*="chart"]',
      '[class*="indicator"]',
      'canvas', // Chart canvases
      'svg', // SVG charts
      '.MuiCard-root', // Card components
    ];

    let hasTechnicalElements = false;
    for (const selector of technicalSelectors) {
      const elements = page.locator(selector);
      const count = await elements.count();
      if (count > 0) {
        hasTechnicalElements = true;
        break;
      }
    }

    // Page should have some technical analysis UI elements
    expect(hasTechnicalElements).toBe(true);
  });
});