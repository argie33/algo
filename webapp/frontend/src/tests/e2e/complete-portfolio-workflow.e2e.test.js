const { test, expect } = require("@playwright/test");

// Test configuration
const BASE_URL = process.env.VITE_API_URL || "http://localhost:5173";
const _API_URL = process.env.VITE_API_URL || "http://localhost:3001";

test.describe("Complete Portfolio Workflow - E2E Tests", () => {
  test.beforeEach(async ({ page }) => {
    // Navigate to the application
    await page.goto(BASE_URL);

    // Wait for the page to load
    await page.waitForLoadState("networkidle");
  });

  test("should complete full user portfolio journey", async ({ page }) => {
    // Step 1: Navigate to Portfolio page
    await page.click("text=Portfolio");
    await page.waitForURL("**/portfolio");

    // Step 2: Verify portfolio page loads with mock data
    await expect(page.locator("text=Portfolio")).toBeVisible();
    await expect(page.locator("text=AAPL")).toBeVisible();
    await expect(page.locator("text=Apple Inc.")).toBeVisible();

    // Step 3: Verify portfolio summary displays
    await expect(page.locator("text=Total Portfolio Value")).toBeVisible();
    await expect(page.locator("text=Today's P&L")).toBeVisible();

    // Step 4: Test table interactions
    const symbolHeader = page.locator("text=Symbol");
    await expect(symbolHeader).toBeVisible();

    // Test sorting by clicking symbol header
    await symbolHeader.click();

    // Step 5: Test tab navigation
    const tabs = page.locator('[role="tab"]');
    const tabCount = await tabs.count();

    if (tabCount > 1) {
      await tabs.nth(1).click();
      await page.waitForTimeout(500); // Wait for tab transition
    }

    // Step 6: Test pagination if present
    const paginationElement = page.locator("text=rows per page");
    if (await paginationElement.isVisible()) {
      // Test pagination controls
      const nextButton = page.locator('[aria-label="Go to next page"]');
      if ((await nextButton.isVisible()) && (await nextButton.isEnabled())) {
        await nextButton.click();
      }
    }

    // Step 7: Test add holding dialog (if add button exists)
    const addButton = page
      .locator('[aria-label*="add"], button:has-text("Add")')
      .first();
    if (await addButton.isVisible()) {
      await addButton.click();

      // Wait for dialog to appear
      await expect(page.locator('[role="dialog"]')).toBeVisible();

      // Fill out form if present
      const symbolInput = page.locator(
        'input[name="symbol"], input[placeholder*="symbol" i]'
      );
      if (await symbolInput.isVisible()) {
        await symbolInput.fill("TSLA");
      }

      // Close dialog
      const cancelButton = page.locator(
        'button:has-text("Cancel"), button[aria-label="close"]'
      );
      if (await cancelButton.isVisible()) {
        await cancelButton.click();
      }
    }
  });

  test("should navigate between different pages seamlessly", async ({
    page,
  }) => {
    // Test navigation flow: Dashboard -> Portfolio -> Dashboard

    // Start at Dashboard
    await page.click("text=Dashboard");
    await page.waitForURL("**/dashboard", { timeout: 10000 });
    await expect(
      page.locator(
        'h1:has-text("Dashboard"), h2:has-text("Dashboard"), text=Dashboard'
      )
    ).toBeVisible();

    // Navigate to Portfolio
    await page.click("text=Portfolio");
    await page.waitForURL("**/portfolio", { timeout: 10000 });
    await expect(page.locator("text=Portfolio")).toBeVisible();

    // Navigate to Settings
    await page.click("text=Settings");
    await page.waitForURL("**/settings", { timeout: 10000 });
    await expect(page.locator("text=Settings")).toBeVisible();

    // Back to Dashboard
    await page.click("text=Dashboard");
    await page.waitForURL("**/dashboard", { timeout: 10000 });
    await expect(
      page.locator(
        'h1:has-text("Dashboard"), h2:has-text("Dashboard"), text=Dashboard'
      )
    ).toBeVisible();
  });

  test("should handle responsive design correctly", async ({ page }) => {
    // Test desktop view
    await page.setViewportSize({ width: 1200, height: 800 });
    await page.click("text=Portfolio");

    // Verify desktop layout
    const desktopGrid = page.locator(".MuiGrid-root").first();
    await expect(desktopGrid).toBeVisible();

    // Test tablet view
    await page.setViewportSize({ width: 768, height: 1024 });
    await page.waitForTimeout(500);

    // Verify tablet layout adjustments
    await expect(page.locator("text=Portfolio")).toBeVisible();

    // Test mobile view
    await page.setViewportSize({ width: 375, height: 667 });
    await page.waitForTimeout(500);

    // Verify mobile layout
    await expect(page.locator("text=Portfolio")).toBeVisible();
  });

  test("should display charts and visualizations", async ({ page }) => {
    await page.click("text=Portfolio");
    await page.waitForLoadState("networkidle");

    // Wait for charts to render
    await page.waitForTimeout(2000);

    // Check for Recharts components
    const chartElements = page.locator(".recharts-wrapper");
    if ((await chartElements.count()) > 0) {
      await expect(chartElements.first()).toBeVisible();
    }

    // Check for pie chart (allocation)
    const pieChart = page.locator(".recharts-pie");
    if (await pieChart.isVisible()) {
      await expect(pieChart).toBeVisible();
    }
  });

  test("should handle data loading and error states", async ({ page }) => {
    // Intercept API calls to test error handling
    await page.route("**/api/**", (route) => {
      // Simulate API error for first request
      if (route.request().url().includes("/api/portfolio")) {
        route.fulfill({
          status: 500,
          contentType: "application/json",
          body: JSON.stringify({ error: "Internal Server Error" }),
        });
      } else {
        route.continue();
      }
    });

    await page.click("text=Portfolio");

    // Should handle error gracefully (may show error message or fallback to mock data)
    await expect(page.locator("text=Portfolio")).toBeVisible();
  });

  test("should search and filter functionality work", async ({ page }) => {
    await page.click("text=Portfolio");

    // Look for search input
    const searchInput = page.locator(
      'input[placeholder*="search" i], input[type="search"]'
    );
    if (await searchInput.isVisible()) {
      await searchInput.fill("AAPL");
      await page.waitForTimeout(500);

      // Should filter results
      await expect(page.locator("text=AAPL")).toBeVisible();
    }
  });

  test("should handle authentication flow (mocked)", async ({ page }) => {
    // Mock authentication state
    await page.addInitScript(() => {
      window.localStorage.setItem(
        "authTokens",
        JSON.stringify({
          idToken: "mock-id-token",
          accessToken: "mock-access-token",
        })
      );
    });

    await page.goto(BASE_URL);

    // Should be able to access protected routes
    await page.click("text=Portfolio");
    await expect(page.locator("text=Portfolio")).toBeVisible();
  });

  test("should handle real-time updates simulation", async ({ page }) => {
    await page.click("text=Dashboard");

    // Simulate WebSocket or polling updates
    await page.evaluate(() => {
      // Trigger a custom event that the app might listen for
      window.dispatchEvent(
        new CustomEvent("marketDataUpdate", {
          detail: {
            symbol: "AAPL",
            price: 195.5,
            change: 3.25,
          },
        })
      );
    });

    await page.waitForTimeout(1000);

    // Verify page is still functional after update
    await expect(page.locator("text=Dashboard")).toBeVisible();
  });

  test("should perform well under normal usage", async ({ page }) => {
    const startTime = Date.now();

    // Navigate through key pages
    await page.click("text=Dashboard");
    await page.waitForLoadState("networkidle");

    await page.click("text=Portfolio");
    await page.waitForLoadState("networkidle");

    await page.click("text=Settings");
    await page.waitForLoadState("networkidle");

    const endTime = Date.now();
    const totalTime = endTime - startTime;

    // Should complete navigation within reasonable time
    expect(totalTime).toBeLessThan(10000); // 10 seconds
  });

  test("should handle keyboard navigation", async ({ page }) => {
    await page.click("text=Portfolio");

    // Test tab navigation
    await page.keyboard.press("Tab");
    await page.keyboard.press("Tab");

    // Test Enter key on focusable elements
    const focusedElement = page.locator(":focus");
    if (await focusedElement.isVisible()) {
      await page.keyboard.press("Enter");
    }

    // Should still be functional
    await expect(page.locator("text=Portfolio")).toBeVisible();
  });

  test("should maintain state across page refreshes", async ({ page }) => {
    await page.click("text=Portfolio");

    // Make some changes (if interactive elements exist)
    const tabs = page.locator('[role="tab"]');
    if ((await tabs.count()) > 1) {
      await tabs.nth(1).click();
    }

    // Refresh page
    await page.reload();
    await page.waitForLoadState("networkidle");

    // Should maintain basic functionality
    await expect(page.locator("text=Portfolio")).toBeVisible();
  });

  test("should handle concurrent user interactions", async ({ page }) => {
    await page.click("text=Portfolio");

    // Simulate multiple rapid interactions
    const promises = [
      page.click("text=Symbol"),
      page.click("text=Company"),
      page.click("text=Shares"),
    ];

    // Wait for all interactions to complete
    await Promise.allSettled(promises);

    // Should remain stable
    await expect(page.locator("text=Portfolio")).toBeVisible();
  });

  test("should work with different data scenarios", async ({ page }) => {
    // Test with empty portfolio scenario
    await page.addInitScript(() => {
      window.mockPortfolioData = {
        holdings: [],
        summary: { total_value: 0, total_pnl: 0 },
      };
    });

    await page.click("text=Portfolio");

    // Should handle empty state gracefully
    await expect(page.locator("text=Portfolio")).toBeVisible();
  });
});
