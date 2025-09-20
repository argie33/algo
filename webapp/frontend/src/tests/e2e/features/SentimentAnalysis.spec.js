import { test, expect } from "@playwright/test";

test.describe("Sentiment Analysis Page E2E Tests", () => {
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

  test("should load Sentiment Analysis page without errors", async ({ page }) => {
    // Monitor console errors
    const consoleErrors = [];
    page.on("console", (msg) => {
      if (msg.type() === "error") {
        consoleErrors.push(msg.text());
      }
    });

    console.log("🧪 Testing Sentiment Analysis at /sentiment...");

    // Navigate to Sentiment Analysis page
    try {
      await page.goto("/sentiment", {
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
        `📊 Sentiment Analysis: ${consoleErrors.length} total errors, ${muiTabsErrors.length} MUI Tabs errors`
      );

      if (muiTabsErrors.length > 0) {
        console.log("❌ MUI Tabs errors on Sentiment Analysis:");
        muiTabsErrors.forEach((error) => console.log(`   - ${error}`));
      }

      // Should not have MUI Tabs errors on Sentiment Analysis page
      expect(
        muiTabsErrors.length,
        "Sentiment Analysis should not have MUI Tabs errors"
      ).toBe(0);

      // Verify page loaded successfully
      const body = page.locator("body");
      await expect(body).toBeVisible();

      // Check for sentiment analysis content
      const hasSentimentContent = await page.locator("body *").count();
      expect(hasSentimentContent).toBeGreaterThan(0);

    } catch (error) {
      console.log("⚠️ Sentiment Analysis failed to load:", error.message);
      await page.screenshot({ path: 'debug-sentiment-analysis.png' });
      throw error;
    }
  });

  test("should display sentiment analysis elements", async ({ page }) => {
    await page.goto("/sentiment", {
      waitUntil: "domcontentloaded",
      timeout: 15000,
    });
    await page.waitForSelector("#root", { timeout: 10000 });
    await page.waitForTimeout(2000);

    // Look for common sentiment analysis elements
    const sentimentSelectors = [
      '[data-testid*="sentiment"]',
      '[class*="sentiment"]',
      '[class*="score"]',
      '[class*="analysis"]',
      'canvas', // Charts
      'svg', // SVG charts
      '.MuiCard-root', // Card components
      '.MuiProgress-root', // Progress indicators
    ];

    let hasSentimentElements = false;
    for (const selector of sentimentSelectors) {
      const elements = page.locator(selector);
      const count = await elements.count();
      if (count > 0) {
        hasSentimentElements = true;
        break;
      }
    }

    // Page should have some sentiment analysis UI elements
    expect(hasSentimentElements).toBe(true);
  });
});