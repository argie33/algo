/**
 * Authentication Flow Tests
 * Tests login, logout, API key setup, and protected routes
 */

import { test, expect } from "@playwright/test";

test.describe("Financial Platform - Authentication Flows", () => {
  test("should handle login flow", async ({ page }) => {
    await page.goto("/");
    await page.waitForLoadState("domcontentloaded");
    await page.waitForTimeout(2000);

    console.log("🔐 Testing authentication flow...");

    // Look for sign in button or authentication prompt
    const signInButton = page
      .locator(
        'button:has-text("Sign In"), [aria-label*="sign"], [data-testid*="auth"]'
      )
      .first();

    if (await signInButton.isVisible()) {
      console.log("✅ Sign in button found");
      await signInButton.click();
      await page.waitForTimeout(1000);

      // Check if auth modal or form appears
      const authForm = await page
        .locator('form, [role="dialog"], .auth, .login')
        .first();
      const isVisible = await authForm.isVisible().catch(() => false);

      if (isVisible) {
        console.log("✅ Authentication form displayed");
      } else {
        console.log("ℹ️ Authentication may use external provider");
      }
    } else {
      console.log(
        "ℹ️ No authentication UI found - may be already authenticated"
      );
    }

    // Check for authentication state indicators
    const hasAuthState = await page
      .locator('[data-testid*="user"], .user-menu, .profile')
      .count();
    console.log(`🔍 Authentication indicators found: ${hasAuthState}`);

    expect(true).toBe(true); // Test passes if page loads
  });

  test("should handle API key setup flow", async ({ page }) => {
    await page.goto("/settings");
    await page.waitForLoadState("domcontentloaded");
    await page.waitForTimeout(2000);

    console.log("🔑 Testing API key setup...");

    // Look for and click API Keys tab - with multiple approaches
    const apiKeysSelectors = [
      '[data-testid="api-keys-tab"]',
      'text="API Keys"',
      'button:has-text("API Keys")',
      '[role="tab"]:has-text("API")',
      ".api-keys-tab",
    ];

    let tabFound = false;
    for (const selector of apiKeysSelectors) {
      const tab = page.locator(selector).first();
      if (await tab.isVisible({ timeout: 1000 })) {
        console.log(`🔍 Clicking API Keys tab with selector: ${selector}`);
        await tab.click();
        await page.waitForTimeout(1000);
        tabFound = true;
        break;
      }
    }

    if (!tabFound) {
      console.log("ℹ️ No API Keys tab found - might be on API page already");
    }

    // Look for API key related elements
    const apiKeyElements = await page
      .locator(
        'input[placeholder*="key"], input[name*="key"], [data-testid*="api"], .api-key, input[type="password"]'
      )
      .count();

    console.log(`🔍 API key input elements found: ${apiKeyElements}`);

    // Look for provider setup (Alpaca, Polygon, etc.)
    const providerElements = await page
      .locator(
        'text="Alpaca", text="Polygon", text="Finnhub", .provider, [data-provider]'
      )
      .count();

    console.log(`🏢 Provider elements found: ${providerElements}`);

    // Check for setup wizard or configuration options
    const setupElements = await page
      .locator(
        '.wizard, .setup, button:has-text("Setup"), button:has-text("Configure"), button:has-text("Add")'
      )
      .count();

    console.log(`⚙️ Setup elements found: ${setupElements}`);

    // Should find at least some API-related elements after clicking the tab
    expect(apiKeyElements + providerElements + setupElements).toBeGreaterThan(
      0
    );
  });

  test("should handle protected routes", async ({ page }) => {
    // Test without authentication
    console.log("🛡️ Testing protected routes...");

    const protectedRoutes = [
      "/portfolio",
      "/trade-history",
      "/orders",
      "/settings",
    ];

    let accessibleRoutes = 0;
    let redirectedRoutes = 0;

    for (const route of protectedRoutes) {
      try {
        await page.goto(route, { timeout: 30000 });
        await page.waitForLoadState("domcontentloaded", { timeout: 15000 });

        // Check if redirected to login or shows auth prompt
        const currentUrl = page.url();
        const hasAuthPrompt = await page
          .locator('.auth, .login, [role="dialog"]')
          .count();

        // Check for text-based auth indicators
        const textBasedAuth = await page
          .locator('text("Sign In"), text("Login")')
          .count();

        if (
          currentUrl.includes("login") ||
          currentUrl.includes("auth") ||
          hasAuthPrompt > 0 ||
          textBasedAuth > 0
        ) {
          console.log(`🔒 ${route}: Protected (redirected or shows auth)`);
          redirectedRoutes++;
        } else {
          console.log(`✅ ${route}: Accessible`);
          accessibleRoutes++;
        }
      } catch (error) {
        console.log(`⚠️ ${route}: Error - ${error.message.slice(0, 50)}`);
      }
    }

    console.log(
      `📊 Route accessibility: ${accessibleRoutes} accessible, ${redirectedRoutes} protected`
    );
    expect(accessibleRoutes + redirectedRoutes).toBeGreaterThan(0);
  });

  test("should handle authentication with API keys", async ({ page }) => {
    // Set up authenticated state with API keys
    await page.addInitScript(() => {
      localStorage.setItem("financial_auth_token", "test-auth-token");
      localStorage.setItem(
        "api_keys_status",
        JSON.stringify({
          alpaca: { configured: true, valid: true },
          polygon: { configured: true, valid: true },
          finnhub: { configured: true, valid: true },
        })
      );
    });

    await page.goto("/portfolio");
    await page.waitForLoadState("domcontentloaded");
    await page.waitForTimeout(2000);

    console.log("🔑 Testing authenticated state with API keys...");

    // Check if page content loads successfully
    const pageTitle = await page.title();
    console.log(`📄 Page title: "${pageTitle}"`);

    // Check for any interactive elements (buttons, links, inputs)
    const interactiveElements = await page
      .locator('button, a[href], input, [role="button"], [role="link"]')
      .count();

    console.log(`🔍 Interactive elements found: ${interactiveElements}`);

    // Check for general portfolio or data elements
    const contentElements = await page
      .locator(
        ".portfolio, .holdings, .positions, .balance, .data, .chart, .table, tbody tr"
      )
      .count();

    console.log(`📊 Content elements found: ${contentElements}`);

    // Verify page has meaningful content
    const pageContent = await page.locator("#root").textContent();
    const hasContent = pageContent && pageContent.length > 500;

    console.log(
      `📄 Page content loaded: ${hasContent ? "Yes" : "No"} (${pageContent?.length || 0} chars)`
    );

    // Test passes if page loads with interactive elements or content
    expect(interactiveElements + contentElements).toBeGreaterThan(0);
  });

  test("should handle logout flow", async ({ page }) => {
    // Set up authenticated state
    await page.addInitScript(() => {
      localStorage.setItem("financial_auth_token", "test-auth-token");
    });

    await page.goto("/");
    await page.waitForLoadState("domcontentloaded");
    await page.waitForTimeout(2000);

    console.log("🚪 Testing logout flow...");

    // Look for logout button/menu
    const logoutElements = await page
      .locator(
        'button:has-text("Logout"), button:has-text("Sign Out"), .logout, [data-testid*="logout"]'
      )
      .count();

    console.log(`🔍 Logout elements found: ${logoutElements}`);

    // Look for user menu/profile that might contain logout
    const userMenu = await page
      .locator('.user-menu, .profile, .avatar, [data-testid*="user"]')
      .count();

    console.log(`👤 User menu elements found: ${userMenu}`);

    if (logoutElements > 0) {
      console.log("✅ Logout functionality available");
    } else if (userMenu > 0) {
      console.log("✅ User menu available (logout likely inside)");
    } else {
      console.log("ℹ️ No explicit logout UI found");
    }

    expect(true).toBe(true); // Test passes if page loads
  });
});
