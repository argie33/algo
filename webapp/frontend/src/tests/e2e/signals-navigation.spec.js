/**
 * Trading Signals Navigation and Basic Functionality E2E Test
 * Tests the signals page is accessible via menu and loads correctly
 */

import { test, expect } from "@playwright/test";

test.describe("Trading Signals Navigation", () => {
  test.beforeEach(async ({ page }) => {
    // Set up authenticated state
    await page.addInitScript(() => {
      localStorage.setItem("financial_auth_token", "test-auth-token");
      localStorage.setItem("user_data", JSON.stringify({
        username: "testuser",
        authenticated: true
      }));
    });
  });

  test("should navigate to signals page via stocks menu", async ({ page }) => {
    console.log("📊 Testing signals page navigation...");

    // Navigate to home page
    await page.goto("/");
    await page.waitForLoadState("networkidle");
    await page.waitForTimeout(1000);

    // Look for the stocks section in the navigation menu
    const stocksSection = page.locator('text="Stocks"').first();
    await expect(stocksSection).toBeVisible();

    // Click to expand stocks section if collapsed
    try {
      await stocksSection.click();
      await page.waitForTimeout(500);
    } catch (e) {
      console.log("Stocks section might already be expanded");
    }

    // Look for Trading Signals menu item
    const tradingSignalsLink = page.locator('text="Trading Signals"').first();
    await expect(tradingSignalsLink).toBeVisible();

    // Click on Trading Signals
    await tradingSignalsLink.click();
    await page.waitForLoadState("networkidle");
    await page.waitForTimeout(2000);

    // Verify we're on the signals page
    await expect(page).toHaveURL(/.*trading-signals.*/);

    // Check page title and main header
    const pageTitle = await page.title();
    expect(pageTitle).toContain("Trading Signals");

    // Verify main signals page elements are present
    await expect(page.locator('text="Trading Signals"').first()).toBeVisible();

    // Check for filter section
    await expect(page.locator('text="Filters"').first()).toBeVisible();

    // Check for signal type filter
    await expect(page.locator('text="Signal Type"').first()).toBeVisible();

    // Check for timeframe filter
    await expect(page.locator('text="Timeframe"').first()).toBeVisible();

    console.log("✅ Trading Signals page navigation test completed successfully");
  });

  test("should load signals data and display table", async ({ page }) => {
    console.log("📊 Testing signals data loading...");

    // Navigate directly to signals page
    await page.goto("/trading-signals");
    await page.waitForLoadState("networkidle");
    await page.waitForTimeout(3000);

    // Check if signals table is present
    const signalsTable = page.locator('table').first();
    await expect(signalsTable).toBeVisible();

    // Check for table headers
    await expect(page.locator('text="Symbol"').first()).toBeVisible();
    await expect(page.locator('text="Signal"').first()).toBeVisible();
    await expect(page.locator('text="Current Price"').first()).toBeVisible();

    console.log("✅ Trading Signals data loading test completed successfully");
  });

  test("should allow filtering signals", async ({ page }) => {
    console.log("📊 Testing signals filtering...");

    // Navigate to signals page
    await page.goto("/trading-signals");
    await page.waitForLoadState("networkidle");
    await page.waitForTimeout(2000);

    // Test timeframe filter
    const timeframeSelect = page.locator('text="Timeframe"').locator('..').locator('select, input[role="combobox"], [role="button"]').first();

    if (await timeframeSelect.isVisible()) {
      await timeframeSelect.click();
      await page.waitForTimeout(500);

      // Try to select weekly timeframe
      const weeklyOption = page.locator('text="Weekly"').first();
      if (await weeklyOption.isVisible()) {
        await weeklyOption.click();
        await page.waitForTimeout(1000);
        console.log("✅ Timeframe filter test completed");
      }
    }

    // Test signal type filter
    const signalTypeSelect = page.locator('text="Signal Type"').locator('..').locator('select, input[role="combobox"], [role="button"]').first();

    if (await signalTypeSelect.isVisible()) {
      await signalTypeSelect.click();
      await page.waitForTimeout(500);

      // Try to select buy signals only
      const buyOption = page.locator('text="Buy Only"').first();
      if (await buyOption.isVisible()) {
        await buyOption.click();
        await page.waitForTimeout(1000);
        console.log("✅ Signal type filter test completed");
      }
    }

    console.log("✅ Trading Signals filtering test completed successfully");
  });
});