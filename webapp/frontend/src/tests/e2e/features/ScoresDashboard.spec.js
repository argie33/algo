import { test, expect } from "@playwright/test";

test.describe("Bullseye Stock Screener E2E Tests", () => {
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

  test("should load Bullseye Stock Screener page without errors", async ({ page }) => {
    // Monitor console errors
    const consoleErrors = [];
    page.on("console", (msg) => {
      if (msg.type() === "error") {
        consoleErrors.push(msg.text());
      }
    });

    console.log("🧪 Testing Bullseye Stock Screener at /scores...");

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
        `📊 Bullseye Stock Screener: ${consoleErrors.length} total console messages, ${criticalErrors.length} critical errors`
      );

      if (criticalErrors.length > 0) {
        console.log("❌ Critical errors on Bullseye Stock Screener:");
        criticalErrors.forEach((error) => console.log(`   - ${error}`));
      }

      // Should not have critical errors on Scores Dashboard page
      expect(
        criticalErrors.length,
        "Bullseye Stock Screener should not have critical errors"
      ).toBe(0);

      // Verify page loaded successfully
      const body = page.locator("#root");
      await expect(body).toBeVisible();

      // Check for scores dashboard content
      const hasScoresContent = await page.locator("#root *").count();
      expect(hasScoresContent).toBeGreaterThan(0);

    } catch (error) {
      console.log("⚠️ Bullseye Stock Screener failed to load:", error.message);
      await page.screenshot({ path: 'debug-scores-dashboard.png' });
      throw error;
    }
  });

  test("should display Bullseye title and search functionality", async ({ page }) => {
    await page.goto("/scores", {
      waitUntil: "domcontentloaded",
      timeout: 15000,
    });
    await page.waitForTimeout(2000);

    // Check for Bullseye title
    const titleElement = page.locator('text=/Bullseye.*Stock Screener/i');
    await expect(titleElement).toBeVisible();

    // Check for search functionality
    const searchInput = page.locator('input[placeholder*="Search"]');
    await expect(searchInput).toBeVisible();

    // Check for summary statistics
    const totalStocks = page.locator('text=/Total Stocks Analyzed/i');
    await expect(totalStocks).toBeVisible();

    const topScore = page.locator('text=/Highest Overall Score/i');
    await expect(topScore).toBeVisible();

    const avgScore = page.locator('text=/Market Average/i');
    await expect(avgScore).toBeVisible();

    const highQuality = page.locator('text=/High Quality Stocks/i');
    await expect(highQuality).toBeVisible();
  });

  test("should display accordion with all individual score bars", async ({ page }) => {
    await page.goto("/scores", {
      waitUntil: "domcontentloaded",
      timeout: 15000,
    });
    await page.waitForTimeout(3000);

    // Check for accordion structure
    const accordions = page.locator('.MuiAccordion-root');
    const accordionCount = await accordions.count();
    expect(accordionCount).toBeGreaterThan(0);

    // Check for individual score labels in accordion summary (without colons - they're labels, not chips)
    const qualityLabel = page.locator('text=/^Quality$/i').first();
    const momentumLabel = page.locator('text=/^Momentum$/i').first();
    const valueLabel = page.locator('text=/^Value$/i').first();
    const growthLabel = page.locator('text=/^Growth$/i').first();
    const positioningLabel = page.locator('text=/^Positioning$/i').first();
    const trendLabel = page.locator('text=/^Trend$/i').first();
    const sentimentLabel = page.locator('text=/^Sentiment$/i').first();

    await expect(qualityLabel).toBeVisible();
    await expect(momentumLabel).toBeVisible();
    await expect(valueLabel).toBeVisible();
    await expect(growthLabel).toBeVisible();
    await expect(positioningLabel).toBeVisible();
    await expect(trendLabel).toBeVisible();
    await expect(sentimentLabel).toBeVisible();
  });

  test("should display score gauge with grade in accordion summary", async ({ page }) => {
    await page.goto("/scores", {
      waitUntil: "domcontentloaded",
      timeout: 15000,
    });
    await page.waitForTimeout(3000);

    // Check for score gauge (circular gauge with grade)
    const accordion = page.locator('.MuiAccordion-root').first();
    await expect(accordion).toBeVisible();

    // Score gauge should be visible in the accordion summary
    const scoreGauge = accordion.locator('div').filter({ hasText: /^[A-F][+-]?$/ }).first();
    await expect(scoreGauge).toBeVisible();
  });

  test("should expand accordion to show factor analysis and NOT show trading signal", async ({ page }) => {
    await page.goto("/scores", {
      waitUntil: "domcontentloaded",
      timeout: 15000,
    });
    await page.waitForTimeout(3000);

    // Wait for accordion to load
    const accordion = page.locator('.MuiAccordion-root').first();
    await expect(accordion).toBeVisible();

    // Find and click expand button
    const expandButton = accordion.locator('[aria-label*="expand"]').first();
    await expandButton.click();
    await page.waitForTimeout(1000);

    // Check for expanded content (factor analysis) - should show 7 factor cards (removed Relative Strength)
    const factorAnalysis = page.locator('text=/Quality & Fundamentals/i');
    await expect(factorAnalysis).toBeVisible();

    const priceAction = page.locator('text=/Price Action & Momentum/i');
    await expect(priceAction).toBeVisible();

    const trendAnalysis = page.locator('text=/Trend Analysis/i');
    await expect(trendAnalysis).toBeVisible();

    const valueAssessment = page.locator('text=/Value Assessment/i');
    await expect(valueAssessment).toBeVisible();

    const growthPotential = page.locator('text=/Growth Potential/i');
    await expect(growthPotential).toBeVisible();

    const marketPositioning = page.locator('text=/Market Positioning/i');
    await expect(marketPositioning).toBeVisible();

    const marketSentiment = page.locator('text=/Market Sentiment/i');
    await expect(marketSentiment).toBeVisible();

    // Trading Signal should NOT be visible as a separate card in factor analysis
    const tradingSignalCard = page.locator('text=/^Trading Signal$/i').last();
    await expect(tradingSignalCard).not.toBeVisible();
  });

  test("should filter stocks with search functionality", async ({ page }) => {
    await page.goto("/scores", {
      waitUntil: "domcontentloaded",
      timeout: 15000,
    });
    await page.waitForTimeout(3000);

    // Wait for initial data to load
    const accordion = page.locator('.MuiAccordion-root').first();
    await expect(accordion).toBeVisible();

    // Get initial accordion count
    const initialAccordions = page.locator('.MuiAccordion-root');
    const initialCount = await initialAccordions.count();

    if (initialCount > 0) {
      // Use search functionality
      const searchInput = page.locator('input[placeholder*="Search"]');
      await searchInput.fill('AAP');
      await page.waitForTimeout(1000);

      // Check filtered results
      const filteredAccordions = page.locator('.MuiAccordion-root');
      const filteredCount = await filteredAccordions.count();
      expect(filteredCount).toBeLessThanOrEqual(initialCount);

      // Clear search
      await searchInput.fill('');
      await page.waitForTimeout(1000);

      // Should show all stocks again
      const restoredAccordions = page.locator('.MuiAccordion-root');
      const restoredCount = await restoredAccordions.count();
      expect(restoredCount).toBe(initialCount);
    }
  });

  test("should have clickable accordions that navigate to stock detail", async ({ page }) => {
    await page.goto("/scores", {
      waitUntil: "domcontentloaded",
      timeout: 15000,
    });
    await page.waitForTimeout(3000);

    // Wait for accordion to load
    const accordion = page.locator('.MuiAccordion-root').first();
    await expect(accordion).toBeVisible();

    // Get the symbol from the first accordion
    const symbolText = await accordion.locator('text=/^[A-Z]{1,5}$/').first().textContent();
    const symbol = symbolText?.trim();

    // Click the accordion
    await accordion.click();
    await page.waitForTimeout(1000);

    // Should navigate to stock detail page
    if (symbol) {
      await expect(page).toHaveURL(new RegExp(`/stocks/${symbol}`));
    }
  });

  test("should display advanced filter controls", async ({ page }) => {
    await page.goto("/scores", {
      waitUntil: "domcontentloaded",
      timeout: 15000,
    });
    await page.waitForTimeout(2000);

    // Check for filter icon button
    const filterButton = page.locator('button').filter({ has: page.locator('svg') }).first();
    await filterButton.click();
    await page.waitForTimeout(500);

    // Check for advanced score filters
    const minCompositeFilter = page.locator('text=/Min Composite/i');
    await expect(minCompositeFilter).toBeVisible();

    const minMomentumFilter = page.locator('text=/Min Momentum/i');
    await expect(minMomentumFilter).toBeVisible();

    const minQualityFilter = page.locator('text=/Min Quality/i');
    await expect(minQualityFilter).toBeVisible();

    const minValueFilter = page.locator('text=/Min Value/i');
    await expect(minValueFilter).toBeVisible();

    const minGrowthFilter = page.locator('text=/Min Growth/i');
    await expect(minGrowthFilter).toBeVisible();
  });

  test("should display trading signals in accordion summary only", async ({ page }) => {
    await page.goto("/scores", {
      waitUntil: "domcontentloaded",
      timeout: 15000,
    });
    await page.waitForTimeout(3000);

    // Wait for accordion to load
    const accordion = page.locator('.MuiAccordion-root').first();
    await expect(accordion).toBeVisible();

    // Check for trading signal in summary (should be BUY, SELL, HOLD, or N/A)
    const tradingSignal = accordion.locator('text=/^(BUY|SELL|HOLD|N/A)$/i').first();

    // Trading signal might not be loaded yet for all stocks, so we check if it exists
    const signalCount = await tradingSignal.count();
    if (signalCount > 0) {
      await expect(tradingSignal).toBeVisible();
    }
  });

  test("should display accordion format (not leaderboard tables)", async ({ page }) => {
    await page.goto("/scores", {
      waitUntil: "domcontentloaded",
      timeout: 15000,
    });
    await page.waitForTimeout(3000);

    // Verify accordion structure IS present
    const accordions = page.locator('.MuiAccordion-root');
    const accordionCount = await accordions.count();
    expect(accordionCount).toBeGreaterThan(0);

    // Verify NO leaderboard tables
    const leaderboardHeaders = page.locator('text=/Composite Score Leaders/i');
    await expect(leaderboardHeaders).not.toBeVisible();
  });
});
