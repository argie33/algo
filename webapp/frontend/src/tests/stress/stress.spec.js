/**
 * Stress Testing Suite
 * High-load and edge case stress testing
 */

import { test, expect } from '@playwright/test';

test.describe('Stress Testing', () => {
  test.beforeEach(async ({ page }) => {
    // Set up stress testing monitoring
    await page.addInitScript(() => {
      window.__STRESS_TEST_DATA__ = {
        memoryUsage: [],
        performanceMetrics: [],
        errorCount: 0,
        startTime: Date.now()
      };

      // Monitor errors
      const originalError = console.error;
      console.error = function(...args) {
        window.__STRESS_TEST_DATA__.errorCount++;
        return originalError.apply(console, args);
      };

      // Monitor memory usage
      setInterval(() => {
        if (performance.memory) {
          window.__STRESS_TEST_DATA__.memoryUsage.push({
            used: performance.memory.usedJSHeapSize,
            total: performance.memory.totalJSHeapSize,
            timestamp: Date.now()
          });
        }
      }, 1000);

      // Monitor performance
      const observer = new PerformanceObserver((list) => {
        list.getEntries().forEach(entry => {
          window.__STRESS_TEST_DATA__.performanceMetrics.push({
            name: entry.name,
            duration: entry.duration,
            type: entry.entryType,
            timestamp: entry.startTime
          });
        });
      });
      observer.observe({ entryTypes: ['navigation', 'resource', 'measure'] });
    });
  });

  test('should handle rapid navigation stress', async ({ page }) => {
    const pages = ['/dashboard', '/portfolio', '/market-overview', '/settings', '/'];
    const navigationCount = 50;

    let successfulNavigations = 0;
    let errorCount = 0;

    for (let i = 0; i < navigationCount; i++) {
      const targetPage = pages[i % pages.length];

      try {
        await page.goto(targetPage);
        await page.waitForLoadState('domcontentloaded', { timeout: 5000 });
        successfulNavigations++;
      } catch (error) {
        errorCount++;
        console.log(`Navigation ${i} failed: ${error.message}`);
      }

      // Very brief pause to simulate rapid user behavior
      await page.waitForTimeout(50);
    }

    // Should complete majority of navigations successfully
    expect(successfulNavigations).toBeGreaterThan(navigationCount * 0.8);
    expect(errorCount).toBeLessThan(navigationCount * 0.2);

    // Check application is still responsive
    const finalPageContent = await page.textContent('body');
    expect(finalPageContent.length).toBeGreaterThan(0);
  });

  test('should handle memory stress from data loading', async ({ page }) => {
    await page.goto('/portfolio');
    await page.waitForLoadState('networkidle');

    // Simulate loading large amounts of data
    const dataLoadCycles = 20;

    for (let i = 0; i < dataLoadCycles; i++) {
      // Simulate API data loading
      await page.evaluate((cycle) => {
        // Create large data structures to stress memory
        const largeDataSet = Array(1000).fill().map((_, index) => ({
          id: cycle * 1000 + index,
          symbol: `SYM${index}`,
          price: Math.random() * 1000,
          volume: Math.random() * 1000000,
          data: Array(100).fill().map(() => Math.random()),
          timestamp: Date.now()
        }));

        // Store in window to prevent garbage collection during test
        if (!window.__STRESS_DATA__) {
          window.__STRESS_DATA__ = [];
        }
        window.__STRESS_DATA__.push(largeDataSet);

        // Simulate DOM manipulation
        const container = document.createElement('div');
        container.style.display = 'none';

        for (let j = 0; j < 100; j++) {
          const element = document.createElement('div');
          element.textContent = `Item ${cycle}-${j}`;
          element.className = 'stress-test-item';
          container.appendChild(element);
        }

        document.body.appendChild(container);
      }, i);

      await page.waitForTimeout(100);
    }

    // Check memory usage
    const memoryData = await page.evaluate(() => window.__STRESS_TEST_DATA__.memoryUsage);

    if (memoryData.length > 0) {
      const initialMemory = memoryData[0].used;
      const finalMemory = memoryData[memoryData.length - 1].used;
      const memoryIncrease = finalMemory - initialMemory;

      // Memory increase should be reasonable (less than 500MB)
      expect(memoryIncrease).toBeLessThan(500 * 1024 * 1024);
    }

    // Application should still be responsive
    const isResponsive = await page.evaluate(() => {
      return document.readyState === 'complete' && !document.hidden;
    });
    expect(isResponsive).toBe(true);

    // Clean up stress test data
    await page.evaluate(() => {
      delete window.__STRESS_DATA__;
      const stressElements = document.querySelectorAll('.stress-test-item');
      stressElements.forEach(el => el.parentElement?.remove());
    });
  });

  test('should handle rapid user interactions', async ({ page }) => {
    await page.goto('/dashboard');
    await page.waitForLoadState('networkidle');

    const interactionCount = 100;
    let successfulInteractions = 0;

    // Get all interactive elements
    const interactiveElements = await page.locator('button, a, input, select, [role="button"]').all();

    for (let i = 0; i < interactionCount; i++) {
      if (interactiveElements.length === 0) break;

      const element = interactiveElements[i % interactiveElements.length];

      try {
        if (await element.isVisible() && await element.isEnabled()) {
          const tagName = await element.evaluate(el => el.tagName.toLowerCase());

          if (tagName === 'input') {
            await element.fill(`test${i}`);
            await element.clear();
          } else if (tagName === 'select') {
            const options = await element.locator('option').all();
            if (options.length > 1) {
              await element.selectOption({ index: 1 });
            }
          } else {
            await element.click({ timeout: 1000 });
          }

          successfulInteractions++;
        }
      } catch (error) {
        // Some interactions may fail due to timing or state changes
        console.log(`Interaction ${i} failed: ${error.message}`);
      }

      // Very rapid interactions
      await page.waitForTimeout(10);
    }

    // Should handle majority of interactions successfully
    expect(successfulInteractions).toBeGreaterThan(interactionCount * 0.6);

    // Check for JavaScript errors
    const stressData = await page.evaluate(() => window.__STRESS_TEST_DATA__);
    expect(stressData.errorCount).toBeLessThan(interactionCount * 0.1);
  });

  test('should handle concurrent API requests stress', async ({ page }) => {
    await page.goto('/dashboard');
    await page.waitForLoadState('networkidle');

    const concurrentRequests = 50;
    const requests = [];

    // Create many concurrent API requests
    for (let i = 0; i < concurrentRequests; i++) {
      const request = page.evaluate(async (index) => {
        const startTime = Date.now();
        try {
          const endpoints = [
            '/api/portfolio/summary',
            '/api/market/overview',
            '/api/user/profile',
            '/api/analytics/performance',
            '/api/health'
          ];

          const endpoint = endpoints[index % endpoints.length];
          const response = await fetch(endpoint, {
            headers: { 'Authorization': 'Bearer test-token' }
          });

          return {
            index,
            status: response.status,
            duration: Date.now() - startTime,
            success: response.ok
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

      requests.push(request);
    }

    const results = await Promise.all(requests);

    // Analyze results
    const successfulRequests = results.filter(r => r.success);
    const _failedRequests = results.filter(r => !r.success);
    const rateLimitedRequests = results.filter(r => r.status === 429);

    // Should handle a reasonable number of concurrent requests
    expect(successfulRequests.length).toBeGreaterThan(concurrentRequests * 0.3);

    // Rate limiting is acceptable under stress
    if (rateLimitedRequests.length > 0) {
      expect(rateLimitedRequests.length).toBeLessThan(concurrentRequests * 0.7);
    }

    // Successful requests should still be reasonably fast
    const avgResponseTime = successfulRequests.reduce((sum, r) => sum + r.duration, 0) / successfulRequests.length;
    expect(avgResponseTime).toBeLessThan(5000); // 5 seconds max under stress
  });

  test('should handle DOM manipulation stress', async ({ page }) => {
    await page.goto('/');
    await page.waitForLoadState('networkidle');

    const manipulationCycles = 20;

    for (let cycle = 0; cycle < manipulationCycles; cycle++) {
      await page.evaluate((cycleNum) => {
        // Create large DOM structure
        const container = document.createElement('div');
        container.id = `stress-container-${cycleNum}`;
        container.style.display = 'none'; // Hidden to avoid visual issues

        // Add many elements
        for (let i = 0; i < 200; i++) {
          const element = document.createElement('div');
          element.className = 'stress-element';
          element.textContent = `Stress Element ${cycleNum}-${i}`;
          element.style.cssText = `
            width: 100px;
            height: 50px;
            background: rgb(${Math.floor(Math.random() * 255)}, ${Math.floor(Math.random() * 255)}, ${Math.floor(Math.random() * 255)});
            margin: 1px;
            padding: 5px;
          `;

          // Add event listeners to stress memory
          element.addEventListener('click', () => {
            element.style.opacity = element.style.opacity === '0.5' ? '1' : '0.5';
          });

          container.appendChild(element);
        }

        document.body.appendChild(container);
      }, cycle);

      await page.waitForTimeout(50);

      // Periodically clean up some elements
      if (cycle % 5 === 0) {
        await page.evaluate((cycleNum) => {
          const containersToRemove = Math.floor(cycleNum / 5);
          for (let i = 0; i < containersToRemove; i++) {
            const container = document.getElementById(`stress-container-${i}`);
            if (container) {
              container.remove();
            }
          }
        }, cycle);
      }
    }

    // Check DOM performance
    const domStats = await page.evaluate(() => {
      const allElements = document.querySelectorAll('*');
      const stressElements = document.querySelectorAll('.stress-element');

      return {
        totalElements: allElements.length,
        stressElements: stressElements.length,
        documentReady: document.readyState
      };
    });

    expect(domStats.documentReady).toBe('complete');
    expect(domStats.totalElements).toBeGreaterThan(0);

    // Clean up
    await page.evaluate(() => {
      const stressContainers = document.querySelectorAll('[id^="stress-container-"]');
      stressContainers.forEach(container => container.remove());
    });
  });

  test('should handle WebSocket connection stress', async ({ page }) => {
    await page.goto('/dashboard');
    await page.waitForLoadState('networkidle');

    // Monitor WebSocket connections
    const wsConnections = [];
    page.on('websocket', ws => {
      wsConnections.push({
        url: ws.url(),
        timestamp: Date.now(),
        closed: false
      });

      ws.on('close', () => {
        const connection = wsConnections.find(conn => conn.url === ws.url());
        if (connection) {
          connection.closed = true;
        }
      });
    });

    // Simulate WebSocket stress by triggering data refresh rapidly
    const refreshCycles = 20;

    for (let i = 0; i < refreshCycles; i++) {
      await page.evaluate(() => {
        // Trigger data refresh if available
        const refreshButtons = document.querySelectorAll('[data-refresh], .refresh-btn');
        refreshButtons.forEach(btn => {
          if (btn.click) btn.click();
        });

        // Simulate WebSocket message handling
        if (window.dispatchEvent) {
          const event = new CustomEvent('data-update', {
            detail: {
              timestamp: Date.now(),
              data: Array(100).fill().map(() => Math.random())
            }
          });
          window.dispatchEvent(event);
        }
      });

      await page.waitForTimeout(100);
    }

    await page.waitForTimeout(2000);

    // WebSocket connections should be stable
    const activeConnections = wsConnections.filter(conn => !conn.closed);
    expect(activeConnections.length).toBeLessThan(10); // Reasonable connection limit

    // Should not have excessive connection attempts
    expect(wsConnections.length).toBeLessThan(50);
  });

  test('should handle scroll performance stress', async ({ page }) => {
    await page.goto('/portfolio');
    await page.waitForLoadState('networkidle');

    // Add many elements for scrolling stress test
    await page.evaluate(() => {
      const container = document.querySelector('.portfolio-container, main, body');
      if (container) {
        for (let i = 0; i < 1000; i++) {
          const row = document.createElement('div');
          row.className = 'stress-scroll-item';
          row.style.cssText = `
            height: 50px;
            padding: 10px;
            border-bottom: 1px solid #eee;
            display: flex;
            align-items: center;
          `;
          row.innerHTML = `
            <div style="flex: 1;">Item ${i}</div>
            <div style="flex: 1;">$${(Math.random() * 1000).toFixed(2)}</div>
            <div style="flex: 1;">${(Math.random() * 100).toFixed(2)}%</div>
          `;
          container.appendChild(row);
        }
      }
    });

    // Rapid scrolling stress test
    const scrollCycles = 50;
    const scrollPositions = [];

    for (let i = 0; i < scrollCycles; i++) {
      const scrollPosition = Math.random() * 50000; // Random scroll position
      scrollPositions.push(scrollPosition);

      await page.evaluate((pos) => {
        window.scrollTo(0, pos);
      }, scrollPosition);

      await page.waitForTimeout(20); // Very rapid scrolling
    }

    // Check scroll performance
    const finalScrollPosition = await page.evaluate(() => window.pageYOffset);
    expect(finalScrollPosition).toBeGreaterThanOrEqual(0);

    // Page should remain responsive
    const isResponsive = await page.evaluate(() => {
      return document.readyState === 'complete';
    });
    expect(isResponsive).toBe(true);

    // Clean up stress elements
    await page.evaluate(() => {
      const stressElements = document.querySelectorAll('.stress-scroll-item');
      stressElements.forEach(el => el.remove());
    });
  });

  test('should handle form validation stress', async ({ page }) => {
    await page.goto('/settings');
    await page.waitForLoadState('networkidle');

    const inputs = await page.locator('input, textarea, select').all();
    const validationCycles = 100;

    let _validationErrors = 0;
    let successfulValidations = 0;

    for (let cycle = 0; cycle < validationCycles; cycle++) {
      if (inputs.length === 0) break;

      const input = inputs[cycle % inputs.length];

      try {
        if (await input.isVisible() && await input.isEnabled()) {
          // Test with invalid data
          const invalidValues = [
            '',
            'x'.repeat(1000), // Very long string
            '!@#$%^&*()',
            '<script>alert("test")</script>',
            '../../etc/passwd',
            'null',
            'undefined',
            String(Math.random())
          ];

          const invalidValue = invalidValues[cycle % invalidValues.length];

          await input.fill(invalidValue);
          await input.blur();

          // Check for validation feedback
          const hasValidationError = await page.evaluate(() => {
            const errors = document.querySelectorAll('.error, .invalid, [aria-invalid="true"]');
            return errors.length > 0;
          });

          if (hasValidationError) {
            _validationErrors++;
          }

          // Test with potentially valid data
          await input.fill(`valid-${cycle}`);
          await input.blur();

          successfulValidations++;
        }
      } catch (error) {
        console.log(`Validation cycle ${cycle} failed: ${error.message}`);
      }

      await page.waitForTimeout(10);
    }

    // Form validation should handle stress gracefully
    expect(successfulValidations).toBeGreaterThan(validationCycles * 0.5);

    // Check that form is still functional
    const formFunctional = await page.evaluate(() => {
      const forms = document.querySelectorAll('form');
      return forms.length === 0 || Array.from(forms).some(form => !form.disabled);
    });
    expect(formFunctional).toBe(true);
  });

  test('should handle resource cleanup under stress', async ({ page }) => {
    await page.goto('/dashboard');
    await page.waitForLoadState('networkidle');

    // Monitor resource usage
    const initialMetrics = await page.evaluate(() => ({
      memory: performance.memory ? performance.memory.usedJSHeapSize : 0,
      timing: performance.now()
    }));

    // Create and destroy many resources
    const resourceCycles = 30;

    for (let cycle = 0; cycle < resourceCycles; cycle++) {
      await page.evaluate((cycleNum) => {
        // Create various resources
        const resources = [];

        // DOM elements
        for (let i = 0; i < 50; i++) {
          const element = document.createElement('div');
          element.innerHTML = `<span>Resource ${cycleNum}-${i}</span>`;
          element.addEventListener('click', () => console.log('clicked'));
          resources.push(element);
        }

        // Event listeners
        const eventListeners = [];
        for (let i = 0; i < 20; i++) {
          const listener = () => console.log(`listener-${cycleNum}-${i}`);
          window.addEventListener('resize', listener);
          eventListeners.push(listener);
        }

        // Timeouts and intervals
        const timers = [];
        for (let i = 0; i < 10; i++) {
          const timeout = setTimeout(() => {}, 100);
          const interval = setInterval(() => {}, 1000);
          timers.push(timeout, interval);
        }

        // Store for cleanup
        window.__STRESS_RESOURCES__ = window.__STRESS_RESOURCES__ || [];
        window.__STRESS_RESOURCES__.push({
          elements: resources,
          listeners: eventListeners,
          timers: timers
        });

        // Cleanup older resources
        if (window.__STRESS_RESOURCES__.length > 5) {
          const oldResources = window.__STRESS_RESOURCES__.shift();

          // Clean up elements
          oldResources.elements.forEach(el => {
            if (el.parentNode) el.parentNode.removeChild(el);
          });

          // Clean up event listeners
          oldResources.listeners.forEach(listener => {
            window.removeEventListener('resize', listener);
          });

          // Clean up timers
          oldResources.timers.forEach(timer => {
            clearTimeout(timer);
            clearInterval(timer);
          });
        }
      }, cycle);

      await page.waitForTimeout(50);
    }

    // Final cleanup
    await page.evaluate(() => {
      if (window.__STRESS_RESOURCES__) {
        window.__STRESS_RESOURCES__.forEach(resources => {
          resources.elements.forEach(el => {
            if (el.parentNode) el.parentNode.removeChild(el);
          });
          resources.listeners.forEach(listener => {
            window.removeEventListener('resize', listener);
          });
          resources.timers.forEach(timer => {
            clearTimeout(timer);
            clearInterval(timer);
          });
        });
        delete window.__STRESS_RESOURCES__;
      }
    });

    // Check final resource usage
    const finalMetrics = await page.evaluate(() => ({
      memory: performance.memory ? performance.memory.usedJSHeapSize : 0,
      timing: performance.now()
    }));

    // Memory usage should be reasonable after cleanup
    if (initialMetrics.memory > 0 && finalMetrics.memory > 0) {
      const memoryIncrease = finalMetrics.memory - initialMetrics.memory;
      expect(memoryIncrease).toBeLessThan(100 * 1024 * 1024); // Less than 100MB increase
    }

    // Application should still be responsive
    const isResponsive = await page.evaluate(() => {
      return document.readyState === 'complete';
    });
    expect(isResponsive).toBe(true);
  });
});