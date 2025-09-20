/**
 * Mobile Responsiveness Test Suite
 * Comprehensive mobile and responsive design testing
 */

import { test, expect, devices } from '@playwright/test';

// Device configurations for testing
const testDevices = [
  { name: 'iPhone 12', ...devices['iPhone 12'] },
  { name: 'iPad', ...devices['iPad'] },
  { name: 'Samsung Galaxy S21', ...devices['Galaxy S21'] },
  { name: 'Desktop', viewport: { width: 1920, height: 1080 } }
];

test.describe('Mobile Responsiveness', () => {
  test.beforeEach(async ({ page }) => {
    // Set up mobile testing environment
    await page.addInitScript(() => {
      // Mock touch events for better mobile testing
      window.__TOUCH_EVENTS__ = [];

      ['touchstart', 'touchmove', 'touchend'].forEach(eventType => {
        document.addEventListener(eventType, (e) => {
          window.__TOUCH_EVENTS__.push({
            type: eventType,
            touches: e.touches.length,
            timestamp: Date.now()
          });
        });
      });

      // Mock device orientation
      window.__ORIENTATION_CHANGES__ = [];
      window.addEventListener('orientationchange', () => {
        window.__ORIENTATION_CHANGES__.push({
          orientation: window.orientation,
          timestamp: Date.now()
        });
      });
    });
  });

  for (const device of testDevices) {
    test(`should be responsive on ${device.name}`, async ({ browser }) => {
      const context = await browser.newContext({
        ...device,
        locale: 'en-US'
      });
      const page = await context.newPage();

      try {
        await page.goto('/');
        await page.waitForLoadState('networkidle');

        // Test basic layout responsiveness
        const viewport = page.viewportSize();
        const isMobile = viewport.width < 768;
        const _isTablet = viewport.width >= 768 && viewport.width < 1024;

        // Check navigation is appropriate for screen size
        if (isMobile) {
          // Mobile should have hamburger menu or collapsed navigation
          const mobileNav = await page.locator('.mobile-menu, .hamburger, [aria-label*="menu"]').count();
          const fullNav = await page.locator('nav ul li').count();

          expect(mobileNav > 0 || fullNav <= 3).toBe(true);
        } else {
          // Desktop should have full navigation
          const fullNav = await page.locator('nav ul li, nav a').count();
          expect(fullNav).toBeGreaterThan(0);
        }

        // Test content readability
        const headings = await page.locator('h1, h2, h3').all();
        for (const heading of headings.slice(0, 3)) {
          if (await heading.isVisible()) {
            const fontSize = await heading.evaluate(el =>
              window.getComputedStyle(el).fontSize
            );
            const fontSizeNum = parseInt(fontSize);

            // Mobile headings should be large enough to read
            if (isMobile) {
              expect(fontSizeNum).toBeGreaterThan(18);
            }
          }
        }

        // Test touch targets on mobile
        if (isMobile) {
          const buttons = await page.locator('button, a, [role="button"]').all();
          for (const button of buttons.slice(0, 5)) {
            if (await button.isVisible()) {
              const box = await button.boundingBox();
              if (box) {
                // Touch targets should be at least 44px
                expect(Math.min(box.width, box.height)).toBeGreaterThan(40);
              }
            }
          }
        }

        // Test horizontal scrolling
        const bodyWidth = await page.evaluate(() => document.body.scrollWidth);
        const viewportWidth = viewport.width;

        // Should not have horizontal scroll
        expect(bodyWidth).toBeLessThanOrEqual(viewportWidth + 5); // 5px tolerance

      } finally {
        await context.close();
      }
    });
  }

  test('should handle mobile navigation patterns', async ({ page }) => {
    // Test on mobile viewport
    await page.setViewportSize({ width: 375, height: 667 });
    await page.goto('/');
    await page.waitForLoadState('networkidle');

    // Test hamburger menu
    const hamburger = page.locator('.hamburger, .mobile-menu-toggle, [aria-label*="menu"]').first();

    if (await hamburger.isVisible()) {
      // Menu should be closed initially
      const menu = page.locator('.mobile-menu, .nav-menu');
      const isInitiallyClosed = await menu.evaluate(el => {
        const style = window.getComputedStyle(el);
        return style.display === 'none' ||
               style.visibility === 'hidden' ||
               style.opacity === '0' ||
               el.getAttribute('aria-hidden') === 'true';
      });

      expect(isInitiallyClosed).toBe(true);

      // Open menu
      await hamburger.click();
      await page.waitForTimeout(500);

      const isOpen = await menu.evaluate(el => {
        const style = window.getComputedStyle(el);
        return style.display !== 'none' &&
               style.visibility !== 'hidden' &&
               style.opacity !== '0' &&
               el.getAttribute('aria-hidden') !== 'true';
      });

      expect(isOpen).toBe(true);

      // Test menu links
      const menuLinks = await menu.locator('a, button').all();
      expect(menuLinks.length).toBeGreaterThan(0);

      // Close menu by clicking outside
      await page.click('body', { position: { x: 10, y: 10 } });
      await page.waitForTimeout(500);

      const isClosedAfterOutsideClick = await menu.evaluate(el => {
        const style = window.getComputedStyle(el);
        return style.display === 'none' ||
               style.visibility === 'hidden' ||
               style.opacity === '0' ||
               el.getAttribute('aria-hidden') === 'true';
      });

      expect(isClosedAfterOutsideClick).toBe(true);
    }
  });

  test('should handle touch interactions properly', async ({ page }) => {
    await page.setViewportSize({ width: 375, height: 667 });
    await page.goto('/dashboard');
    await page.waitForLoadState('networkidle');

    // Test touch events
    const touchableElements = await page.locator('button, a, [role="button"], .clickable').all();

    for (const element of touchableElements.slice(0, 5)) {
      if (await element.isVisible()) {
        // Test touch start
        await element.dispatchEvent('touchstart', {
          touches: [{ clientX: 50, clientY: 50 }]
        });
        await page.waitForTimeout(100);

        // Test touch end
        await element.dispatchEvent('touchend', {
          touches: []
        });
        await page.waitForTimeout(100);
      }
    }

    // Verify touch events were captured
    const touchEvents = await page.evaluate(() => window.__TOUCH_EVENTS__);
    expect(touchEvents.length).toBeGreaterThan(0);
  });

  test('should handle swipe gestures', async ({ page }) => {
    await page.setViewportSize({ width: 375, height: 667 });
    await page.goto('/portfolio');
    await page.waitForLoadState('networkidle');

    // Look for swipeable elements
    const carousel = page.locator('.carousel, .swiper, .slider').first();
    const table = page.locator('table, .table-container').first();

    if (await carousel.isVisible()) {
      // Test swipe on carousel
      const box = await carousel.boundingBox();
      if (box) {
        // Swipe left
        await page.mouse.move(box.x + box.width * 0.8, box.y + box.height / 2);
        await page.mouse.down();
        await page.mouse.move(box.x + box.width * 0.2, box.y + box.height / 2);
        await page.mouse.up();
        await page.waitForTimeout(500);

        // Swipe right
        await page.mouse.move(box.x + box.width * 0.2, box.y + box.height / 2);
        await page.mouse.down();
        await page.mouse.move(box.x + box.width * 0.8, box.y + box.height / 2);
        await page.mouse.up();
        await page.waitForTimeout(500);
      }
    }

    if (await table.isVisible()) {
      // Test horizontal scrolling on table
      const box = await table.boundingBox();
      if (box) {
        await page.mouse.move(box.x + box.width / 2, box.y + box.height / 2);
        await page.mouse.down();
        await page.mouse.move(box.x + box.width / 2 - 100, box.y + box.height / 2);
        await page.mouse.up();
        await page.waitForTimeout(500);
      }
    }
  });

  test('should adapt forms for mobile input', async ({ page }) => {
    await page.setViewportSize({ width: 375, height: 667 });
    await page.goto('/settings');
    await page.waitForLoadState('networkidle');

    const inputs = await page.locator('input, textarea, select').all();

    for (const input of inputs.slice(0, 5)) {
      if (await input.isVisible()) {
        const inputType = await input.getAttribute('type');
        const inputMode = await input.getAttribute('inputmode');
        const _autocomplete = await input.getAttribute('autocomplete');

        // Check appropriate input types for mobile
        const isEmail = inputType === 'email' || await input.getAttribute('name') === 'email';
        const isPhone = inputType === 'tel' || await input.getAttribute('name')?.includes('phone');
        const isNumber = inputType === 'number' || inputMode === 'numeric';

        if (isEmail) {
          expect(inputType).toBe('email');
        }
        if (isPhone) {
          expect(inputType).toBe('tel');
        }
        if (isNumber) {
          expect(['number', 'tel'].includes(inputType) || inputMode === 'numeric').toBe(true);
        }

        // Test touch interaction
        await input.focus();
        await page.waitForTimeout(200);

        // Check if virtual keyboard consideration
        const focused = await input.evaluate(el => el === document.activeElement);
        expect(focused).toBe(true);

        await input.fill('test');
        const value = await input.inputValue();
        expect(value).toBe('test');

        await input.clear();
      }
    }
  });

  test('should handle orientation changes', async ({ page }) => {
    // Start in portrait
    await page.setViewportSize({ width: 375, height: 667 });
    await page.goto('/dashboard');
    await page.waitForLoadState('networkidle');

    // Take screenshot in portrait
    const portraitLayout = await page.evaluate(() => {
      return {
        width: window.innerWidth,
        height: window.innerHeight,
        orientation: window.innerWidth < window.innerHeight ? 'portrait' : 'landscape'
      };
    });

    expect(portraitLayout.orientation).toBe('portrait');

    // Switch to landscape
    await page.setViewportSize({ width: 667, height: 375 });
    await page.waitForTimeout(1000);

    const landscapeLayout = await page.evaluate(() => {
      return {
        width: window.innerWidth,
        height: window.innerHeight,
        orientation: window.innerWidth < window.innerHeight ? 'portrait' : 'landscape'
      };
    });

    expect(landscapeLayout.orientation).toBe('landscape');

    // Check that layout adapts appropriately
    const navigation = page.locator('nav, .navigation');
    if (await navigation.isVisible()) {
      const navHeight = await navigation.evaluate(el => el.offsetHeight);
      // Navigation should be more compact in landscape
      expect(navHeight).toBeLessThan(100);
    }
  });

  test('should optimize performance for mobile devices', async ({ page }) => {
    await page.setViewportSize({ width: 375, height: 667 });

    // Simulate slower mobile network
    await page.route('**/*', async route => {
      await new Promise(resolve => setTimeout(resolve, 100));
      await route.continue();
    });

    const startTime = Date.now();
    await page.goto('/');
    await page.waitForLoadState('networkidle');
    const loadTime = Date.now() - startTime;

    // Mobile should load within reasonable time even with slow network
    expect(loadTime).toBeLessThan(8000);

    // Check for mobile optimizations
    const images = await page.locator('img').all();
    let optimizedImages = 0;

    for (const img of images.slice(0, 5)) {
      if (await img.isVisible()) {
        const src = await img.getAttribute('src');
        const srcset = await img.getAttribute('srcset');
        const loading = await img.getAttribute('loading');

        // Check for responsive images
        if (srcset || src?.includes('w_') || src?.includes('mobile')) {
          optimizedImages++;
        }

        // Check for lazy loading
        if (loading === 'lazy') {
          optimizedImages++;
        }
      }
    }

    // Should have some mobile optimizations
    expect(optimizedImages).toBeGreaterThan(0);
  });

  test('should handle mobile-specific features', async ({ page }) => {
    await page.setViewportSize({ width: 375, height: 667 });
    await page.goto('/');
    await page.waitForLoadState('networkidle');

    // Test pull-to-refresh if available
    const pullToRefresh = page.locator('[data-pull-refresh], .pull-refresh');
    if (await pullToRefresh.count() > 0) {
      // Simulate pull gesture
      await page.mouse.move(187, 100);
      await page.mouse.down();
      await page.mouse.move(187, 200);
      await page.waitForTimeout(500);
      await page.mouse.up();
      await page.waitForTimeout(1000);
    }

    // Test infinite scroll if available
    const scrollContainer = page.locator('.infinite-scroll, .scroll-container').first();
    if (await scrollContainer.isVisible()) {
      // Scroll to bottom
      await scrollContainer.evaluate(el => {
        el.scrollTop = el.scrollHeight;
      });
      await page.waitForTimeout(2000);
    }

    // Test sticky headers
    const stickyHeaders = await page.locator('.sticky, [style*="position: sticky"]').all();
    for (const header of stickyHeaders) {
      if (await header.isVisible()) {
        const position = await header.evaluate(el =>
          window.getComputedStyle(el).position
        );
        expect(['sticky', 'fixed'].includes(position)).toBe(true);
      }
    }
  });

  test('should maintain accessibility on mobile', async ({ page }) => {
    await page.setViewportSize({ width: 375, height: 667 });
    await page.goto('/');
    await page.waitForLoadState('networkidle');

    // Test focus management
    await page.keyboard.press('Tab');
    const focusedElement = await page.evaluate(() => document.activeElement?.tagName);
    expect(['BUTTON', 'A', 'INPUT'].includes(focusedElement)).toBe(true);

    // Test ARIA labels on mobile navigation
    const mobileButtons = await page.locator('button[aria-label], [role="button"][aria-label]').all();
    for (const button of mobileButtons.slice(0, 3)) {
      if (await button.isVisible()) {
        const ariaLabel = await button.getAttribute('aria-label');
        expect(ariaLabel).toBeTruthy();
        expect(ariaLabel.length).toBeGreaterThan(2);
      }
    }

    // Test minimum touch target sizes
    const interactiveElements = await page.locator('button, a, input, [role="button"]').all();
    let adequateTouchTargets = 0;

    for (const element of interactiveElements.slice(0, 10)) {
      if (await element.isVisible()) {
        const box = await element.boundingBox();
        if (box && Math.min(box.width, box.height) >= 44) {
          adequateTouchTargets++;
        }
      }
    }

    // Most interactive elements should have adequate touch targets
    expect(adequateTouchTargets).toBeGreaterThan(interactiveElements.length * 0.7);
  });

  test('should handle mobile data tables', async ({ page }) => {
    await page.setViewportSize({ width: 375, height: 667 });
    await page.goto('/portfolio');
    await page.waitForLoadState('networkidle');

    const tables = await page.locator('table').all();

    for (const table of tables) {
      if (await table.isVisible()) {
        const tableContainer = table.locator('..').first();

        // Check if table is scrollable horizontally
        const isScrollable = await tableContainer.evaluate(el => {
          return el.scrollWidth > el.clientWidth;
        });

        if (isScrollable) {
          // Test horizontal scrolling
          await tableContainer.evaluate(el => {
            el.scrollLeft = 100;
          });

          const scrollLeft = await tableContainer.evaluate(el => el.scrollLeft);
          expect(scrollLeft).toBeGreaterThan(0);
        }

        // Check for mobile table adaptations
        const tableStyle = await table.evaluate(el => window.getComputedStyle(el));
        const hasResponsiveFeatures =
          tableStyle.display === 'block' ||
          tableStyle.overflowX === 'auto' ||
          tableStyle.overflowX === 'scroll';

        expect(hasResponsiveFeatures).toBe(true);
      }
    }
  });

  test('should handle mobile charts and visualizations', async ({ page }) => {
    await page.setViewportSize({ width: 375, height: 667 });
    await page.goto('/dashboard');
    await page.waitForLoadState('networkidle');
    await page.waitForTimeout(3000);

    const charts = await page.locator('.chart, canvas, svg[class*="chart"]').all();

    for (const chart of charts.slice(0, 3)) {
      if (await chart.isVisible()) {
        const box = await chart.boundingBox();

        if (box) {
          // Chart should fit within mobile viewport
          expect(box.width).toBeLessThanOrEqual(375);

          // Chart should maintain reasonable aspect ratio
          const aspectRatio = box.width / box.height;
          expect(aspectRatio).toBeGreaterThan(0.5);
          expect(aspectRatio).toBeLessThan(3);

          // Test touch interaction on chart
          await chart.tap({ position: { x: box.width / 2, y: box.height / 2 } });
          await page.waitForTimeout(500);
        }
      }
    }
  });
});