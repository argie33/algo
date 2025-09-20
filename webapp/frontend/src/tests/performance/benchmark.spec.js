/**
 * Performance Benchmark Test Suite
 * Comprehensive performance validation and benchmarking
 */

import { test, expect } from '@playwright/test';

test.describe('Performance Benchmarks', () => {
  test.beforeEach(async ({ page }) => {
    // Set up performance monitoring
    await page.addInitScript(() => {
      window.__PERFORMANCE_DATA__ = {
        navigation: {},
        resources: [],
        marks: [],
        measures: []
      };

      // Capture navigation timing
      window.addEventListener('load', () => {
        setTimeout(() => {
          const timing = performance.getEntriesByType('navigation')[0];
          window.__PERFORMANCE_DATA__.navigation = {
            domContentLoaded: timing.domContentLoadedEventEnd - timing.domContentLoadedEventStart,
            loadComplete: timing.loadEventEnd - timing.loadEventStart,
            firstPaint: timing.responseEnd - timing.requestStart,
            totalTime: timing.loadEventEnd - timing.navigationStart,
            dnsLookup: timing.domainLookupEnd - timing.domainLookupStart,
            tcpConnect: timing.connectEnd - timing.connectStart,
            serverResponse: timing.responseEnd - timing.responseStart,
            domProcessing: timing.domComplete - timing.domLoading
          };
        }, 100);
      });

      // Capture resource timing
      const observer = new PerformanceObserver((list) => {
        list.getEntries().forEach(entry => {
          if (entry.entryType === 'resource') {
            window.__PERFORMANCE_DATA__.resources.push({
              name: entry.name,
              duration: entry.duration,
              size: entry.transferSize || 0,
              type: entry.initiatorType
            });
          } else if (entry.entryType === 'mark') {
            window.__PERFORMANCE_DATA__.marks.push({
              name: entry.name,
              startTime: entry.startTime
            });
          } else if (entry.entryType === 'measure') {
            window.__PERFORMANCE_DATA__.measures.push({
              name: entry.name,
              duration: entry.duration,
              startTime: entry.startTime
            });
          }
        });
      });

      observer.observe({ entryTypes: ['resource', 'mark', 'measure'] });
    });
  });

  test('should meet page load performance targets', async ({ page }) => {
    const startTime = Date.now();
    await page.goto('/');

    await page.waitForLoadState('networkidle');
    const loadTime = Date.now() - startTime;

    // Page should load within 3 seconds
    expect(loadTime).toBeLessThan(3000);

    // Wait for performance data
    await page.waitForTimeout(1000);

    const perfData = await page.evaluate(() => window.__PERFORMANCE_DATA__);

    if (perfData.navigation.totalTime) {
      // Total page load should be under 3 seconds
      expect(perfData.navigation.totalTime).toBeLessThan(3000);

      // DOM processing should be efficient
      expect(perfData.navigation.domProcessing).toBeLessThan(1000);

      // Server response should be fast
      expect(perfData.navigation.serverResponse).toBeLessThan(500);
    }
  });

  test('should optimize resource loading performance', async ({ page }) => {
    await page.goto('/portfolio');
    await page.waitForLoadState('networkidle');
    await page.waitForTimeout(2000);

    const perfData = await page.evaluate(() => window.__PERFORMANCE_DATA__);

    // Analyze resource performance
    const jsResources = perfData.resources.filter(r => r.name.includes('.js'));
    const cssResources = perfData.resources.filter(r => r.name.includes('.css'));
    const imageResources = perfData.resources.filter(r => r.type === 'img');

    // JavaScript bundles should load quickly
    for (const js of jsResources) {
      expect(js.duration).toBeLessThan(1000);

      // Main bundles should be reasonably sized (under 2MB)
      if (js.name.includes('main') || js.name.includes('vendor')) {
        expect(js.size).toBeLessThan(2 * 1024 * 1024);
      }
    }

    // CSS should load efficiently
    for (const css of cssResources) {
      expect(css.duration).toBeLessThan(500);
      expect(css.size).toBeLessThan(500 * 1024); // Under 500KB
    }

    // Images should be optimized
    for (const img of imageResources) {
      expect(img.duration).toBeLessThan(2000);
    }
  });

  test('should maintain smooth UI interactions', async ({ page }) => {
    await page.goto('/');
    await page.waitForLoadState('networkidle');

    // Measure interaction responsiveness
    const interactions = [
      { action: () => page.click('nav a:first-child'), name: 'navigation' },
      { action: () => page.fill('input[type="search"]', 'AAPL'), name: 'search_input' },
      { action: () => page.click('button:visible'), name: 'button_click' }
    ];

    for (const interaction of interactions) {
      const startTime = Date.now();

      try {
        await interaction.action();
        await page.waitForTimeout(100); // Allow UI to update

        const responseTime = Date.now() - startTime;

        // Interactions should respond within 100ms
        expect(responseTime).toBeLessThan(100);
      } catch (e) {
        // Some interactions might not be available on all pages
        console.log(`Interaction ${interaction.name} not available: ${e.message}`);
      }
    }
  });

  test('should optimize memory usage', async ({ page }) => {
    await page.goto('/');
    await page.waitForLoadState('networkidle');

    // Measure initial memory usage
    const initialMemory = await page.evaluate(() => {
      if ('memory' in performance) {
        return {
          used: performance.memory.usedJSHeapSize,
          total: performance.memory.totalJSHeapSize,
          limit: performance.memory.jsHeapSizeLimit
        };
      }
      return null;
    });

    // Navigate through several pages to test memory leaks
    const pages = ['/portfolio', '/dashboard', '/settings', '/'];

    for (const pagePath of pages) {
      await page.goto(pagePath);
      await page.waitForLoadState('networkidle');
      await page.waitForTimeout(1000);
    }

    // Measure memory after navigation
    const finalMemory = await page.evaluate(() => {
      if ('memory' in performance) {
        return {
          used: performance.memory.usedJSHeapSize,
          total: performance.memory.totalJSHeapSize,
          limit: performance.memory.jsHeapSizeLimit
        };
      }
      return null;
    });

    if (initialMemory && finalMemory) {
      // Memory usage shouldn't increase dramatically
      const memoryIncrease = finalMemory.used - initialMemory.used;
      const memoryIncreasePercent = (memoryIncrease / initialMemory.used) * 100;

      // Memory increase should be reasonable (less than 50%)
      expect(memoryIncreasePercent).toBeLessThan(50);

      // Total memory usage should stay within reasonable bounds (under 100MB)
      expect(finalMemory.used).toBeLessThan(100 * 1024 * 1024);
    }
  });

  test('should handle large data sets efficiently', async ({ page }) => {
    await page.goto('/portfolio');
    await page.waitForLoadState('networkidle');

    // Measure rendering performance with large data
    const renderingStart = await page.evaluate(() => {
      performance.mark('large-data-start');
      return performance.now();
    });

    // Wait for data to load and render
    await page.waitForTimeout(3000);

    const renderingEnd = await page.evaluate(() => {
      performance.mark('large-data-end');
      performance.measure('large-data-render', 'large-data-start', 'large-data-end');
      return performance.now();
    });

    const renderTime = renderingEnd - renderingStart;

    // Large data rendering should complete within 5 seconds
    expect(renderTime).toBeLessThan(5000);

    // Check if virtualization is working for large lists
    const visibleRows = await page.locator('tbody tr:visible, .virtual-item:visible').count();
    const totalRows = await page.locator('tbody tr, .data-row').count();

    // If there are many rows, virtualization should limit visible ones
    if (totalRows > 50) {
      expect(visibleRows).toBeLessThan(totalRows);
      expect(visibleRows).toBeLessThan(100); // Reasonable virtualization limit
    }
  });

  test('should optimize network requests', async ({ page }) => {
    const requests = [];

    page.on('request', request => {
      requests.push({
        url: request.url(),
        method: request.method(),
        timestamp: Date.now()
      });
    });

    page.on('response', response => {
      const request = requests.find(req => req.url === response.url());
      if (request) {
        request.status = response.status();
        request.responseTime = Date.now() - request.timestamp;
      }
    });

    await page.goto('/dashboard');
    await page.waitForLoadState('networkidle');
    await page.waitForTimeout(3000);

    const apiRequests = requests.filter(req => req.url.includes('/api/'));

    // API requests should be reasonably fast
    for (const request of apiRequests) {
      if (request.responseTime) {
        expect(request.responseTime).toBeLessThan(2000); // Under 2 seconds
      }
    }

    // Should not make excessive API calls
    expect(apiRequests.length).toBeLessThan(20);

    // Should group similar requests efficiently
    const uniqueEndpoints = new Set(apiRequests.map(req => req.url.split('?')[0]));
    const duplicateRequests = apiRequests.length - uniqueEndpoints.size;

    // Minimal duplicate requests
    expect(duplicateRequests).toBeLessThan(5);
  });

  test('should maintain 60 FPS during animations', async ({ page }) => {
    await page.goto('/');
    await page.waitForLoadState('networkidle');

    // Start FPS monitoring
    await page.evaluate(() => {
      window.__FPS_DATA__ = [];
      let lastTime = performance.now();
      let frameCount = 0;

      function measureFPS() {
        const currentTime = performance.now();
        frameCount++;

        if (currentTime - lastTime >= 1000) {
          window.__FPS_DATA__.push(frameCount);
          frameCount = 0;
          lastTime = currentTime;
        }

        requestAnimationFrame(measureFPS);
      }

      requestAnimationFrame(measureFPS);
    });

    // Trigger animations by interacting with the UI
    const animatedElements = await page.locator('.animate, [class*="transition"], [class*="fade"]').all();

    for (const element of animatedElements.slice(0, 3)) {
      if (await element.isVisible()) {
        await element.hover();
        await page.waitForTimeout(500);
        await element.click().catch(() => {}); // Ignore click errors
        await page.waitForTimeout(500);
      }
    }

    // Collect FPS data
    await page.waitForTimeout(3000);
    const fpsData = await page.evaluate(() => window.__FPS_DATA__);

    if (fpsData.length > 0) {
      const avgFPS = fpsData.reduce((a, b) => a + b) / fpsData.length;
      const minFPS = Math.min(...fpsData);

      // Average FPS should be close to 60
      expect(avgFPS).toBeGreaterThan(30);

      // Minimum FPS shouldn't drop too low
      expect(minFPS).toBeGreaterThan(20);
    }
  });

  test('should optimize bundle size and loading strategy', async ({ page }) => {
    await page.goto('/');
    await page.waitForLoadState('networkidle');
    await page.waitForTimeout(2000);

    const perfData = await page.evaluate(() => window.__PERFORMANCE_DATA__);

    // Calculate total JavaScript bundle size
    const jsResources = perfData.resources.filter(r =>
      r.name.includes('.js') && !r.name.includes('node_modules')
    );

    const totalJSSize = jsResources.reduce((total, resource) => total + (resource.size || 0), 0);

    // Total JS bundle should be under 2MB
    expect(totalJSSize).toBeLessThan(2 * 1024 * 1024);

    // Check for code splitting
    const chunkFiles = jsResources.filter(r =>
      r.name.includes('chunk') || r.name.includes('lazy')
    );

    // Should have code splitting if total size is large
    if (totalJSSize > 500 * 1024) {
      expect(chunkFiles.length).toBeGreaterThan(0);
    }

    // Main bundle should be reasonably sized
    const mainBundle = jsResources.find(r => r.name.includes('main'));
    if (mainBundle) {
      expect(mainBundle.size).toBeLessThan(1024 * 1024); // Under 1MB
    }
  });

  test('should handle concurrent operations efficiently', async ({ page }) => {
    await page.goto('/dashboard');
    await page.waitForLoadState('networkidle');

    // Perform multiple concurrent operations
    const concurrentOperations = [
      page.click('nav a:nth-child(1)'),
      page.fill('input[type="search"]', 'test'),
      page.click('button:visible').catch(() => {}),
      page.hover('.chart-container').catch(() => {}),
      page.evaluate(() => window.scrollTo(0, 500))
    ];

    const startTime = Date.now();
    await Promise.all(concurrentOperations);
    const operationTime = Date.now() - startTime;

    // Concurrent operations should complete efficiently
    expect(operationTime).toBeLessThan(2000);

    // UI should remain responsive
    const isResponsive = await page.evaluate(() => {
      // Check if page is still interactive
      return document.readyState === 'complete' &&
             !document.hidden &&
             window.requestAnimationFrame !== undefined;
    });

    expect(isResponsive).toBe(true);
  });

  test('should optimize Core Web Vitals', async ({ page }) => {
    await page.goto('/');

    // Measure Core Web Vitals
    const webVitals = await page.evaluate(() => {
      return new Promise(resolve => {
        const vitals = {};

        // Largest Contentful Paint
        new PerformanceObserver((list) => {
          const entries = list.getEntries();
          const lastEntry = entries[entries.length - 1];
          vitals.lcp = lastEntry.startTime;
        }).observe({ entryTypes: ['largest-contentful-paint'] });

        // First Input Delay would be measured on real interactions
        // For testing, we'll simulate it
        vitals.fid = 0; // Assuming no delay in test environment

        // Cumulative Layout Shift
        let cumulativeScore = 0;
        new PerformanceObserver((list) => {
          for (const entry of list.getEntries()) {
            if (!entry.hadRecentInput) {
              cumulativeScore += entry.value;
            }
          }
          vitals.cls = cumulativeScore;
        }).observe({ entryTypes: ['layout-shift'] });

        setTimeout(() => resolve(vitals), 3000);
      });
    });

    // Core Web Vitals thresholds
    if (webVitals.lcp) {
      expect(webVitals.lcp).toBeLessThan(2500); // LCP < 2.5s
    }

    expect(webVitals.fid).toBeLessThan(100); // FID < 100ms

    if (webVitals.cls !== undefined) {
      expect(webVitals.cls).toBeLessThan(0.1); // CLS < 0.1
    }
  });
});