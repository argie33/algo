/**
 * Comprehensive E2E Performance Tests
 * Tests load performance, concurrent users, real API stress testing
 * No mocks - validates real system performance under stress
 */

import { test, expect } from '@playwright/test';

test.describe('Performance and Load Testing', () => {
  let page;
  let context;
  
  test.beforeEach(async ({ browser }) => {
    context = await browser.newContext({
      // Enable performance monitoring
      recordVideo: { dir: 'test-results/videos/' },
      recordHar: { path: 'test-results/network.har' }
    });
    page = await context.newPage();
    
    // Track performance metrics
    await page.addInitScript(() => {
      window.performanceMetrics = {
        navigationStart: performance.now(),
        loadTimes: [],
        apiCallTimes: [],
        renderTimes: []
      };
      
      // Track API call performance
      const originalFetch = window.fetch;
      window.fetch = function(...args) {
        const startTime = performance.now();
        return originalFetch.apply(this, args).then(response => {
          const endTime = performance.now();
          window.performanceMetrics.apiCallTimes.push({
            url: args[0],
            duration: endTime - startTime,
            status: response.status
          });
          return response;
        });
      };
      
      // Track render performance
      window.addEventListener('load', () => {
        window.performanceMetrics.loadTimes.push({
          type: 'initial-load',
          duration: performance.now() - window.performanceMetrics.navigationStart
        });
      });
    });
  });

  test.afterEach(async () => {
    // Extract performance metrics
    const metrics = await page.evaluate(() => window.performanceMetrics);
    console.log('Performance Metrics:', JSON.stringify(metrics, null, 2));
    
    await context.close();
  });

  test('should load dashboard within performance thresholds', async () => {
    console.log('🔄 Testing dashboard load performance...');
    
    const startTime = Date.now();
    
    await page.goto('/dashboard');
    
    // Wait for critical elements to load
    await page.waitForSelector('[data-testid="dashboard-container"]', { timeout: 30000 });
    
    const loadTime = Date.now() - startTime;
    console.log(`Dashboard load time: ${loadTime}ms`);
    
    // Performance thresholds
    expect(loadTime).toBeLessThan(5000); // 5 seconds max initial load
    
    // Wait for all dashboard components to load
    await page.waitForSelector('[data-testid="portfolio-summary"]', { timeout: 10000 });
    await page.waitForSelector('[data-testid="market-overview"]', { timeout: 10000 });
    await page.waitForSelector('[data-testid="watchlist-preview"]', { timeout: 10000 });
    
    const fullLoadTime = Date.now() - startTime;
    console.log(`Full dashboard load time: ${fullLoadTime}ms`);
    
    expect(fullLoadTime).toBeLessThan(10000); // 10 seconds max for full load
    
    // Check for layout shifts
    const layoutShiftScore = await page.evaluate(() => {
      return new Promise(resolve => {
        let cls = 0;
        new PerformanceObserver(list => {
          for (const entry of list.getEntries()) {
            if (!entry.hadRecentInput) {
              cls += entry.value;
            }
          }
          resolve(cls);
        }).observe({ type: 'layout-shift', buffered: true });
        
        setTimeout(() => resolve(cls), 3000);
      });
    });
    
    console.log(`Cumulative Layout Shift: ${layoutShiftScore}`);
    expect(layoutShiftScore).toBeLessThan(0.1); // Good CLS score
  });

  test('should handle multiple concurrent API calls efficiently', async () => {
    console.log('🔄 Testing concurrent API call performance...');
    
    await page.goto('/market-overview');
    await page.waitForSelector('[data-testid="market-container"]', { timeout: 30000 });
    
    // Trigger multiple data refreshes simultaneously
    const startTime = performance.now();
    
    await Promise.all([
      page.click('[data-testid="refresh-market-data"]'),
      page.click('[data-testid="refresh-sectors"]'),
      page.click('[data-testid="refresh-indices"]'),
      page.click('[data-testid="refresh-movers"]')
    ]);
    
    // Wait for all requests to complete
    await page.waitForTimeout(5000);
    
    const endTime = performance.now();
    const concurrentCallTime = endTime - startTime;
    
    console.log(`Concurrent API calls completed in: ${concurrentCallTime}ms`);
    expect(concurrentCallTime).toBeLessThan(8000); // 8 seconds max for concurrent calls
    
    // Verify all sections loaded data
    const marketData = await page.locator('[data-testid="market-data"]');
    const sectorsData = await page.locator('[data-testid="sectors-data"]');
    const indicesData = await page.locator('[data-testid="indices-data"]');
    const moversData = await page.locator('[data-testid="movers-data"]');
    
    await expect(marketData).toBeVisible();
    await expect(sectorsData).toBeVisible();
    await expect(indicesData).toBeVisible();
    await expect(moversData).toBeVisible();
    
    // Check API call performance metrics
    const apiMetrics = await page.evaluate(() => window.performanceMetrics.apiCallTimes);
    const recentCalls = apiMetrics.filter(call => call.duration > 0);
    
    if (recentCalls.length > 0) {
      const averageApiTime = recentCalls.reduce((sum, call) => sum + call.duration, 0) / recentCalls.length;
      console.log(`Average API call time: ${averageApiTime}ms`);
      expect(averageApiTime).toBeLessThan(3000); // 3 seconds average
    }
  });

  test('should maintain performance under rapid navigation', async () => {
    console.log('🔄 Testing rapid navigation performance...');
    
    const navigationPaths = [
      '/dashboard',
      '/portfolio',
      '/market-overview',
      '/stock-detail/AAPL',
      '/watchlist',
      '/settings',
      '/dashboard'
    ];
    
    const navigationTimes = [];
    
    for (let i = 0; i < navigationPaths.length; i++) {
      const startTime = performance.now();
      
      await page.goto(navigationPaths[i]);
      await page.waitForLoadState('networkidle', { timeout: 10000 });
      
      const endTime = performance.now();
      const navTime = endTime - startTime;
      navigationTimes.push(navTime);
      
      console.log(`Navigation to ${navigationPaths[i]}: ${navTime}ms`);
      
      // Brief pause to allow cleanup
      await page.waitForTimeout(500);
    }
    
    // Calculate navigation performance metrics
    const averageNavTime = navigationTimes.reduce((sum, time) => sum + time, 0) / navigationTimes.length;
    const maxNavTime = Math.max(...navigationTimes);
    
    console.log(`Average navigation time: ${averageNavTime}ms`);
    console.log(`Max navigation time: ${maxNavTime}ms`);
    
    expect(averageNavTime).toBeLessThan(3000); // 3 seconds average
    expect(maxNavTime).toBeLessThan(6000); // 6 seconds max
    
    // Check for memory leaks during rapid navigation
    const finalMemory = await page.evaluate(() => {
      if (performance.memory) {
        return {
          usedJSHeapSize: performance.memory.usedJSHeapSize,
          totalJSHeapSize: performance.memory.totalJSHeapSize,
          jsHeapSizeLimit: performance.memory.jsHeapSizeLimit
        };
      }
      return null;
    });
    
    if (finalMemory) {
      console.log('Memory usage after navigation:', finalMemory);
      const memoryUsagePercent = (finalMemory.usedJSHeapSize / finalMemory.jsHeapSizeLimit) * 100;
      expect(memoryUsagePercent).toBeLessThan(50); // Less than 50% memory usage
    }
  });

  test('should handle large data sets efficiently', async () => {
    console.log('🔄 Testing large data set handling...');
    
    await page.goto('/advanced-screener');
    await page.waitForSelector('[data-testid="screener-container"]', { timeout: 30000 });
    
    // Set filters to return large result set
    await page.selectOption('[data-testid="market-cap-filter"]', 'all');
    await page.selectOption('[data-testid="sector-filter"]', 'all');
    await page.fill('[data-testid="volume-min"]', '1000');
    
    const startTime = performance.now();
    
    // Run screener to get large data set
    await page.click('[data-testid="run-screener"]');
    
    // Wait for results table to load
    await page.waitForSelector('[data-testid="results-table"]', { timeout: 30000 });
    
    const loadTime = performance.now() - startTime;
    console.log(`Large data set load time: ${loadTime}ms`);
    
    expect(loadTime).toBeLessThan(15000); // 15 seconds max for large data
    
    // Check virtual scrolling performance if implemented
    const resultsTable = await page.locator('[data-testid="results-table"]');
    await expect(resultsTable).toBeVisible();
    
    // Test scrolling performance
    const scrollStartTime = performance.now();
    
    for (let i = 0; i < 10; i++) {
      await page.keyboard.press('PageDown');
      await page.waitForTimeout(100);
    }
    
    const scrollTime = performance.now() - scrollStartTime;
    console.log(`Scroll performance (10 page downs): ${scrollTime}ms`);
    
    expect(scrollTime).toBeLessThan(3000); // 3 seconds for scrolling
    
    // Test sorting performance
    const sortStartTime = performance.now();
    
    await page.click('[data-testid="sort-volume"]');
    await page.waitForSelector('[data-testid="sorted-indicator"]', { timeout: 5000 });
    
    const sortTime = performance.now() - sortStartTime;
    console.log(`Sort performance: ${sortTime}ms`);
    
    expect(sortTime).toBeLessThan(2000); // 2 seconds for sorting
  });

  test('should maintain performance with real-time data updates', async () => {
    console.log('🔄 Testing real-time data update performance...');
    
    await page.goto('/live-data-enhanced');
    await page.waitForSelector('[data-testid="live-data-container"]', { timeout: 30000 });
    
    // Start real-time data feed
    await page.click('[data-testid="start-live-feed"]');
    
    // Monitor performance during live updates
    const startTime = performance.now();
    let updateCount = 0;
    
    // Track data updates
    await page.evaluate(() => {
      window.updateCount = 0;
      window.updateTimes = [];
      
      // Monitor DOM changes
      const observer = new MutationObserver(() => {
        window.updateCount++;
        window.updateTimes.push(performance.now());
      });
      
      const liveDataContainer = document.querySelector('[data-testid="live-data-container"]');
      if (liveDataContainer) {
        observer.observe(liveDataContainer, { 
          childList: true, 
          subtree: true, 
          attributes: true 
        });
      }
    });
    
    // Let live data run for 30 seconds
    await page.waitForTimeout(30000);
    
    const endTime = performance.now();
    const totalTime = endTime - startTime;
    
    // Get update metrics
    const updateMetrics = await page.evaluate(() => ({
      updateCount: window.updateCount,
      updateTimes: window.updateTimes
    }));
    
    console.log(`Real-time updates in 30 seconds: ${updateMetrics.updateCount}`);
    console.log(`Total time: ${totalTime}ms`);
    
    if (updateMetrics.updateCount > 0) {
      const averageUpdateInterval = totalTime / updateMetrics.updateCount;
      console.log(`Average update interval: ${averageUpdateInterval}ms`);
      
      // Should have reasonable update frequency
      expect(averageUpdateInterval).toBeGreaterThan(100); // At least 100ms between updates
      expect(averageUpdateInterval).toBeLessThan(10000); // At most 10 seconds between updates
    }
    
    // Check that page remains responsive during updates
    const responseStartTime = performance.now();
    await page.click('[data-testid="pause-live-feed"]');
    const responseTime = performance.now() - responseStartTime;
    
    console.log(`UI response time during live updates: ${responseTime}ms`);
    expect(responseTime).toBeLessThan(500); // 500ms max response time
  });

  test('should handle multiple users simulation', async () => {
    console.log('🔄 Testing multiple concurrent users simulation...');
    
    // Create multiple browser contexts to simulate different users
    const userContexts = [];
    const userPages = [];
    
    try {
      // Create 5 concurrent user sessions
      for (let i = 0; i < 5; i++) {
        const userContext = await page.context().browser().newContext();
        const userPage = await userContext.newPage();
        
        userContexts.push(userContext);
        userPages.push(userPage);
      }
      
      const startTime = performance.now();
      
      // Have all users navigate to dashboard simultaneously
      await Promise.all(
        userPages.map(userPage => userPage.goto('/dashboard'))
      );
      
      // Wait for all dashboards to load
      await Promise.all(
        userPages.map(userPage => 
          userPage.waitForSelector('[data-testid="dashboard-container"]', { timeout: 30000 })
        )
      );
      
      const loadTime = performance.now() - startTime;
      console.log(`Multi-user dashboard load time: ${loadTime}ms`);
      
      expect(loadTime).toBeLessThan(15000); // 15 seconds for 5 concurrent users
      
      // Have all users perform actions simultaneously
      const actionStartTime = performance.now();
      
      await Promise.all(
        userPages.map(async (userPage, index) => {
          // Different actions for each user
          switch (index % 3) {
            case 0:
              const refreshButton = userPage.locator('[data-testid="refresh-data"]');
              if (await refreshButton.isVisible()) {
                await refreshButton.click();
              }
              break;
            case 1:
              await userPage.goto('/portfolio');
              break;
            case 2:
              await userPage.goto('/market-overview');
              break;
          }
        })
      );
      
      const actionTime = performance.now() - actionStartTime;
      console.log(`Multi-user actions completed in: ${actionTime}ms`);
      
      expect(actionTime).toBeLessThan(10000); // 10 seconds for concurrent actions
      
      // Verify all users still have functional interfaces
      for (const userPage of userPages) {
        const navigation = await userPage.locator('[data-testid="main-navigation"]');
        await expect(navigation).toBeVisible();
      }
      
    } finally {
      // Clean up all user contexts
      for (const userContext of userContexts) {
        await userContext.close();
      }
    }
  });

  test('should optimize bundle loading and caching', async () => {
    console.log('🔄 Testing bundle loading and caching performance...');
    
    // First visit - cold cache
    const coldStartTime = performance.now();
    
    await page.goto('/dashboard');
    await page.waitForSelector('[data-testid="dashboard-container"]', { timeout: 30000 });
    
    const coldLoadTime = performance.now() - coldStartTime;
    console.log(`Cold load time: ${coldLoadTime}ms`);
    
    // Get network metrics for first load
    const coldNetworkMetrics = await page.evaluate(() => {
      const entries = performance.getEntriesByType('resource');
      return entries.map(entry => ({
        name: entry.name,
        duration: entry.duration,
        transferSize: entry.transferSize,
        decodedBodySize: entry.decodedBodySize
      }));
    });
    
    const jsResources = coldNetworkMetrics.filter(metric => 
      metric.name.includes('.js') && metric.transferSize > 0
    );
    
    const totalJSSize = jsResources.reduce((sum, resource) => sum + resource.transferSize, 0);
    console.log(`Total JS bundle size: ${totalJSSize} bytes`);
    
    // Refresh page - warm cache
    const warmStartTime = performance.now();
    
    await page.reload();
    await page.waitForSelector('[data-testid="dashboard-container"]', { timeout: 30000 });
    
    const warmLoadTime = performance.now() - warmStartTime;
    console.log(`Warm load time: ${warmLoadTime}ms`);
    
    // Warm load should be significantly faster
    expect(warmLoadTime).toBeLessThan(coldLoadTime * 0.5); // At least 50% faster
    
    // Navigate to different page to test code splitting
    const codeSpilitStartTime = performance.now();
    
    await page.goto('/stock-detail/AAPL');
    await page.waitForSelector('[data-testid="stock-detail-container"]', { timeout: 30000 });
    
    const codeSplitLoadTime = performance.now() - codeSpilitStartTime;
    console.log(`Code split page load time: ${codeSplitLoadTime}ms`);
    
    expect(codeSplitLoadTime).toBeLessThan(4000); // 4 seconds for code split pages
    
    // Check that new chunks were loaded
    const splitNetworkMetrics = await page.evaluate(() => {
      const entries = performance.getEntriesByType('resource');
      return entries.filter(entry => 
        entry.name.includes('.js') && 
        entry.startTime > 0 && 
        entry.transferSize > 0
      );
    });
    
    console.log(`Additional chunks loaded: ${splitNetworkMetrics.length}`);
  });

  test('should handle API error scenarios without performance degradation', async () => {
    console.log('🔄 Testing performance during API error scenarios...');
    
    await page.goto('/portfolio');
    await page.waitForSelector('[data-testid="portfolio-container"]', { timeout: 30000 });
    
    // Simulate API errors
    await page.route('**/api/portfolio/**', route => {
      // Randomly fail 30% of requests
      if (Math.random() < 0.3) {
        route.fulfill({
          status: 500,
          body: JSON.stringify({ error: 'Server error' })
        });
      } else {
        route.continue();
      }
    });
    
    const errorTestStartTime = performance.now();
    
    // Trigger multiple actions that will encounter errors
    for (let i = 0; i < 10; i++) {
      const refreshButton = page.locator('[data-testid="refresh-portfolio"]');
      if (await refreshButton.isVisible()) {
        await refreshButton.click();
      }
      await page.waitForTimeout(500);
    }
    
    const errorTestTime = performance.now() - errorTestStartTime;
    console.log(`Performance with API errors: ${errorTestTime}ms`);
    
    // Should still complete in reasonable time despite errors
    expect(errorTestTime).toBeLessThan(15000); // 15 seconds with errors
    
    // UI should remain responsive
    const uiResponseStartTime = performance.now();
    await page.click('[data-testid="nav-dashboard"]');
    const uiResponseTime = performance.now() - uiResponseStartTime;
    
    expect(uiResponseTime).toBeLessThan(1000); // 1 second response time
    
    // Clear error simulation
    await page.unroute('**/api/portfolio/**');
  });
});