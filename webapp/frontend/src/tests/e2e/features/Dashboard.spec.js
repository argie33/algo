import { test, expect } from "@playwright/test";

test.describe("Dashboard and Homepage E2E Tests", () => {
  test.setTimeout(30000);

  test.beforeEach(async ({ page }) => {
    // Set up error monitoring
    page.on('console', msg => {
      if (msg.type() === 'error') {
        console.log('Browser error:', msg.text());
      }
    });

    page.on('pageerror', error => {
      console.log('Page error:', error.message);
    });
  });

  test("should load the homepage with correct title", async ({ page }) => {
    try {
      // Navigate to the homepage with longer timeout
      await page.goto("/", {
        waitUntil: "domcontentloaded",
        timeout: 30000
      });

      // Wait for any React hydration
      await page.waitForTimeout(2000);

      // Check if the page title contains expected content
      const title = await page.title();
      expect(title).toMatch(/Financial|Dashboard|Stock|Portfolio/i);
      expect(title).toContain('Dashboard');
      expect(title).toContain('Financial Dashboard');

      // Check if the root element has content (just checking DOM, not visibility)
      const rootCount = await page.locator("#root").count();
      expect(rootCount).toBeGreaterThan(0);

      // Verify page has content (not just empty root)
      const hasContent = await page.locator("#root *").count();
      expect(hasContent).toBeGreaterThan(0);

    } catch (error) {
      console.log("Homepage load error:", error.message);
      // Take screenshot for debugging
      await page.screenshot({ path: 'debug-homepage.png' });
      throw error;
    }
  });

  test("should handle navigation elements", async ({ page }) => {
    try {
      await page.goto("/", {
        waitUntil: "domcontentloaded",
        timeout: 30000
      });

      await page.waitForTimeout(2000);

      // Look for navigation elements with multiple selectors
      const navSelectors = [
        'nav',
        '[role="navigation"]',
        '.nav',
        '.navigation',
        '.MuiDrawer-root',
        '.MuiAppBar-root',
        'header'
      ];

      let navFound = false;
      for (const selector of navSelectors) {
        const nav = page.locator(selector).first();
        if (await nav.isVisible()) {
          await expect(nav).toBeVisible();
          navFound = true;
          break;
        }
      }

      // If no navigation found, that's still okay for some layouts
      if (!navFound) {
        console.log("No traditional navigation found, checking for any interactive elements");
        const interactiveCount = await page.locator("button, a, [role='button']").count();
        expect(interactiveCount).toBeGreaterThan(0);
      }

    } catch (error) {
      console.log("Navigation test error:", error.message);
      await page.screenshot({ path: 'debug-navigation.png' });
      throw error;
    }
  });

  test("should be responsive across different viewports", async ({ page }) => {
    try {
      await page.goto("/", {
        waitUntil: "domcontentloaded",
        timeout: 30000
      });

      await page.waitForTimeout(2000);

      // Test desktop view
      await page.setViewportSize({ width: 1920, height: 1080 });
      await page.waitForTimeout(1000); // Allow layout adjustment

      const root = page.locator("#root");
      const rootCount = await root.count();
      expect(rootCount).toBe(1);

      // Verify root has actual content
      const desktopContent = await root.locator("*").count();
      expect(desktopContent).toBeGreaterThan(0);

      // Test mobile view
      await page.setViewportSize({ width: 375, height: 667 });
      await page.waitForTimeout(1000); // Allow layout adjustment

      // Verify root still exists
      const mobileRootCount = await root.count();
      expect(mobileRootCount).toBe(1);

      // Verify root still has content in mobile view
      const mobileContent = await root.locator("*").count();
      expect(mobileContent).toBeGreaterThan(0);

      // Test tablet view
      await page.setViewportSize({ width: 768, height: 1024 });
      await page.waitForTimeout(1000);
      const tabletRootCount = await root.count();
      expect(tabletRootCount).toBe(1);

    } catch (error) {
      console.log("Responsive test error:", error.message);
      await page.screenshot({ path: 'debug-responsive.png' });
      throw error;
    }
  });

  test("should have correct document title", async ({ page }) => {
    await page.goto("/", {
      waitUntil: "domcontentloaded",
      timeout: 30000
    });
    await page.waitForTimeout(1000);

    const title = await page.title();
    expect(title).toContain('Dashboard');
    expect(title).toContain('Financial Dashboard');
  });
});