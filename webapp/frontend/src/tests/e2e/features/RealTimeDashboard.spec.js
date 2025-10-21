import { test, expect } from "@playwright/test";

test.describe("Real-Time Dashboard Page E2E Tests", () => {
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

  test("should load Real-Time Dashboard page without errors", async ({ page }) => {
    // Monitor console errors
    const consoleErrors = [];
    page.on("console", (msg) => {
      if (msg.type() === "error") {
        consoleErrors.push(msg.text());
      }
    });

    console.log("🧪 Testing Real-Time Dashboard at /realtime...");

    // Navigate to Real-Time Dashboard page
    try {
      await page.goto("/realtime", {
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
        `📊 Real-Time Dashboard: ${consoleErrors.length} total errors, ${muiTabsErrors.length} MUI Tabs errors`
      );

      if (muiTabsErrors.length > 0) {
        console.log("❌ MUI Tabs errors on Real-Time Dashboard:");
        muiTabsErrors.forEach((error) => console.log(`   - ${error}`));
      }

      // Should not have MUI Tabs errors on Real-Time Dashboard page
      expect(
        muiTabsErrors.length,
        "Real-Time Dashboard should not have MUI Tabs errors"
      ).toBe(0);

      // Verify page loaded successfully
      const body = page.locator("#root");
      await expect(body).toBeVisible();

      // Check for real-time dashboard content
      const hasRealTimeContent = await page.locator("#root *").count();
      expect(hasRealTimeContent).toBeGreaterThan(0);

    } catch (error) {
      console.log("⚠️ Real-Time Dashboard failed to load:", error.message);
      await page.screenshot({ path: 'debug-realtime-dashboard.png' });
      throw error;
    }
  });

  test("should display real-time dashboard elements", async ({ page }) => {
    await page.goto("/realtime", {
      waitUntil: "domcontentloaded",
      timeout: 15000,
    });
    await page.waitForTimeout(2000);

    // Look for common real-time dashboard elements
    const realTimeSelectors = [
      '[data-testid*="realtime"]',
      '[data-testid*="live"]',
      '[class*="realtime"]',
      '[class*="live"]',
      '[class*="streaming"]',
      'canvas', // Charts
      'svg', // SVG charts
      '.MuiCard-root', // Card components
    ];

    let hasRealTimeElements = false;
    for (const selector of realTimeSelectors) {
      const elements = page.locator(selector);
      const count = await elements.count();
      if (count > 0) {
        hasRealTimeElements = true;
        break;
      }
    }

    // Page should have some real-time dashboard UI elements
    expect(hasRealTimeElements).toBe(true);
  });
});