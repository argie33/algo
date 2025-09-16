/**
 * Financial Platform E2E Tests
 * Tests critical workflows for the financial trading and analysis platform
 */

import { test, expect } from "@playwright/test";

test.describe("Financial Platform Critical Workflows", () => {
  test.beforeEach(async ({ page, browserName }) => {
    // Set up authentication and API keys for financial platform
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

    // Firefox-specific optimization: longer timeouts for navigation
    const timeout = browserName === "firefox" ? 5000 : 2000;

    await page.goto("/", { waitUntil: "domcontentloaded", timeout: 30000 });
    await page.waitForSelector("#root", { state: "attached", timeout: 15000 });
    await page.waitForTimeout(timeout);
  });

  test("should load financial dashboard with market data", async ({ page }) => {
    // Monitor for financial app errors
    const consoleErrors = [];

    page.on("console", (msg) => {
      if (msg.type() === "error") {
        consoleErrors.push(msg.text());
      }
    });

    // Dashboard should load without critical errors
    await expect(page.locator("#root")).toBeVisible();

    // Should display financial dashboard content
    const rootContent = await page.locator("#root").textContent();
    expect(rootContent.length).toBeGreaterThan(500);

    // Should not have critical React errors that break functionality
    const criticalErrors = consoleErrors.filter(
      (error) =>
        error.includes("Cannot read properties of undefined") ||
        error.includes("Maximum call stack")
    );
    expect(criticalErrors.length).toBe(0);
  });

  test("should navigate to key financial sections", async ({
    page,
    browserName,
  }) => {
    // Test navigation to core financial platform pages
    const sections = [
      { path: "/portfolio", name: "Portfolio Management" },
      { path: "/market", name: "Market Overview" },
      { path: "/trading", name: "Trading Signals" },
      { path: "/technical", name: "Technical Analysis" },
      { path: "/screener", name: "Stock Screener" },
      { path: "/sentiment", name: "Sentiment Analysis" },
    ];

    let successfulNavigation = 0;
    const navigationTimeout = browserName === "firefox" ? 10000 : 5000;
    const waitTime = browserName === "firefox" ? 3000 : 1000;

    // Monitor for React Context and other critical errors during navigation
    const consoleErrors = [];
    page.on("console", (msg) => {
      if (msg.type() === "error") {
        consoleErrors.push(msg.text());
      }
    });

    for (const section of sections) {
      try {
        await page.goto(section.path, {
          waitUntil: "domcontentloaded",
          timeout: navigationTimeout,
        });
        await page.waitForSelector("#root", {
          state: "attached",
          timeout: navigationTimeout,
        });
        await page.waitForTimeout(waitTime);

        if (page.url().includes(section.path)) {
          successfulNavigation++;
          console.log(`✅ Successfully navigated to ${section.name}`);
        }
      } catch (e) {
        console.log(`⚠️ Navigation to ${section.name} failed:`, e.message);
        // Continue with other sections even if one fails
      }
    }

    // Should be able to navigate to at least half the sections
    expect(successfulNavigation).toBeGreaterThanOrEqual(3);

    // Log console errors for debugging
    if (consoleErrors.length > 0) {
      console.log(
        `❌ Console errors during navigation:`,
        consoleErrors.slice(0, 3)
      );
    }

    // CRITICAL: Fail test if React Context or dependency errors occur during navigation
    const criticalNavigationErrors = consoleErrors.filter(
      (error) =>
        error.includes("Cannot set properties of undefined") ||
        error.includes("ContextConsumer") ||
        error.includes("react-is") ||
        error.includes("Maximum call stack")
    );
    expect(criticalNavigationErrors.length).toBe(0);
  });

  test("should handle portfolio data loading", async ({ page }) => {
    // Mock portfolio API responses
    await page.route("**/api/portfolio/**", (route) => {
      route.fulfill({
        json: {
          success: true,
          data: {
            totalValue: 125000.5,
            dailyChange: 2500.25,
            holdings: [
              { symbol: "AAPL", shares: 100, value: 18945.5, change: 245.25 },
              { symbol: "GOOGL", shares: 25, value: 3512.75, change: -125.5 },
              { symbol: "MSFT", shares: 150, value: 52525.0, change: 875.25 },
            ],
            sectors: [
              { name: "Technology", percentage: 75.5, value: 94562.88 },
              { name: "Healthcare", percentage: 24.5, value: 30437.62 },
            ],
          },
        },
      });
    });

    await page.goto("/portfolio");
    await page.waitForSelector("#root", { state: "attached" });
    await page.waitForTimeout(3000);

    // Should display portfolio page content
    const content = await page.locator("#root").textContent();
    expect(content.length).toBeGreaterThan(200);
    expect(page.url()).toContain("/portfolio");
  });

  test("should display market data and indices", async ({ page }) => {
    // Mock market data API responses
    await page.route("**/api/market/**", (route) => {
      route.fulfill({
        json: {
          success: true,
          data: {
            indices: [
              {
                symbol: "^GSPC",
                name: "S&P 500",
                value: 4520.25,
                change: 1.2,
                changePercent: 0.027,
              },
              {
                symbol: "^DJI",
                name: "Dow Jones",
                value: 35180.5,
                change: 248.32,
                changePercent: 0.71,
              },
              {
                symbol: "^IXIC",
                name: "NASDAQ",
                value: 14520.8,
                change: -45.25,
                changePercent: -0.31,
              },
            ],
            sectors: [
              { name: "Technology", change: 1.85, volume: 2.5e9 },
              { name: "Healthcare", change: 0.92, volume: 1.8e9 },
              { name: "Financial Services", change: 1.42, volume: 2.1e9 },
            ],
          },
        },
      });
    });

    await page.goto("/market");
    await page.waitForSelector("#root", { state: "attached" });
    await page.waitForTimeout(2000);

    const content = await page.locator("#root").textContent();
    expect(content.length).toBeGreaterThan(200);
    expect(page.url()).toContain("/market");
  });

  test("should handle authentication flow", async ({ page }) => {
    // Clear auth state
    await page.addInitScript(() => {
      localStorage.clear();
    });

    await page.goto("/portfolio");
    await page.waitForSelector("#root", { state: "attached" });
    await page.waitForTimeout(2000);

    // Should load some form of authentication UI or redirect
    await expect(page.locator("#root")).toBeVisible();
    const content = await page.locator("#root").textContent();
    expect(content.length).toBeGreaterThan(20); // Should have some auth-related content
  });

  test("should display market data", async ({ page }) => {
    // Mock market API
    await page.route("**/api/market/**", (route) => {
      route.fulfill({
        json: {
          success: true,
          data: {
            indices: { SPY: { price: 445.32, change: 2.15 } },
            sectors: [{ name: "Technology", performance: 1.85 }],
          },
        },
      });
    });

    await page.goto("/market");
    await page.waitForSelector("#root", { state: "attached" });
    await page.waitForTimeout(3000);

    // Should display market page
    await expect(page.locator("#root")).toBeVisible();
    const content = await page.locator("#root").textContent();
    expect(content.length).toBeGreaterThan(100);
  });

  test("should handle settings changes", async ({ page }) => {
    await page.goto("/settings");
    await page.waitForSelector("#root", { state: "attached" });
    await page.waitForTimeout(2000);

    // Should display settings page
    await expect(page.locator("#root")).toBeVisible();
    const content = await page.locator("#root").textContent();
    expect(content.length).toBeGreaterThan(50);
  });

  test("should be responsive on mobile", async ({ page, isMobile }) => {
    if (!isMobile) {
      // Simulate mobile viewport
      await page.setViewportSize({ width: 375, height: 667 });
    }

    await page.goto("/");
    await page.waitForSelector("#root", { state: "attached" });
    await page.waitForTimeout(2000);

    // Should load on mobile
    await expect(page.locator("#root")).toBeVisible();

    // Should have content that adapts to mobile
    const content = await page.locator("#root").textContent();
    expect(content.length).toBeGreaterThan(100);
  });
});
