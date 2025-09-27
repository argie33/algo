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

      // Check for critical errors (ignore minor warnings)
      const criticalErrors = consoleErrors.filter(
        (error) =>
          !error.includes("Warning:") &&
          !error.includes("DevTools") &&
          error.includes("Error")
      );

      console.log(
        `📊 Scores Dashboard: ${consoleErrors.length} total console messages, ${criticalErrors.length} critical errors`
      );

      if (criticalErrors.length > 0) {
        console.log("❌ Critical errors on Scores Dashboard:");
        criticalErrors.forEach((error) => console.log(`   - ${error}`));
      }

      // Should not have critical errors on Scores Dashboard page
      expect(
        criticalErrors.length,
        "Scores Dashboard should not have critical errors"
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

  test("should display scores dashboard with list view and search", async ({ page }) => {
    await page.goto("/scores", {
      waitUntil: "domcontentloaded",
      timeout: 15000,
    });
    await page.waitForSelector("#root", { timeout: 10000 });
    await page.waitForTimeout(2000);

    // Check for dashboard title
    const titleElement = page.locator('text=/Stock Scores Dashboard/i');
    await expect(titleElement).toBeVisible();

    // Check for search functionality
    const searchInput = page.locator('input[placeholder*="Search"]');
    await expect(searchInput).toBeVisible();

    // Check for summary statistics
    const totalStocks = page.locator('text=/Total Stocks/i');
    await expect(totalStocks).toBeVisible();

    // Check for stocks list (should be accordion format, not dropdown)
    const stocksList = page.locator('.MuiAccordion-root');
    await expect(stocksList.first()).toBeVisible();

    // Verify no dropdown/autocomplete present
    const autocomplete = page.locator('.MuiAutocomplete-root');
    await expect(autocomplete).toHaveCount(0);

    // Verify no methodology tab
    const methodologyTab = page.locator('text=/Methodology/i');
    await expect(methodologyTab).toHaveCount(0);
  });

  test("should expand accordion and show factor details", async ({ page }) => {
    await page.goto("/scores", {
      waitUntil: "domcontentloaded",
      timeout: 15000,
    });
    await page.waitForSelector("#root", { timeout: 10000 });
    await page.waitForTimeout(3000);

    // Wait for stocks to load
    const firstAccordion = page.locator('.MuiAccordion-root').first();
    await expect(firstAccordion).toBeVisible();

    // Click to expand first accordion
    const accordionSummary = firstAccordion.locator('.MuiAccordionSummary-root');
    await accordionSummary.click();

    // Wait for expansion
    await page.waitForTimeout(1000);

    // Check for factor analysis content
    const factorAnalysis = page.locator('text=/Factor Analysis/i');
    await expect(factorAnalysis).toBeVisible();

    // Check for individual factors
    const momentumFactor = page.locator('text=/Momentum/i');
    const trendFactor = page.locator('text=/Trend/i');
    const valueFactor = page.locator('text=/Value/i');
    const qualityFactor = page.locator('text=/Quality/i');
    const technicalFactor = page.locator('text=/Technical/i');
    const riskFactor = page.locator('text=/Risk/i');

    await expect(momentumFactor).toBeVisible();
    await expect(trendFactor).toBeVisible();
    await expect(valueFactor).toBeVisible();
    await expect(qualityFactor).toBeVisible();
    await expect(technicalFactor).toBeVisible();
    await expect(riskFactor).toBeVisible();
  });

  test("should filter stocks with search functionality", async ({ page }) => {
    await page.goto("/scores", {
      waitUntil: "domcontentloaded",
      timeout: 15000,
    });
    await page.waitForSelector("#root", { timeout: 10000 });
    await page.waitForTimeout(3000);

    // Wait for stocks to load
    const stocksList = page.locator('.MuiAccordion-root');
    const initialCount = await stocksList.count();

    if (initialCount > 0) {
      // Use search functionality
      const searchInput = page.locator('input[placeholder*="Search"]');
      await searchInput.fill('AAPL');
      await page.waitForTimeout(1000);

      // Check filtered results
      const filteredCount = await stocksList.count();
      expect(filteredCount).toBeLessThanOrEqual(initialCount);

      // Clear search
      await searchInput.fill('');
      await page.waitForTimeout(1000);

      // Should show all stocks again
      const restoredCount = await stocksList.count();
      expect(restoredCount).toBe(initialCount);
    }
  });

  test("should not display peer comparison or methodology sections", async ({ page }) => {
    await page.goto("/scores", {
      waitUntil: "domcontentloaded",
      timeout: 15000,
    });
    await page.waitForSelector("#root", { timeout: 10000 });
    await page.waitForTimeout(3000);

    // Verify no peer comparison
    const peerComparison = page.locator('text=/Peer Comparison/i');
    await expect(peerComparison).toHaveCount(0);

    // Verify no methodology tab or section
    const methodology = page.locator('text=/Methodology/i');
    await expect(methodology).toHaveCount(0);

    // Verify no tabs structure (since we removed tabs)
    const tabsContainer = page.locator('.MuiTabs-root');
    await expect(tabsContainer).toHaveCount(0);
  });
});