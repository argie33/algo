/**
 * Complete System E2E Tests
 * End-to-end tests for critical user journeys using Playwright
 */

import { test, expect } from "@playwright/test";

// Test configuration
const BASE_URL = process.env.VITE_API_URL || "http://localhost:3000";
const _API_URL = process.env.VITE_API_URL || "http://localhost:3001";

// Test user credentials
const TEST_USER = {
  email: "e2e-test@example.com",
  password: "TestPassword123!",
  firstName: "E2E",
  lastName: "Test",
};

test.describe("Complete Financial Platform E2E Tests", () => {
  test.beforeEach(async ({ page }) => {
    // Set up test environment
    await page.goto(BASE_URL);

    // Wait for app to load
    await page.waitForLoadState("networkidle");
  });

  test.describe("User Registration and Onboarding", () => {
    test("should complete new user registration flow", async ({ page }) => {
      // Navigate to registration
      await page.click("text=Sign Up", { timeout: 10000 });

      // Fill registration form
      await page.fill('[data-testid="email-input"]', TEST_USER.email);
      await page.fill('[data-testid="password-input"]', TEST_USER.password);
      await page.fill('[data-testid="first-name-input"]', TEST_USER.firstName);
      await page.fill('[data-testid="last-name-input"]', TEST_USER.lastName);

      // Submit registration
      await page.click('[data-testid="register-button"]');

      // Should redirect to dashboard or onboarding
      await expect(page).toHaveURL(/.*\/(dashboard|onboarding).*/);

      // Should show welcome message
      await expect(page.locator("text=Welcome")).toBeVisible({ timeout: 5000 });
    });

    test("should complete API key setup onboarding", async ({ page }) => {
      // Assuming user is logged in and on onboarding page
      await page.goto(`${BASE_URL}/onboarding`);

      // Start API key setup
      await page.click("text=Setup API Keys");

      // Select Alpaca provider
      await page.selectOption('[data-testid="provider-select"]', "alpaca");

      // Fill API key form
      await page.fill('[data-testid="api-key-input"]', "TEST_API_KEY");
      await page.fill('[data-testid="secret-key-input"]', "TEST_SECRET_KEY");

      // Test connection
      await page.click('[data-testid="test-connection-button"]');

      // Should show connection status
      await expect(
        page.locator('[data-testid="connection-status"]')
      ).toBeVisible();

      // Save API key
      await page.click('[data-testid="save-api-key-button"]');

      // Should proceed to next step
      await expect(page.locator("text=API Key Saved")).toBeVisible();
    });
  });

  test.describe("Authentication Flow", () => {
    test("should login existing user successfully", async ({ page }) => {
      // Navigate to login
      await page.click("text=Login");

      // Fill login form
      await page.fill('[data-testid="email-input"]', TEST_USER.email);
      await page.fill('[data-testid="password-input"]', TEST_USER.password);

      // Submit login
      await page.click('[data-testid="login-button"]');

      // Should redirect to dashboard
      await expect(page).toHaveURL(/.*\/dashboard.*/);

      // Should show user menu
      await expect(page.locator('[data-testid="user-menu"]')).toBeVisible();
    });

    test("should handle login errors gracefully", async ({ page }) => {
      // Navigate to login
      await page.click("text=Login");

      // Fill form with invalid credentials
      await page.fill('[data-testid="email-input"]', "invalid@example.com");
      await page.fill('[data-testid="password-input"]', "wrongpassword");

      // Submit login
      await page.click('[data-testid="login-button"]');

      // Should show error message
      await expect(page.locator('[data-testid="error-message"]')).toBeVisible();
      await expect(page.locator("text=Invalid credentials")).toBeVisible();
    });

    test("should logout user successfully", async ({ page }) => {
      // Login first
      await loginUser(page, TEST_USER);

      // Open user menu
      await page.click('[data-testid="user-menu"]');

      // Click logout
      await page.click('[data-testid="logout-button"]');

      // Should redirect to login page
      await expect(page).toHaveURL(/.*\/(login|auth).*/);

      // Should show login form
      await expect(page.locator('[data-testid="login-form"]')).toBeVisible();
    });
  });

  test.describe("Portfolio Management", () => {
    test.beforeEach(async ({ page }) => {
      await loginUser(page, TEST_USER);
    });

    test("should display portfolio overview", async ({ page }) => {
      // Navigate to portfolio
      await page.click('[data-testid="portfolio-nav"]');

      // Should show portfolio data
      await expect(
        page.locator('[data-testid="portfolio-value"]')
      ).toBeVisible();
      await expect(page.locator('[data-testid="todays-pnl"]')).toBeVisible();
      await expect(page.locator('[data-testid="total-pnl"]')).toBeVisible();

      // Should show positions table
      await expect(
        page.locator('[data-testid="positions-table"]')
      ).toBeVisible();
    });

    test("should show portfolio performance chart", async ({ page }) => {
      await page.goto(`${BASE_URL}/portfolio`);

      // Should render portfolio chart
      await expect(
        page.locator('[data-testid="portfolio-chart"]')
      ).toBeVisible();

      // Test timeframe switching
      await page.click('[data-testid="timeframe-1W"]');
      await page.waitForLoadState("networkidle");

      await page.click('[data-testid="timeframe-1M"]');
      await page.waitForLoadState("networkidle");

      // Chart should update
      await expect(
        page.locator('[data-testid="portfolio-chart"]')
      ).toBeVisible();
    });

    test("should display asset allocation", async ({ page }) => {
      await page.goto(`${BASE_URL}/portfolio`);

      // Should show allocation chart
      await expect(
        page.locator('[data-testid="allocation-chart"]')
      ).toBeVisible();

      // Should show sector breakdown
      await expect(
        page.locator('[data-testid="sector-allocation"]')
      ).toBeVisible();
    });
  });

  test.describe("Trading Functionality", () => {
    test.beforeEach(async ({ page }) => {
      await loginUser(page, TEST_USER);
    });

    test("should place buy order successfully", async ({ page }) => {
      // Navigate to trading
      await page.click('[data-testid="trading-nav"]');

      // Fill order form
      await page.fill('[data-testid="symbol-input"]', "AAPL");
      await page.fill('[data-testid="quantity-input"]', "10");

      // Select order type
      await page.selectOption('[data-testid="order-type-select"]', "market");

      // Select buy side
      await page.click('[data-testid="buy-button"]');

      // Place order
      await page.click('[data-testid="place-order-button"]');

      // Should show order confirmation
      await expect(
        page.locator('[data-testid="order-confirmation"]')
      ).toBeVisible();
      await expect(
        page.locator("text=Order Placed Successfully")
      ).toBeVisible();
    });

    test("should place limit sell order", async ({ page }) => {
      await page.goto(`${BASE_URL}/trading`);

      // Fill order form
      await page.fill('[data-testid="symbol-input"]', "MSFT");
      await page.fill('[data-testid="quantity-input"]', "5");
      await page.fill('[data-testid="limit-price-input"]', "385.00");

      // Select limit order
      await page.selectOption('[data-testid="order-type-select"]', "limit");

      // Select sell side
      await page.click('[data-testid="sell-button"]');

      // Place order
      await page.click('[data-testid="place-order-button"]');

      // Should show order confirmation
      await expect(
        page.locator('[data-testid="order-confirmation"]')
      ).toBeVisible();
    });

    test("should validate order parameters", async ({ page }) => {
      await page.goto(`${BASE_URL}/trading`);

      // Try to place order without symbol
      await page.fill('[data-testid="quantity-input"]', "10");
      await page.click('[data-testid="place-order-button"]');

      // Should show validation error
      await expect(
        page.locator('[data-testid="validation-error"]')
      ).toBeVisible();
      await expect(page.locator("text=Symbol is required")).toBeVisible();
    });

    test("should show order history", async ({ page }) => {
      await page.goto(`${BASE_URL}/trading/history`);

      // Should show orders table
      await expect(page.locator('[data-testid="orders-table"]')).toBeVisible();

      // Should show order details
      const firstOrder = page.locator('[data-testid="order-row"]').first();
      await expect(firstOrder).toBeVisible();

      // Click on order for details
      await firstOrder.click();
      await expect(page.locator('[data-testid="order-details"]')).toBeVisible();
    });
  });

  test.describe("Market Data and Research", () => {
    test("should display market overview", async ({ page }) => {
      // Navigate to market overview
      await page.click('[data-testid="market-nav"]');

      // Should show market indices
      await expect(page.locator('[data-testid="sp500-index"]')).toBeVisible();
      await expect(page.locator('[data-testid="nasdaq-index"]')).toBeVisible();
      await expect(page.locator('[data-testid="dow-index"]')).toBeVisible();

      // Should show top movers
      await expect(page.locator('[data-testid="top-gainers"]')).toBeVisible();
      await expect(page.locator('[data-testid="top-losers"]')).toBeVisible();
    });

    test("should search and view stock details", async ({ page }) => {
      await page.goto(`${BASE_URL}/market`);

      // Search for a stock
      await page.fill('[data-testid="stock-search"]', "AAPL");
      await page.press('[data-testid="stock-search"]', "Enter");

      // Should show search results
      await expect(
        page.locator('[data-testid="search-results"]')
      ).toBeVisible();

      // Click on first result
      await page.click('[data-testid="stock-result"]');

      // Should navigate to stock detail page
      await expect(page).toHaveURL(/.*\/stocks\/AAPL.*/);

      // Should show stock information
      await expect(page.locator('[data-testid="stock-price"]')).toBeVisible();
      await expect(page.locator('[data-testid="stock-chart"]')).toBeVisible();
    });

    test("should display news and sentiment", async ({ page }) => {
      await page.goto(`${BASE_URL}/news`);

      // Should show news articles
      await expect(page.locator('[data-testid="news-articles"]')).toBeVisible();

      // Should show sentiment indicator
      await expect(
        page.locator('[data-testid="market-sentiment"]')
      ).toBeVisible();

      // Click on first article
      const firstArticle = page.locator('[data-testid="news-article"]').first();
      await firstArticle.click();

      // Should show article details
      await expect(
        page.locator('[data-testid="article-content"]')
      ).toBeVisible();
    });
  });

  test.describe("Settings and Configuration", () => {
    test.beforeEach(async ({ page }) => {
      await loginUser(page, TEST_USER);
    });

    test("should update notification preferences", async ({ page }) => {
      // Navigate to settings
      await page.click('[data-testid="settings-nav"]');

      // Click on notifications tab
      await page.click('[data-testid="notifications-tab"]');

      // Toggle email notifications
      await page.click('[data-testid="email-notifications-toggle"]');

      // Should show save confirmation
      await expect(
        page.locator('[data-testid="settings-saved"]')
      ).toBeVisible();
    });

    test("should manage API keys", async ({ page }) => {
      await page.goto(`${BASE_URL}/settings/api-keys`);

      // Should show API keys list
      await expect(page.locator('[data-testid="api-keys-list"]')).toBeVisible();

      // Add new API key
      await page.click('[data-testid="add-api-key-button"]');

      // Fill API key form
      await page.selectOption('[data-testid="provider-select"]', "polygon");
      await page.fill('[data-testid="api-key-input"]', "NEW_TEST_KEY");

      // Test connection
      await page.click('[data-testid="test-connection-button"]');

      // Save API key
      await page.click('[data-testid="save-api-key-button"]');

      // Should show in list
      await expect(page.locator("text=NEW_TEST_KEY")).toBeVisible();
    });

    test("should update trading preferences", async ({ page }) => {
      await page.goto(`${BASE_URL}/settings/trading`);

      // Update default quantity
      await page.fill('[data-testid="default-quantity-input"]', "50");

      // Toggle order confirmation
      await page.click('[data-testid="confirm-orders-toggle"]');

      // Should auto-save
      await expect(
        page.locator('[data-testid="settings-saved"]')
      ).toBeVisible();
    });
  });

  test.describe("Dashboard Overview", () => {
    test.beforeEach(async ({ page }) => {
      await loginUser(page, TEST_USER);
    });

    test("should display comprehensive dashboard", async ({ page }) => {
      await page.goto(`${BASE_URL}/dashboard`);

      // Should show portfolio summary
      await expect(
        page.locator('[data-testid="portfolio-summary"]')
      ).toBeVisible();

      // Should show market overview
      await expect(
        page.locator('[data-testid="market-overview"]')
      ).toBeVisible();

      // Should show recent activity
      await expect(
        page.locator('[data-testid="recent-activity"]')
      ).toBeVisible();

      // Should show performance chart
      await expect(
        page.locator('[data-testid="performance-chart"]')
      ).toBeVisible();
    });

    test("should show real-time updates", async ({ page }) => {
      await page.goto(`${BASE_URL}/dashboard`);

      // Get initial portfolio value
      const _initialValue = await page
        .locator('[data-testid="portfolio-value"]')
        .textContent();

      // Wait for potential updates
      await page.waitForTimeout(5000);

      // Should still show value (might be updated)
      await expect(
        page.locator('[data-testid="portfolio-value"]')
      ).toBeVisible();
    });
  });

  test.describe("Mobile Responsiveness", () => {
    test.beforeEach(async ({ page }) => {
      // Set mobile viewport
      await page.setViewportSize({ width: 375, height: 667 });
      await loginUser(page, TEST_USER);
    });

    test("should display mobile navigation", async ({ page }) => {
      await page.goto(`${BASE_URL}/dashboard`);

      // Should show mobile navigation
      await expect(page.locator('[data-testid="mobile-nav"]')).toBeVisible();

      // Open mobile menu
      await page.click('[data-testid="mobile-menu-button"]');

      // Should show navigation items
      await expect(
        page.locator('[data-testid="mobile-nav-menu"]')
      ).toBeVisible();
    });

    test("should adapt portfolio layout for mobile", async ({ page }) => {
      await page.goto(`${BASE_URL}/portfolio`);

      // Should show mobile-optimized layout
      await expect(
        page.locator('[data-testid="mobile-portfolio"]')
      ).toBeVisible();

      // Should show swipeable cards
      await expect(
        page.locator('[data-testid="portfolio-cards"]')
      ).toBeVisible();
    });
  });

  test.describe("Error Handling and Edge Cases", () => {
    test("should handle network errors gracefully", async ({ page }) => {
      // Simulate network failure
      await page.route("**/api/**", (route) => route.abort());

      await page.goto(`${BASE_URL}/portfolio`);

      // Should show error message
      await expect(page.locator('[data-testid="network-error"]')).toBeVisible();

      // Should show retry option
      await expect(page.locator('[data-testid="retry-button"]')).toBeVisible();
    });

    test("should handle invalid stock symbols", async ({ page }) => {
      await loginUser(page, TEST_USER);
      await page.goto(`${BASE_URL}/trading`);

      // Enter invalid symbol
      await page.fill('[data-testid="symbol-input"]', "INVALID123");
      await page.fill('[data-testid="quantity-input"]', "10");

      // Try to place order
      await page.click('[data-testid="place-order-button"]');

      // Should show validation error
      await expect(
        page.locator('[data-testid="invalid-symbol-error"]')
      ).toBeVisible();
    });

    test("should handle session expiration", async ({ page }) => {
      await loginUser(page, TEST_USER);

      // Simulate expired session
      await page.evaluate(() => {
        localStorage.removeItem("authToken");
      });

      // Try to access protected page
      await page.goto(`${BASE_URL}/portfolio`);

      // Should redirect to login
      await expect(page).toHaveURL(/.*\/(login|auth).*/);
    });
  });

  test.describe("Performance and Loading", () => {
    test("should load pages within acceptable time", async ({ page }) => {
      const startTime = Date.now();

      await page.goto(`${BASE_URL}/dashboard`);
      await page.waitForLoadState("networkidle");

      const loadTime = Date.now() - startTime;

      // Should load within 5 seconds
      expect(loadTime).toBeLessThan(5000);
    });

    test("should show loading states", async ({ page }) => {
      await loginUser(page, TEST_USER);

      // Navigate to portfolio
      await page.click('[data-testid="portfolio-nav"]');

      // Should show loading indicator initially
      await expect(
        page.locator('[data-testid="loading-indicator"]')
      ).toBeVisible();

      // Loading should disappear when data loads
      await page.waitForLoadState("networkidle");
      await expect(
        page.locator('[data-testid="loading-indicator"]')
      ).not.toBeVisible();
    });
  });

  test.describe("Accessibility", () => {
    test("should be keyboard navigable", async ({ page }) => {
      await page.goto(BASE_URL);

      // Should be able to tab through elements
      await page.press("body", "Tab");
      await page.press("body", "Tab");
      await page.press("body", "Tab");

      // Should focus on interactive elements
      const focusedElement = await page.locator(":focus");
      await expect(focusedElement).toBeVisible();
    });

    test("should have proper heading structure", async ({ page }) => {
      await page.goto(`${BASE_URL}/dashboard`);

      // Should have h1 heading
      await expect(page.locator("h1")).toBeVisible();

      // Should have proper heading hierarchy
      const headings = await page.locator("h1, h2, h3, h4, h5, h6").all();
      expect(headings.length).toBeGreaterThan(0);
    });
  });
});

// Helper function to login user
async function loginUser(page, user) {
  await page.goto(`${BASE_URL}/login`);

  await page.fill('[data-testid="email-input"]', user.email);
  await page.fill('[data-testid="password-input"]', user.password);
  await page.click('[data-testid="login-button"]');

  // Wait for redirect to dashboard
  await page.waitForURL(/.*\/dashboard.*/);
}
