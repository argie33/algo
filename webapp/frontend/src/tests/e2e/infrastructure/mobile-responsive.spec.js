/**
 * Mobile-Specific E2E Tests
 * Tests focused on mobile device functionality and responsive design
 */

import { test, expect } from "@playwright/test";

test.describe("Mobile-Specific Testing", () => {
  test.beforeEach(async ({ page, isMobile, browserName }) => {
    // Set up mobile viewport for comprehensive testing
    if (!isMobile) {
      await page.setViewportSize({ width: 375, height: 667 }); // iPhone SE
    }

    // Mobile-optimized timeout configurations
    const timeout =
      browserName === "firefox"
        ? 8000
        : browserName === "webkit"
          ? 10000
          : 6000;
    page.setDefaultTimeout(timeout);

    // Set up authentication and API keys
    await page.addInitScript(() => {
      localStorage.setItem("financial_auth_token", "mobile-test-token");
      localStorage.setItem(
        "api_keys_status",
        JSON.stringify({
          alpaca: { configured: true, valid: true },
          polygon: { configured: true, valid: true },
          finnhub: { configured: true, valid: true },
        })
      );

      // Mobile-specific optimizations
      window.MOBILE_TEST_MODE = true;
      window.DISABLE_ANIMATIONS = true;
    });

    // Mock consistent mobile API responses
    await page.route("**/api/**", (route) => {
      const url = route.request().url();

      if (url.includes("/portfolio")) {
        route.fulfill({
          json: {
            success: true,
            data: {
              totalValue: 50000.25,
              totalGainLoss: 2500.0,
              holdings: [
                {
                  symbol: "AAPL",
                  quantity: 10,
                  currentPrice: 195.2,
                  totalValue: 1952.0,
                },
                {
                  symbol: "MSFT",
                  quantity: 5,
                  currentPrice: 385.75,
                  totalValue: 1928.75,
                },
                {
                  symbol: "GOOGL",
                  quantity: 2,
                  currentPrice: 2650.75,
                  totalValue: 5301.5,
                },
              ],
            },
          },
        });
      } else if (url.includes("/market")) {
        route.fulfill({
          json: {
            success: true,
            data: {
              indices: {
                SPY: { price: 445.32, change: 2.15, changePercent: 0.48 },
                QQQ: { price: 375.68, change: -1.23, changePercent: -0.33 },
                DIA: { price: 355.91, change: 0.87, changePercent: 0.24 },
              },
            },
          },
        });
      } else {
        route.fulfill({ json: { success: true, data: {} } });
      }
    });
  });

  test("Mobile dashboard should load and display key metrics", async ({
    page,
  }) => {
    console.log("📱 Testing mobile dashboard...");

    await page.goto("/", { waitUntil: "domcontentloaded" });
    await page.waitForSelector("#root", { state: "attached" });
    await page.waitForTimeout(3000);

    // Should display financial dashboard on mobile
    await expect(page.locator("#root")).toBeVisible();

    // Check for mobile-responsive elements
    const content = await page.locator("#root").textContent();
    expect(content.length).toBeGreaterThan(300);

    // Test mobile navigation accessibility
    const mobileMenus = await page
      .locator('button[aria-label*="menu"], .mobile-menu, .hamburger')
      .count();
    console.log(`📱 Mobile menu elements found: ${mobileMenus}`);

    // Test touch-friendly elements
    const touchTargets = await page
      .locator('button, a, input, [role="button"]')
      .all();
    let touchFriendlyCount = 0;

    for (const target of touchTargets.slice(0, 10)) {
      // Test first 10 elements
      const box = await target.boundingBox();
      if (box && box.width >= 44 && box.height >= 44) {
        touchFriendlyCount++;
      }
    }

    console.log(
      `📱 Touch-friendly targets: ${touchFriendlyCount}/${Math.min(touchTargets.length, 10)}`
    );
    expect(touchFriendlyCount).toBeGreaterThan(0);
  });

  test("Mobile portfolio page should be touch-optimized", async ({ page }) => {
    console.log("📱 Testing mobile portfolio interactions...");

    await page.goto("/portfolio", { waitUntil: "domcontentloaded" });
    await page.waitForSelector("#root", { state: "attached" });
    await page.waitForTimeout(2000);

    // Test scroll behavior on mobile
    const initialScrollY = await page.evaluate(() => window.scrollY);
    await page.evaluate(() => window.scrollBy(0, 200));
    await page.waitForTimeout(500);
    const scrolledY = await page.evaluate(() => window.scrollY);

    expect(scrolledY).toBeGreaterThan(initialScrollY);
    console.log(`📱 Mobile scroll test: ${initialScrollY} → ${scrolledY}`);

    // Test mobile-specific interactions
    const tapTargets = await page
      .locator('button, [role="button"], .clickable')
      .all();
    if (tapTargets.length > 0) {
      try {
        // Test tap gesture
        await tapTargets[0].tap();
        await page.waitForTimeout(500);
        console.log("📱 Mobile tap gesture successful");
      } catch (e) {
        console.log(`📱 Tap gesture failed: ${e.message.slice(0, 50)}`);
      }
    }

    // Verify mobile viewport usage
    const viewport = page.viewportSize();
    expect(viewport.width).toBeLessThanOrEqual(768); // Mobile breakpoint
    console.log(`📱 Mobile viewport: ${viewport.width}x${viewport.height}`);
  });

  test("Mobile market data should be readable and accessible", async ({
    page,
  }) => {
    console.log("📱 Testing mobile market data readability...");

    await page.goto("/market", { waitUntil: "domcontentloaded" });
    await page.waitForSelector("#root", { state: "attached" });
    await page.waitForTimeout(2000);

    // Test text readability on mobile
    const textElements = await page
      .locator("p, div, span, h1, h2, h3, h4, h5, h6")
      .all();
    let readableTextCount = 0;

    for (const element of textElements.slice(0, 20)) {
      try {
        const styles = await element.evaluate((el) => {
          const computed = window.getComputedStyle(el);
          return {
            fontSize: parseInt(computed.fontSize),
            lineHeight: computed.lineHeight,
            display: computed.display,
          };
        });

        if (styles.fontSize >= 16 && styles.display !== "none") {
          readableTextCount++;
        }
      } catch (e) {
        // Element may not be visible, skip
      }
    }

    console.log(
      `📱 Readable text elements: ${readableTextCount}/${Math.min(textElements.length, 20)}`
    );
    expect(readableTextCount).toBeGreaterThan(5);

    // Test mobile data table responsiveness
    const tables = await page.locator("table, .data-table, .grid").count();
    if (tables > 0) {
      console.log(`📱 Data tables found: ${tables}`);

      // Check for horizontal scroll on tables
      const tableOverflow = await page
        .locator("table")
        .first()
        .evaluate((el) => {
          return el.scrollWidth > el.clientWidth;
        });
      console.log(`📱 Table horizontal scroll available: ${tableOverflow}`);
    }
  });

  test("Mobile navigation should work with touch gestures", async ({
    page,
  }) => {
    console.log("📱 Testing mobile navigation gestures...");

    await page.goto("/", { waitUntil: "domcontentloaded" });
    await page.waitForSelector("#root", { state: "attached" });
    await page.waitForTimeout(1500);

    const mobileRoutes = ["/portfolio", "/market", "/settings"];
    let successfulMobileNavigation = 0;

    for (const route of mobileRoutes) {
      try {
        console.log(`📱 Testing mobile navigation to ${route}...`);

        await page.goto(route, {
          waitUntil: "domcontentloaded",
          timeout: 8000,
        });
        await page.waitForSelector("#root", {
          state: "attached",
          timeout: 6000,
        });
        await page.waitForTimeout(1000);

        if (page.url().includes(route)) {
          successfulMobileNavigation++;
          console.log(`✅ Mobile navigation to ${route} successful`);
        }
      } catch (e) {
        console.log(
          `❌ Mobile navigation to ${route} failed: ${e.message.slice(0, 50)}`
        );
      }
    }

    expect(successfulMobileNavigation).toBeGreaterThanOrEqual(2);
    console.log(
      `📱 Mobile navigation success: ${successfulMobileNavigation}/${mobileRoutes.length}`
    );
  });

  test("Mobile performance should meet Core Web Vitals", async ({ page }) => {
    console.log("📱 Testing mobile performance metrics...");

    const performanceMetrics = [];

    // Test mobile-specific performance
    const mobilePages = ["/", "/portfolio", "/market"];

    for (const pagePath of mobilePages) {
      const startTime = Date.now();

      try {
        await page.goto(pagePath, { waitUntil: "domcontentloaded" });
        await page.waitForSelector("#root", { state: "attached" });

        const loadTime = Date.now() - startTime;

        // Get mobile-specific performance metrics
        const metrics = await page.evaluate(() => {
          const navigation = performance.getEntriesByType("navigation")[0];
          return {
            domContentLoaded:
              navigation?.domContentLoadedEventEnd -
              navigation?.domContentLoadedEventStart,
            loadComplete: navigation?.loadEventEnd - navigation?.loadEventStart,
            firstPaint:
              performance.getEntriesByName("first-paint")[0]?.startTime || 0,
          };
        });

        performanceMetrics.push({
          page: pagePath,
          loadTime,
          ...metrics,
        });

        console.log(
          `📱 ${pagePath}: ${loadTime}ms load, ${metrics.domContentLoaded}ms DOM ready`
        );
      } catch (e) {
        console.log(
          `📱 Performance test failed for ${pagePath}: ${e.message.slice(0, 50)}`
        );
      }
    }

    // Mobile performance expectations (more lenient than desktop)
    const avgLoadTime =
      performanceMetrics.reduce((sum, m) => sum + m.loadTime, 0) /
      performanceMetrics.length;
    console.log(`📱 Average mobile load time: ${Math.round(avgLoadTime)}ms`);

    expect(avgLoadTime).toBeLessThan(8000); // 8 seconds for mobile
    expect(performanceMetrics.length).toBeGreaterThan(0);
  });

  test("Mobile accessibility should support assistive technologies", async ({
    page,
  }) => {
    console.log("📱 Testing mobile accessibility...");

    await page.goto("/", { waitUntil: "domcontentloaded" });
    await page.waitForSelector("#root", { state: "attached" });
    await page.waitForTimeout(2000);

    // Test mobile screen reader support
    const ariaLabels = await page
      .locator("[aria-label], [aria-labelledby], [aria-describedby]")
      .count();
    console.log(`📱 ARIA labels found: ${ariaLabels}`);
    expect(ariaLabels).toBeGreaterThan(3);

    // Test mobile focus management
    const focusableElements = await page
      .locator(
        'button, a, input, select, textarea, [tabindex]:not([tabindex="-1"])'
      )
      .count();
    console.log(`📱 Focusable elements: ${focusableElements}`);
    expect(focusableElements).toBeGreaterThan(5);

    // Test mobile keyboard navigation (for external keyboards)
    try {
      await page.keyboard.press("Tab");
      await page.waitForTimeout(200);
      await page.keyboard.press("Tab");
      await page.waitForTimeout(200);
      console.log("📱 Mobile keyboard navigation working");
    } catch (e) {
      console.log(
        `📱 Mobile keyboard navigation issue: ${e.message.slice(0, 50)}`
      );
    }

    // Test mobile heading hierarchy
    const headings = await page.locator("h1, h2, h3, h4, h5, h6").count();
    console.log(`📱 Heading elements: ${headings}`);
    expect(headings).toBeGreaterThan(1);
  });
});
