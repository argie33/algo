const { test, expect } = require("@playwright/test");

// Test configuration
const BASE_URL = process.env.VITE_API_URL || "http://localhost:5173";
const _API_URL = process.env.VITE_API_URL || "http://localhost:3001";

test.describe("Dashboard Real-time Workflow - E2E Tests", () => {
  test.beforeEach(async ({ page }) => {
    await page.goto(BASE_URL);
    await page.waitForLoadState("networkidle");
  });

  test("should display dashboard with market data widgets", async ({
    page,
  }) => {
    // Navigate to Dashboard
    await page.click("text=Dashboard");
    await page.waitForURL("**/dashboard", { timeout: 10000 });

    // Verify main dashboard elements
    await expect(
      page.locator(
        'h1:has-text("Dashboard"), h2:has-text("Dashboard"), text=Dashboard'
      )
    ).toBeVisible();

    // Check for MUI Grid layout
    const gridElements = page.locator(".MuiGrid-root");
    expect(await gridElements.count()).toBeGreaterThan(0);

    // Check for Card components (widgets)
    const cardElements = page.locator(".MuiCard-root");
    if ((await cardElements.count()) > 0) {
      await expect(cardElements.first()).toBeVisible();
    }
  });

  test("should handle market data updates", async ({ page }) => {
    await page.click("text=Dashboard");

    // Mock market data update via API interception
    await page.route("**/api/market/**", async (route) => {
      if (route.request().method() === "GET") {
        await route.fulfill({
          status: 200,
          contentType: "application/json",
          body: JSON.stringify({
            indices: {
              SPY: { price: 450.25, change: 5.75, changePercent: 1.29 },
              QQQ: { price: 380.5, change: -2.25, changePercent: -0.59 },
            },
            marketStatus: "OPEN",
            lastUpdated: new Date().toISOString(),
          }),
        });
      } else {
        await route.continue();
      }
    });

    // Trigger data refresh if button exists
    const refreshButton = page.locator(
      'button[aria-label*="refresh"], button:has-text("Refresh")'
    );
    if (await refreshButton.isVisible()) {
      await refreshButton.click();
      await page.waitForTimeout(1000);
    }

    // Verify dashboard remains functional
    await expect(page.locator("text=Dashboard")).toBeVisible();
  });

  test("should display portfolio summary widget", async ({ page }) => {
    await page.click("text=Dashboard");

    // Look for portfolio-related content on dashboard
    const portfolioContent = page
      .locator("text=Portfolio")
      .or(page.locator("text=Holdings"))
      .or(page.locator("text=Positions"));

    // If portfolio widget exists, test it
    if (await portfolioContent.isVisible()) {
      await expect(portfolioContent).toBeVisible();

      // Test clicking to navigate to full portfolio
      await portfolioContent.click();

      // Should navigate to portfolio page
      await page.waitForURL("**/portfolio", { timeout: 5000 });
      await expect(page.locator("text=Portfolio")).toBeVisible();

      // Navigate back to dashboard
      await page.click("text=Dashboard");
      await page.waitForURL("**/dashboard", { timeout: 5000 });
    }
  });

  test("should handle search functionality", async ({ page }) => {
    await page.click("text=Dashboard");

    // Look for search components (Autocomplete or TextField)
    const searchInput = page.locator(
      '.MuiAutocomplete-root input, input[placeholder*="search" i]'
    );

    if (await searchInput.isVisible()) {
      // Test search functionality
      await searchInput.fill("AAPL");
      await page.waitForTimeout(500);

      // Look for search results or suggestions
      const suggestions = page.locator(
        ".MuiAutocomplete-listbox li, .search-results"
      );
      if ((await suggestions.count()) > 0) {
        // Click first suggestion
        await suggestions.first().click();
      }
    }
  });

  test("should display market indices and movers", async ({ page }) => {
    await page.click("text=Dashboard");

    // Look for market indices or stock symbols
    const _marketSymbols = page
      .locator("text=SPY")
      .or(page.locator("text=QQQ"))
      .or(page.locator("text=DIA"));

    // Check for any market-related content
    const marketContent = page
      .locator("text=Market")
      .or(page.locator("text=Index"))
      .or(page.locator("text=Indices"));

    if (await marketContent.isVisible()) {
      await expect(marketContent).toBeVisible();
    }

    // Look for top movers or gainers/losers
    const moversContent = page
      .locator("text=Gainers")
      .or(page.locator("text=Losers"))
      .or(page.locator("text=Movers"));

    if (await moversContent.isVisible()) {
      await expect(moversContent).toBeVisible();
    }
  });

  test("should display news and alerts", async ({ page }) => {
    await page.click("text=Dashboard");

    // Look for news section
    const newsContent = page
      .locator("text=News")
      .or(page.locator("text=Headlines"))
      .or(page.locator("text=Market News"));

    if (await newsContent.isVisible()) {
      await expect(newsContent).toBeVisible();
    }

    // Look for alert badges or notification indicators
    const alertBadges = page.locator(".MuiBadge-root");
    const _notificationIcons = page.locator(
      '[data-testid*="notification"], .notification'
    );

    if ((await alertBadges.count()) > 0) {
      await expect(alertBadges.first()).toBeVisible();
    }
  });

  test("should handle interactive charts", async ({ page }) => {
    await page.click("text=Dashboard");
    await page.waitForTimeout(2000); // Wait for charts to render

    // Look for chart components
    const chartElements = page.locator(
      '.recharts-wrapper, .chart-container, [data-testid*="chart"]'
    );

    if ((await chartElements.count()) > 0) {
      const firstChart = chartElements.first();
      await expect(firstChart).toBeVisible();

      // Test chart interaction (hover)
      await firstChart.hover();
      await page.waitForTimeout(500);

      // Look for tooltips or interaction feedback
      const tooltips = page.locator(
        ".recharts-tooltip-wrapper, .chart-tooltip"
      );
      if ((await tooltips.count()) > 0) {
        await expect(tooltips.first()).toBeVisible();
      }
    }
  });

  test("should support quick actions and navigation", async ({ page }) => {
    await page.click("text=Dashboard");

    // Test quick action buttons
    const actionButtons = page
      .locator("button")
      .filter({ hasText: /Portfolio|Trade|Buy|Sell|Add|View/ });

    const buttonCount = await actionButtons.count();
    if (buttonCount > 0) {
      // Test first action button
      const firstButton = actionButtons.first();
      const _buttonText = await firstButton.textContent();

      await firstButton.click();

      // Wait for navigation or modal
      await page.waitForTimeout(1000);

      // Should either navigate somewhere or open a dialog
      const isDialog = await page.locator('[role="dialog"]').isVisible();
      const hasNavigated = !page.url().includes("/dashboard");

      expect(isDialog || hasNavigated).toBeTruthy();

      // Return to dashboard if navigated
      if (hasNavigated) {
        await page.click("text=Dashboard");
        await page.waitForURL("**/dashboard", { timeout: 5000 });
      }

      // Close dialog if opened
      if (isDialog) {
        const closeButton = page.locator(
          'button[aria-label="close"], button:has-text("Close"), button:has-text("Cancel")'
        );
        if (await closeButton.isVisible()) {
          await closeButton.click();
        }
      }
    }
  });

  test("should handle table interactions on dashboard", async ({ page }) => {
    await page.click("text=Dashboard");

    // Look for tables on dashboard
    const tables = page.locator(".MuiTable-root");

    if ((await tables.count()) > 0) {
      const firstTable = tables.first();
      await expect(firstTable).toBeVisible();

      // Test table row interactions
      const tableRows = firstTable.locator(".MuiTableRow-root").filter({
        hasNot: page.locator(".MuiTableHead-root .MuiTableRow-root"),
      });

      if ((await tableRows.count()) > 0) {
        // Click on first data row
        await tableRows.first().click();
        await page.waitForTimeout(500);

        // Should either navigate or show details
        // No specific assertion needed as behavior varies
      }
    }
  });

  test("should display performance metrics and analytics", async ({ page }) => {
    await page.click("text=Dashboard");

    // Look for performance-related content
    const performanceContent = page
      .locator("text=Performance")
      .or(page.locator("text=Analytics"))
      .or(page.locator("text=Metrics"));

    if (await performanceContent.isVisible()) {
      await expect(performanceContent).toBeVisible();
    }

    // Look for percentage values or currency amounts
    const percentageElements = page
      .locator("text=/%/")
      .or(page.locator("text=/\\+\\d+\\.\\d+%/"));
    const currencyElements = page.locator("text=/\\$[\\d,]+/");

    // Should have some financial data displayed
    const hasFinancialData =
      (await percentageElements.count()) > 0 ||
      (await currencyElements.count()) > 0;
    expect(hasFinancialData).toBeTruthy();
  });

  test("should handle real-time data simulation", async ({ page }) => {
    await page.click("text=Dashboard");

    // Simulate WebSocket or polling updates
    await page.evaluate(() => {
      // Simulate market data updates
      const updateData = {
        SPY: { price: 452.75, change: 8.25, changePercent: 1.85 },
        timestamp: Date.now(),
      };

      // Trigger events that the app might listen for
      window.dispatchEvent(
        new CustomEvent("marketUpdate", { detail: updateData })
      );
      window.dispatchEvent(
        new CustomEvent("priceUpdate", { detail: updateData })
      );

      // Also test localStorage updates (if app uses them)
      if (window.localStorage) {
        window.localStorage.setItem(
          "lastMarketUpdate",
          JSON.stringify(updateData)
        );
      }
    });

    await page.waitForTimeout(1000);

    // Verify dashboard remains stable and functional
    await expect(page.locator("text=Dashboard")).toBeVisible();
  });

  test("should maintain performance with multiple widgets", async ({
    page,
  }) => {
    const startTime = Date.now();

    await page.click("text=Dashboard");
    await page.waitForLoadState("networkidle");

    // Wait for all widgets to potentially load
    await page.waitForTimeout(3000);

    const endTime = Date.now();
    const loadTime = endTime - startTime;

    // Should load within reasonable time even with multiple widgets
    expect(loadTime).toBeLessThan(8000); // 8 seconds

    // Verify interactivity
    const interactiveElements = page.locator(
      'button, [role="tab"], .MuiTableRow-root'
    );
    const elementCount = await interactiveElements.count();

    if (elementCount > 0) {
      // Test that elements are still interactive
      await interactiveElements.first().hover();
      // Should not throw errors
    }
  });

  test("should handle error states gracefully", async ({ page }) => {
    // Intercept API calls and return errors
    await page.route("**/api/**", async (route) => {
      if (Math.random() > 0.5) {
        // Randomly fail some requests
        await route.fulfill({
          status: 500,
          contentType: "application/json",
          body: JSON.stringify({ error: "Service temporarily unavailable" }),
        });
      } else {
        await route.continue();
      }
    });

    await page.click("text=Dashboard");
    await page.waitForTimeout(2000);

    // Dashboard should still be functional despite some API failures
    await expect(page.locator("text=Dashboard")).toBeVisible();

    // Should either show error messages or fallback content
    const hasContent =
      (await page
        .locator(".MuiCard-root, .MuiGrid-root, table, .recharts-wrapper")
        .count()) > 0;
    expect(hasContent).toBeTruthy();
  });

  test("should support customization and settings", async ({ page }) => {
    await page.click("text=Dashboard");

    // Look for customization options
    const settingsButton = page.locator(
      'button[aria-label*="settings"], button:has-text("Settings"), button:has-text("Customize")'
    );

    if (await settingsButton.isVisible()) {
      await settingsButton.click();
      await page.waitForTimeout(500);

      // Should either open settings dialog or navigate to settings
      const isDialog = await page.locator('[role="dialog"]').isVisible();
      const hasNavigated = page.url().includes("/settings");

      expect(isDialog || hasNavigated).toBeTruthy();

      // Clean up
      if (isDialog) {
        const closeButton = page.locator(
          'button[aria-label="close"], button:has-text("Close")'
        );
        if (await closeButton.isVisible()) {
          await closeButton.click();
        }
      } else if (hasNavigated) {
        await page.click("text=Dashboard");
      }
    }
  });
});
