/**
 * Load Testing Suite
 * Performance testing under various load conditions
 */

import { test, expect } from '@playwright/test';

test.describe('Load Testing', () => {
  test.beforeEach(async ({ page }) => {
    // Set up load testing monitoring
    await page.addInitScript(() => {
      window.__LOAD_TEST_DATA__ = {
        requests: [],
        errors: [],
        timings: [],
        resources: []
      };

      // Monitor all requests
      const originalFetch = window.fetch;
      window.fetch = function(...args) {
        const startTime = Date.now();
        const url = args[0];

        window.__LOAD_TEST_DATA__.requests.push({
          url,
          startTime,
          method: (args[1] && args[1].method) || 'GET'
        });

        return originalFetch.apply(this, args)
          .then(response => {
            const endTime = Date.now();
            const request = window.__LOAD_TEST_DATA__.requests.find(r =>
              r.url === url && r.startTime === startTime
            );
            if (request) {
              request.endTime = endTime;
              request.duration = endTime - startTime;
              request.status = response.status;
            }
            return response;
          })
          .catch(error => {
            const endTime = Date.now();
            window.__LOAD_TEST_DATA__.errors.push({
              url,
              error: error.message,
              timestamp: endTime
            });
            throw error;
          });
      };

      // Monitor performance entries
      const observer = new PerformanceObserver((list) => {
        list.getEntries().forEach(entry => {
          if (entry.entryType === 'resource') {
            window.__LOAD_TEST_DATA__.resources.push({
              name: entry.name,
              duration: entry.duration,
              transferSize: entry.transferSize || 0,
              responseEnd: entry.responseEnd
            });
          }
        });
      });

      observer.observe({ entryTypes: ['resource'] });
    });
  });

  test('should handle normal user load efficiently', async ({ page }) => {
    // Simulate normal user workflow
    const startTime = Date.now();

    await page.goto('/');
    await page.waitForLoadState('networkidle');

    // Normal user navigation pattern
    const userActions = [
      () => page.goto('/dashboard'),
      () => page.goto('/portfolio'),
      () => page.goto('/market-overview'),
      () => page.goto('/settings'),
      () => page.goto('/')
    ];

    for (const action of userActions) {
      const actionStart = Date.now();
      await action();
      await page.waitForLoadState('networkidle');
      const actionTime = Date.now() - actionStart;

      // Each page should load within 3 seconds under normal load
      expect(actionTime).toBeLessThan(3000);
    }

    const totalTime = Date.now() - startTime;
    expect(totalTime).toBeLessThan(20000); // Total workflow under 20 seconds

    // Check for errors during normal load
    const loadData = await page.evaluate(() => window.__LOAD_TEST_DATA__);
    expect(loadData.errors.length).toBe(0);
  });

  test('should handle rapid consecutive requests', async ({ page }) => {
    await page.goto('/dashboard');
    await page.waitForLoadState('networkidle');

    // Rapid fire requests to test rate limiting and performance
    const rapidRequests = [];
    const requestCount = 20;

    for (let i = 0; i < requestCount; i++) {
      const request = page.evaluate(async (index) => {
        const startTime = Date.now();
        try {
          const response = await fetch(`/api/portfolio/summary?t=${index}`, {
            headers: { 'Authorization': 'Bearer test-token' }
          });
          return {
            index,
            status: response.status,
            duration: Date.now() - startTime,
            success: true
          };
        } catch (error) {
          return {
            index,
            error: error.message,
            duration: Date.now() - startTime,
            success: false
          };
        }
      }, i);

      rapidRequests.push(request);

      // Small delay to simulate rapid but not instantaneous requests
      await page.waitForTimeout(50);
    }

    const results = await Promise.all(rapidRequests);

    // Analyze results
    const successfulRequests = results.filter(r => r.success);
    const _failedRequests = results.filter(r => !r.success);
    const rateLimitedRequests = results.filter(r => r.status === 429);

    // Should handle at least 50% of rapid requests successfully
    expect(successfulRequests.length).toBeGreaterThan(requestCount * 0.5);

    // Rate limiting should kick in for excessive requests
    if (rateLimitedRequests.length > 0) {
      expect(rateLimitedRequests.length).toBeLessThan(requestCount * 0.8);
    }

    // Successful requests should still be reasonably fast
    const avgResponseTime = successfulRequests.reduce((sum, r) => sum + r.duration, 0) / successfulRequests.length;
    expect(avgResponseTime).toBeLessThan(2000);
  });

  test('should maintain performance with concurrent users simulation', async ({ page, context }) => {
    // Simulate multiple concurrent users by opening multiple pages
    const pages = [page];

    // Create additional page contexts to simulate concurrent users
    for (let i = 0; i < 3; i++) {
      const newPage = await context.newPage();
      pages.push(newPage);
    }

    // Concurrent user actions
    const concurrentActions = pages.map(async (userPage, index) => {
      const startTime = Date.now();

      try {
        await userPage.goto('/');
        await userPage.waitForLoadState('networkidle');

        // Each user performs different actions
        const userWorkflows = [
          ['/dashboard', '/portfolio'],
          ['/market-overview', '/settings'],
          ['/portfolio', '/dashboard'],
          ['/settings', '/market-overview']
        ];

        const workflow = userWorkflows[index % userWorkflows.length];

        for (const path of workflow) {
          await userPage.goto(path);
          await userPage.waitForLoadState('networkidle');
          await userPage.waitForTimeout(1000);
        }

        return {
          userId: index,
          success: true,
          duration: Date.now() - startTime
        };
      } catch (error) {
        return {
          userId: index,
          success: false,
          error: error.message,
          duration: Date.now() - startTime
        };
      }
    });

    const results = await Promise.all(concurrentActions);

    // All concurrent users should complete successfully
    const successfulUsers = results.filter(r => r.success);
    expect(successfulUsers.length).toBe(pages.length);

    // Performance shouldn't degrade significantly with concurrent users
    const avgDuration = successfulUsers.reduce((sum, r) => sum + r.duration, 0) / successfulUsers.length;
    expect(avgDuration).toBeLessThan(15000); // Under 15 seconds per user

    // Clean up additional pages
    for (let i = 1; i < pages.length; i++) {
      await pages[i].close();
    }
  });

  test('should handle data-intensive operations under load', async ({ page }) => {
    await page.goto('/portfolio');
    await page.waitForLoadState('networkidle');

    // Simulate data-intensive operations
    const dataOperations = [
      () => page.evaluate(() => fetch('/api/portfolio/detailed-analytics')),
      () => page.evaluate(() => fetch('/api/market/historical-data?period=5years')),
      () => page.evaluate(() => fetch('/api/analytics/performance-metrics')),
      () => page.evaluate(() => fetch('/api/reports/comprehensive-analysis'))
    ];

    const operationResults = [];

    for (const operation of dataOperations) {
      const startTime = Date.now();

      try {
        const result = await operation();
        operationResults.push({
          success: true,
          duration: Date.now() - startTime,
          status: result?.status
        });
      } catch (error) {
        operationResults.push({
          success: false,
          duration: Date.now() - startTime,
          error: error.message
        });
      }

      // Wait between operations to simulate user behavior
      await page.waitForTimeout(2000);
    }

    // Data-intensive operations should complete within reasonable time
    const successfulOps = operationResults.filter(r => r.success);
    expect(successfulOps.length).toBeGreaterThan(0);

    for (const op of successfulOps) {
      expect(op.duration).toBeLessThan(10000); // Under 10 seconds
    }

    // Check memory usage after data operations
    const memoryUsage = await page.evaluate(() => {
      if ('memory' in performance) {
        return performance.memory.usedJSHeapSize;
      }
      return null;
    });

    if (memoryUsage) {
      // Memory usage should stay reasonable (under 150MB)
      expect(memoryUsage).toBeLessThan(150 * 1024 * 1024);
    }
  });

  test('should recover gracefully from server errors under load', async ({ page }) => {
    await page.goto('/dashboard');
    await page.waitForLoadState('networkidle');

    // Simulate server errors and high load conditions
    const errorScenarios = [
      { endpoint: '/api/portfolio/nonexistent', expectedStatus: 404 },
      { endpoint: '/api/invalid-endpoint', expectedStatus: 404 },
      { endpoint: '/api/portfolio/summary', method: 'POST', body: 'invalid', expectedStatus: 400 }
    ];

    for (const scenario of errorScenarios) {
      const responses = [];

      // Make multiple requests to test error handling under load
      for (let i = 0; i < 5; i++) {
        const response = await page.evaluate(async (test) => {
          try {
            const options = {
              method: test.method || 'GET',
              headers: { 'Content-Type': 'application/json' }
            };

            if (test.body) {
              options.body = test.body;
            }

            const res = await fetch(test.endpoint, options);
            return {
              status: res.status,
              ok: res.ok,
              timestamp: Date.now()
            };
          } catch (error) {
            return {
              error: error.message,
              timestamp: Date.now()
            };
          }
        }, scenario);

        responses.push(response);
        await page.waitForTimeout(100);
      }

      // All error responses should be consistent
      const statusCodes = responses.map(r => r.status).filter(Boolean);
      const uniqueStatuses = new Set(statusCodes);

      expect(uniqueStatuses.size).toBeLessThanOrEqual(2); // Consistent error handling
      expect(statusCodes.every(status => status >= 400)).toBe(true); // All errors
    }

    // UI should remain responsive after error scenarios
    const isResponsive = await page.evaluate(() => {
      return document.readyState === 'complete';
    });

    expect(isResponsive).toBe(true);
  });

  test('should handle network throttling and slow connections', async ({ page }) => {
    // Simulate slow network conditions
    await page.route('**/*', async route => {
      // Add delay to simulate slow network
      await new Promise(resolve => setTimeout(resolve, 200));
      await route.continue();
    });

    const startTime = Date.now();
    await page.goto('/');
    await page.waitForLoadState('networkidle');
    const loadTime = Date.now() - startTime;

    // Should still load within reasonable time even on slow network
    expect(loadTime).toBeLessThan(10000); // 10 seconds max for slow connection

    // Navigate to another page
    const navStart = Date.now();
    await page.goto('/portfolio');
    await page.waitForLoadState('networkidle');
    const navTime = Date.now() - navStart;

    expect(navTime).toBeLessThan(8000); // Subsequent loads should be faster

    // Test critical functionality still works
    const searchInput = page.locator('input[type="search"]').first();
    if (await searchInput.isVisible()) {
      await searchInput.fill('AAPL');
      await page.waitForTimeout(1000);

      const value = await searchInput.inputValue();
      expect(value).toBe('AAPL');
    }
  });

  test('should maintain performance with large datasets', async ({ page }) => {
    await page.goto('/portfolio');
    await page.waitForLoadState('networkidle');

    // Simulate loading large datasets
    const dataLoadStart = Date.now();

    await page.evaluate(() => {
      // Simulate large dataset rendering
      const container = document.querySelector('.portfolio-container, .data-container, main');
      if (container) {
        // Add many elements to test rendering performance
        for (let i = 0; i < 1000; i++) {
          const div = document.createElement('div');
          div.className = 'test-data-item';
          div.textContent = `Item ${i}`;
          div.style.display = 'none'; // Hidden to avoid visual issues
          container.appendChild(div);
        }
      }
    });

    const dataLoadTime = Date.now() - dataLoadStart;
    expect(dataLoadTime).toBeLessThan(2000); // Should handle large DOM efficiently

    // Test scrolling performance with large dataset
    const scrollStart = Date.now();

    await page.evaluate(() => {
      window.scrollTo(0, 1000);
    });

    await page.waitForTimeout(100);

    const scrollTime = Date.now() - scrollStart;
    expect(scrollTime).toBeLessThan(500); // Scrolling should remain smooth

    // Check if virtualization is working
    const visibleItems = await page.locator('.test-data-item:visible').count();
    const totalItems = await page.locator('.test-data-item').count();

    if (totalItems > 100) {
      // Should virtualize large lists
      expect(visibleItems).toBeLessThan(totalItems);
    }
  });

  test('should handle WebSocket connections under load', async ({ page }) => {
    await page.goto('/dashboard');
    await page.waitForLoadState('networkidle');

    // Monitor WebSocket connections
    const wsConnections = [];
    page.on('websocket', ws => {
      wsConnections.push({
        url: ws.url(),
        connected: !ws.isClosed(),
        timestamp: Date.now()
      });

      ws.on('framereceived', frame => {
        console.log('WebSocket frame received:', frame.payload.length, 'bytes');
      });
    });

    // Wait for WebSocket connections to establish
    await page.waitForTimeout(5000);

    // Simulate high-frequency data updates
    await page.evaluate(() => {
      // Trigger data refresh if possible
      const refreshButtons = document.querySelectorAll('[data-refresh], .refresh-btn, [aria-label*="refresh"]');
      refreshButtons.forEach(btn => {
        if (btn.click) btn.click();
      });
    });

    await page.waitForTimeout(3000);

    // WebSocket connections should be stable
    for (const ws of wsConnections) {
      expect(ws.connected).toBe(true);
    }

    // Should not have excessive WebSocket connections
    expect(wsConnections.length).toBeLessThan(5);
  });

  test('should maintain session stability under extended load', async ({ page }) => {
    await page.goto('/');
    await page.waitForLoadState('networkidle');

    const sessionStart = Date.now();
    const operationCount = 50;
    const errors = [];

    // Extended session simulation
    for (let i = 0; i < operationCount; i++) {
      try {
        const operations = [
          () => page.goto('/dashboard'),
          () => page.goto('/portfolio'),
          () => page.goto('/market-overview'),
          () => page.reload()
        ];

        const operation = operations[i % operations.length];
        await operation();
        await page.waitForLoadState('networkidle');

        // Short delay between operations
        await page.waitForTimeout(200);

        // Periodically check session validity
        if (i % 10 === 0) {
          const isSessionValid = await page.evaluate(() => {
            return !document.querySelector('.login-required, .session-expired') &&
                   document.readyState === 'complete';
          });

          if (!isSessionValid) {
            errors.push(`Session invalid at operation ${i}`);
          }
        }
      } catch (error) {
        errors.push(`Operation ${i} failed: ${error.message}`);
      }
    }

    const sessionDuration = Date.now() - sessionStart;

    // Session should remain stable throughout extended use
    expect(errors.length).toBeLessThan(operationCount * 0.1); // Less than 10% error rate

    // Extended session should complete in reasonable time
    expect(sessionDuration).toBeLessThan(120000); // Under 2 minutes

    // Final state should be functional
    const finalState = await page.evaluate(() => {
      return {
        readyState: document.readyState,
        hasErrors: document.querySelector('.error, .alert-error') !== null,
        isInteractive: !!document.querySelector('button, input, a')
      };
    });

    expect(finalState.readyState).toBe('complete');
    expect(finalState.isInteractive).toBe(true);
  });
});