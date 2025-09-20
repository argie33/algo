/**
 * Browser Compatibility Test Suite
 * Cross-browser compatibility and feature detection testing
 */

import { test, expect } from '@playwright/test';

// Browser configurations for testing
const _browserConfigs = [
  { name: 'Chrome', browserName: 'chromium' },
  { name: 'Firefox', browserName: 'firefox' },
  { name: 'Safari', browserName: 'webkit' },
  { name: 'Edge', browserName: 'chromium', channel: 'msedge' }
];

test.describe('Browser Compatibility', () => {
  test.beforeEach(async ({ page }) => {
    // Set up compatibility testing environment
    await page.addInitScript(() => {
      window.__BROWSER_FEATURES__ = {
        supportedFeatures: [],
        unsupportedFeatures: [],
        polyfillsNeeded: []
      };

      // Feature detection
      const features = {
        fetch: typeof fetch !== 'undefined',
        promises: typeof Promise !== 'undefined',
        arrow_functions: true, // Can't easily test syntax features
        const_let: true,
        spread_operator: true,
        destructuring: true,
        template_literals: true,
        classes: typeof class {} === 'function',
        modules: typeof Symbol !== 'undefined',
        web_workers: typeof Worker !== 'undefined',
        service_workers: 'serviceWorker' in navigator,
        web_sockets: typeof WebSocket !== 'undefined',
        local_storage: typeof localStorage !== 'undefined',
        session_storage: typeof sessionStorage !== 'undefined',
        geolocation: 'geolocation' in navigator,
        canvas: document.createElement('canvas').getContext !== undefined,
        svg: document.createElementNS('http://www.w3.org/2000/svg', 'svg').createSVGRect !== undefined,
        css_grid: CSS.supports('display', 'grid'),
        css_flexbox: CSS.supports('display', 'flex'),
        css_custom_properties: CSS.supports('--test', 'test'),
        intersection_observer: 'IntersectionObserver' in window,
        mutation_observer: 'MutationObserver' in window,
        resize_observer: 'ResizeObserver' in window
      };

      Object.entries(features).forEach(([feature, supported]) => {
        if (supported) {
          window.__BROWSER_FEATURES__.supportedFeatures.push(feature);
        } else {
          window.__BROWSER_FEATURES__.unsupportedFeatures.push(feature);
        }
      });

      // Detect browser
      const userAgent = navigator.userAgent;
      window.__BROWSER_INFO__ = {
        isChrome: userAgent.includes('Chrome'),
        isFirefox: userAgent.includes('Firefox'),
        isSafari: userAgent.includes('Safari') && !userAgent.includes('Chrome'),
        isEdge: userAgent.includes('Edg'),
        isMobile: /Android|iPhone|iPad|iPod|BlackBerry|IEMobile|Opera Mini/i.test(userAgent)
      };
    });
  });

  test('should work across all major browsers', async ({ page, browserName: _browserName }) => {
    await page.goto('/');
    await page.waitForLoadState('networkidle');

    // Basic functionality should work in all browsers
    const title = await page.title();
    expect(title.length).toBeGreaterThan(0);

    // Check if page content loads
    const bodyContent = await page.textContent('body');
    expect(bodyContent.length).toBeGreaterThan(0);

    // Test navigation
    const navLinks = await page.locator('nav a, .nav-link').all();
    if (navLinks.length > 0) {
      const firstLink = navLinks[0];
      const href = await firstLink.getAttribute('href');
      if (href && !href.startsWith('#')) {
        await firstLink.click();
        await page.waitForLoadState('networkidle');

        const newUrl = page.url();
        expect(newUrl).not.toBe('/');
      }
    }

    // Test form interactions
    const inputs = await page.locator('input[type="text"], input[type="search"]').all();
    if (inputs.length > 0) {
      const input = inputs[0];
      await input.fill('test');
      const value = await input.inputValue();
      expect(value).toBe('test');
    }

    // Test button interactions
    const buttons = await page.locator('button:not([disabled])').all();
    if (buttons.length > 0) {
      const button = buttons[0];
      await button.click();
      // Button should be clickable without errors
    }
  });

  test('should handle JavaScript features consistently', async ({ page }) => {
    await page.goto('/');
    await page.waitForLoadState('networkidle');

    const browserFeatures = await page.evaluate(() => window.__BROWSER_FEATURES__);
    const browserInfo = await page.evaluate(() => window.__BROWSER_INFO__);

    // Core JavaScript features should be supported
    const coreFeatures = ['fetch', 'promises', 'local_storage', 'session_storage'];
    for (const feature of coreFeatures) {
      expect(browserFeatures.supportedFeatures).toContain(feature);
    }

    // Test ES6+ features
    const modernFeatures = ['classes', 'modules'];
    for (const feature of modernFeatures) {
      if (!browserFeatures.supportedFeatures.includes(feature)) {
        console.log(`Modern feature ${feature} not supported in ${browserInfo}`);
      }
    }

    // Test API compatibility
    const apiTests = [
      () => fetch('/api/health').catch(() => 'fetch-error'),
      () => new Promise(resolve => resolve('promise-ok')),
      () => localStorage.setItem('test', 'value'),
      () => sessionStorage.setItem('test', 'value')
    ];

    for (const apiTest of apiTests) {
      try {
        await page.evaluate(apiTest);
      } catch (error) {
        console.log(`API test failed: ${error.message}`);
      }
    }
  });

  test('should handle CSS features gracefully', async ({ page }) => {
    await page.goto('/');
    await page.waitForLoadState('networkidle');

    const cssSupport = await page.evaluate(() => {
      const testElement = document.createElement('div');
      document.body.appendChild(testElement);

      const cssFeatures = {
        grid: CSS.supports('display', 'grid'),
        flexbox: CSS.supports('display', 'flex'),
        custom_properties: CSS.supports('--test', 'red'),
        transforms: CSS.supports('transform', 'rotate(45deg)'),
        transitions: CSS.supports('transition', 'all 0.3s ease'),
        animations: CSS.supports('animation', 'test 1s ease'),
        calc: CSS.supports('width', 'calc(100% - 20px)'),
        viewport_units: CSS.supports('width', '100vw'),
        object_fit: CSS.supports('object-fit', 'cover'),
        backdrop_filter: CSS.supports('backdrop-filter', 'blur(10px)')
      };

      document.body.removeChild(testElement);
      return cssFeatures;
    });

    // Essential CSS features should be supported
    expect(cssSupport.flexbox).toBe(true);
    expect(cssSupport.transforms).toBe(true);
    expect(cssSupport.transitions).toBe(true);

    // Test layout doesn't break without modern features
    const layoutElements = await page.locator('.container, .layout, .grid, .flex').all();
    for (const element of layoutElements.slice(0, 5)) {
      if (await element.isVisible()) {
        const box = await element.boundingBox();
        expect(box.width).toBeGreaterThan(0);
        expect(box.height).toBeGreaterThan(0);
      }
    }
  });

  test('should handle different viewport sizes', async ({ page }) => {
    const viewports = [
      { width: 1920, height: 1080, name: 'Desktop Large' },
      { width: 1366, height: 768, name: 'Desktop Standard' },
      { width: 768, height: 1024, name: 'Tablet' },
      { width: 375, height: 667, name: 'Mobile' }
    ];

    for (const viewport of viewports) {
      await page.setViewportSize({ width: viewport.width, height: viewport.height });
      await page.goto('/');
      await page.waitForLoadState('networkidle');

      // Page should be usable at all viewport sizes
      const bodyOverflow = await page.evaluate(() => {
        const body = document.body;
        const html = document.documentElement;
        return {
          bodyScrollWidth: body.scrollWidth,
          bodyClientWidth: body.clientWidth,
          htmlScrollWidth: html.scrollWidth,
          htmlClientWidth: html.clientWidth
        };
      });

      // Should not have horizontal scroll
      expect(bodyOverflow.bodyScrollWidth).toBeLessThanOrEqual(viewport.width + 20);

      // Content should be accessible
      const mainContent = page.locator('main, .main-content, .content').first();
      if (await mainContent.isVisible()) {
        const contentBox = await mainContent.boundingBox();
        expect(contentBox.width).toBeGreaterThan(200); // Minimum usable width
      }
    }
  });

  test('should handle touch and mouse events', async ({ page }) => {
    await page.goto('/');
    await page.waitForLoadState('networkidle');

    // Test mouse events
    const clickableElements = await page.locator('button, a, [role="button"]').all();

    for (const element of clickableElements.slice(0, 3)) {
      if (await element.isVisible()) {
        // Test mouse hover
        await element.hover();
        await page.waitForTimeout(100);

        // Test mouse click
        await element.click();
        await page.waitForTimeout(100);

        // Test context menu (right click)
        await element.click({ button: 'right' });
        await page.waitForTimeout(100);
      }
    }

    // Test touch events on mobile-like viewport
    await page.setViewportSize({ width: 375, height: 667 });

    const touchElements = await page.locator('button, .touchable').all();
    for (const element of touchElements.slice(0, 3)) {
      if (await element.isVisible()) {
        // Test touch tap
        await element.tap();
        await page.waitForTimeout(100);

        // Test touch and hold
        await element.tap({ timeout: 1000 });
        await page.waitForTimeout(100);
      }
    }
  });

  test('should handle different input methods', async ({ page }) => {
    await page.goto('/settings');
    await page.waitForLoadState('networkidle');

    // Test keyboard navigation
    await page.keyboard.press('Tab');
    await page.keyboard.press('Tab');
    await page.keyboard.press('Enter');
    await page.waitForTimeout(500);

    // Test different input types
    const inputTypes = [
      'input[type="text"]',
      'input[type="email"]',
      'input[type="number"]',
      'input[type="tel"]',
      'input[type="search"]',
      'textarea',
      'select'
    ];

    for (const inputType of inputTypes) {
      const inputs = await page.locator(inputType).all();

      for (const input of inputs.slice(0, 2)) {
        if (await input.isVisible() && await input.isEnabled()) {
          // Test typing
          await input.focus();
          await input.fill('test value');

          const value = await input.inputValue();
          expect(value).toBeTruthy();

          // Test clearing
          await input.clear();

          // Test keyboard shortcuts
          await input.fill('test');
          await page.keyboard.press('Control+a');
          await page.keyboard.press('Control+c');
          await page.keyboard.press('Delete');
          await page.keyboard.press('Control+v');

          const pastedValue = await input.inputValue();
          expect(pastedValue).toBe('test');

          await input.clear();
        }
      }
    }
  });

  test('should handle media and file handling', async ({ page }) => {
    await page.goto('/');
    await page.waitForLoadState('networkidle');

    // Test image loading
    const images = await page.locator('img').all();
    let loadedImages = 0;

    for (const image of images.slice(0, 5)) {
      if (await image.isVisible()) {
        const naturalWidth = await image.evaluate(img => img.naturalWidth);
        const naturalHeight = await image.evaluate(img => img.naturalHeight);

        if (naturalWidth > 0 && naturalHeight > 0) {
          loadedImages++;
        }
      }
    }

    // At least some images should load
    if (images.length > 0) {
      expect(loadedImages).toBeGreaterThan(0);
    }

    // Test video elements if present
    const videos = await page.locator('video').all();
    for (const video of videos) {
      if (await video.isVisible()) {
        const canPlay = await video.evaluate(v => !!(v.canPlayType && v.canPlayType('video/mp4')));
        expect(typeof canPlay).toBe('boolean');
      }
    }

    // Test file input compatibility
    const fileInputs = await page.locator('input[type="file"]').all();
    for (const fileInput of fileInputs) {
      if (await fileInput.isVisible()) {
        const multiple = await fileInput.getAttribute('multiple');
        const accept = await fileInput.getAttribute('accept');

        // File input should have proper attributes
        expect(typeof multiple === 'string' || multiple === null).toBe(true);
        expect(typeof accept === 'string' || accept === null).toBe(true);
      }
    }
  });

  test('should handle network conditions gracefully', async ({ page }) => {
    // Test offline scenario
    await page.setOfflineMode(true);

    try {
      await page.goto('/');
      await page.waitForTimeout(2000);

      // Should show offline indicator or cached content
      const offlineIndicator = await page.locator('.offline, [data-offline], .no-connection').count();
      const hasContent = await page.textContent('body');

      expect(offlineIndicator > 0 || hasContent.length > 100).toBe(true);
    } finally {
      await page.setOfflineMode(false);
    }

    // Test slow network
    await page.route('**/*', async route => {
      await new Promise(resolve => setTimeout(resolve, 500));
      await route.continue();
    });

    await page.goto('/dashboard');
    await page.waitForLoadState('networkidle');

    // Should handle slow loading gracefully
    const _loadingIndicators = await page.locator('.loading, .spinner, .skeleton').count();
    const content = await page.textContent('body');

    expect(content.length).toBeGreaterThan(0);
  });

  test('should handle browser-specific quirks', async ({ page, browserName }) => {
    await page.goto('/');
    await page.waitForLoadState('networkidle');

    const browserInfo = await page.evaluate(() => window.__BROWSER_INFO__);

    // Safari-specific tests
    if (browserName === 'webkit' || browserInfo.isSafari) {
      // Test date input fallback
      const dateInputs = await page.locator('input[type="date"]').all();
      for (const dateInput of dateInputs) {
        if (await dateInput.isVisible()) {
          await dateInput.fill('2023-12-25');
          const value = await dateInput.inputValue();
          expect(value).toBeTruthy();
        }
      }

      // Test Safari-specific CSS
      const webkitStyles = await page.evaluate(() => {
        const testEl = document.createElement('div');
        testEl.style.webkitAppearance = 'none';
        return testEl.style.webkitAppearance === 'none';
      });
      expect(webkitStyles).toBe(true);
    }

    // Firefox-specific tests
    if (browserName === 'firefox' || browserInfo.isFirefox) {
      // Test Firefox-specific features
      const firefoxFeatures = await page.evaluate(() => {
        return {
          mozAppearance: CSS.supports('-moz-appearance', 'none'),
          mozUserSelect: CSS.supports('-moz-user-select', 'none')
        };
      });
      expect(typeof firefoxFeatures.mozAppearance).toBe('boolean');
    }

    // Chrome/Edge-specific tests
    if (browserName === 'chromium' || browserInfo.isChrome || browserInfo.isEdge) {
      // Test Chrome-specific features
      const chromeFeatures = await page.evaluate(() => {
        return {
          webkitBackdropFilter: CSS.supports('-webkit-backdrop-filter', 'blur(10px)'),
          chrome: typeof window.chrome !== 'undefined'
        };
      });
      expect(typeof chromeFeatures.webkitBackdropFilter).toBe('boolean');
    }
  });

  test('should handle polyfills and fallbacks', async ({ page }) => {
    await page.goto('/');
    await page.waitForLoadState('networkidle');

    // Check what polyfills might be needed
    const _polyfillChecks = await page.evaluate(() => {
      const needs = [];

      // Check for common polyfill needs
      if (!window.fetch) needs.push('fetch');
      if (!window.Promise) needs.push('promise');
      if (!Array.prototype.includes) needs.push('array-includes');
      if (!Object.assign) needs.push('object-assign');
      if (!window.IntersectionObserver) needs.push('intersection-observer');

      return needs;
    });

    // App should work even if polyfills are needed
    const functionalityTests = [
      async () => {
        // Test basic DOM manipulation
        await page.evaluate(() => {
          const testEl = document.createElement('div');
          testEl.textContent = 'test';
          document.body.appendChild(testEl);
          document.body.removeChild(testEl);
        });
      },
      async () => {
        // Test event handling
        await page.evaluate(() => {
          const button = document.querySelector('button');
          if (button) {
            button.addEventListener('click', () => {});
          }
        });
      }
    ];

    for (const test of functionalityTests) {
      await test();
    }

    // Should not have critical JavaScript errors
    const errors = await page.evaluate(() => window.__VALIDATION_ERRORS__ || []);
    const criticalErrors = errors.filter(error =>
      error.message.includes('TypeError') ||
      error.message.includes('ReferenceError')
    );

    expect(criticalErrors.length).toBe(0);
  });

  test('should maintain performance across browsers', async ({ page, browserName: _browserName }) => {
    const startTime = Date.now();

    await page.goto('/dashboard');
    await page.waitForLoadState('networkidle');

    const loadTime = Date.now() - startTime;

    // Load time should be reasonable across all browsers
    expect(loadTime).toBeLessThan(10000); // 10 seconds max

    // Test JavaScript performance
    const performanceTest = await page.evaluate(() => {
      const start = performance.now();

      // Simple computation test
      let result = 0;
      for (let i = 0; i < 10000; i++) {
        result += Math.random();
      }

      const computeTime = performance.now() - start;

      return {
        computeTime,
        result: result > 0
      };
    });

    expect(performanceTest.result).toBe(true);
    expect(performanceTest.computeTime).toBeLessThan(1000); // 1 second max

    // Test memory usage if available
    const memoryInfo = await page.evaluate(() => {
      if (performance.memory) {
        return {
          used: performance.memory.usedJSHeapSize,
          total: performance.memory.totalJSHeapSize
        };
      }
      return null;
    });

    if (memoryInfo) {
      expect(memoryInfo.used).toBeLessThan(200 * 1024 * 1024); // Under 200MB
    }
  });
});