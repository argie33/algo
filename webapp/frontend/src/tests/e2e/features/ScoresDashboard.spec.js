import { test, expect } from "@playwright/test";

test.describe("Scores Dashboard Page E2E Tests", () => {
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

  test("should load Scores Dashboard page without errors", async ({ page }) => {
    // Monitor console errors
    const consoleErrors = [];
    page.on("console", (msg) => {
      if (msg.type() === "error") {
        consoleErrors.push(msg.text());
      }
    });

    console.log("🧪 Testing Scores Dashboard at /scores...");

    // Navigate to Scores Dashboard page
    try {
      await page.goto("/scores", {
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
        `📊 Scores Dashboard: ${consoleErrors.length} total errors, ${muiTabsErrors.length} MUI Tabs errors`
      );

      if (muiTabsErrors.length > 0) {
        console.log("❌ MUI Tabs errors on Scores Dashboard:");
        muiTabsErrors.forEach((error) => console.log(`   - ${error}`));
      }

      // Should not have MUI Tabs errors on Scores Dashboard page
      expect(
        muiTabsErrors.length,
        "Scores Dashboard should not have MUI Tabs errors"
      ).toBe(0);

      // Verify page loaded successfully
      const body = page.locator("body");
      await expect(body).toBeVisible();

      // Check for scores dashboard content
      const hasScoresContent = await page.locator("body *").count();
      expect(hasScoresContent).toBeGreaterThan(0);

    } catch (error) {
      console.log("⚠️ Scores Dashboard failed to load:", error.message);
      await page.screenshot({ path: 'debug-scores-dashboard.png' });
      throw error;
    }
  });

  test("should display scores dashboard elements", async ({ page }) => {
    await page.goto("/scores", {
      waitUntil: "domcontentloaded",
      timeout: 15000,
    });
    await page.waitForSelector("#root", { timeout: 10000 });
    await page.waitForTimeout(2000);

    // Look for common scores dashboard elements
    const scoresSelectors = [
      '[data-testid*="score"]',
      '[class*="score"]',
      '[class*="dashboard"]',
      '[class*="rating"]',
      'table', // Scores table
      'canvas', // Charts
      'svg', // SVG charts
      '.MuiCard-root', // Card components
    ];

    let hasScoresElements = false;
    for (const selector of scoresSelectors) {
      const elements = page.locator(selector);
      const count = await elements.count();
      if (count > 0) {
        hasScoresElements = true;
        break;
      }
    }

    // Page should have some scores dashboard UI elements
    expect(hasScoresElements).toBe(true);
  });
});