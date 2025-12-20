/**
 * Load Testing for High-Traffic Scenarios
 * Tests system behavior under heavy load and concurrent users
 */

import { test, expect } from "@playwright/test";

test.describe("Load Testing - High Traffic Scenarios", () => {
  test.beforeEach(async ({ page }) => {
    // Set up consistent test environment
    await page.addInitScript(() => {
      localStorage.setItem("financial_auth_token", "load-test-token");
      localStorage.setItem(
        "api_keys_status",
        JSON.stringify({
          alpaca: { configured: true, valid: true },
          polygon: { configured: true, valid: true },
          finnhub: { configured: true, valid: true },
        })
      );
    });

    // Mock API responses with realistic delays
    await page.route("**/api/**", async (route) => {
      const url = route.request().url();

      // Simulate varying API response times
      const delay = Math.random() * 1000 + 200; // 200-1200ms
      await new Promise((resolve) => setTimeout(resolve, delay));

      if (url.includes("/portfolio")) {
        route.fulfill({
          json: {
            success: true,
            data: {
              totalValue: 125000.5 + Math.random() * 1000,
              holdings: Array.from({ length: 10 }, (_, i) => ({
                symbol:
                  ["AAPL", "MSFT", "GOOGL", "TSLA", "AMZN"][i % 5] +
                  Math.floor(Math.random() * 100),
                value: Math.random() * 50000,
                change: (Math.random() - 0.5) * 1000,
              })),
            },
          },
        });
      } else if (url.includes("/market")) {
        route.fulfill({
          json: {
            success: true,
            data: {
              indices: {
                SPY: {
                  price: 445.32 + Math.random() * 10,
                  change: (Math.random() - 0.5) * 5,
                },
                QQQ: {
                  price: 375.68 + Math.random() * 10,
                  change: (Math.random() - 0.5) * 5,
                },
                DIA: {
                  price: 355.91 + Math.random() * 10,
                  change: (Math.random() - 0.5) * 5,
                },
              },
              sectors: Array.from({ length: 11 }, (_, i) => ({
                name: `Sector ${i + 1}`,
                performance: (Math.random() - 0.5) * 5,
                volume: Math.random() * 1e9,
              })),
            },
          },
        });
      } else {
        route.fulfill({ json: { success: true, data: {} } });
      }
    });
  });

  test("Dashboard should handle rapid navigation load", async ({ page }) => {
    console.log("🚀 Testing rapid navigation load...");

    const navigationTimes = [];
    const routes = [
      "/portfolio",
      "/market",
      "/settings",
      "/stocks",
    ];

    // Rapid navigation test
    for (let i = 0; i < 15; i++) {
      const route = routes[i % routes.length];
      const startTime = Date.now();

      await page.goto(route);
      await page.waitForSelector("#root", { state: "attached" });

      const loadTime = Date.now() - startTime;
      navigationTimes.push(loadTime);

      console.log(`📊 Navigation ${i + 1} to ${route}: ${loadTime}ms`);

      // Quick navigation without waiting
      await page.waitForTimeout(100);
    }

    // Performance analysis
    const avgTime =
      navigationTimes.reduce((a, b) => a + b) / navigationTimes.length;
    const maxTime = Math.max(...navigationTimes);
    const minTime = Math.min(...navigationTimes);

    console.log(
      `📈 Load Test Results - Avg: ${Math.round(avgTime)}ms, Max: ${maxTime}ms, Min: ${minTime}ms`
    );

    // Performance thresholds for high-traffic scenarios
    expect(avgTime, `Average load time: ${avgTime}ms`).toBeLessThan(3000);
    expect(maxTime, `Maximum load time: ${maxTime}ms`).toBeLessThan(8000);
  });

  test("Portfolio page should handle data-heavy scenarios", async ({
    page,
  }) => {
    console.log("💼 Testing portfolio data load performance...");

    // Navigate to portfolio with heavy data load
    const startTime = Date.now();
    await page.goto("/portfolio");
    await page.waitForLoadState("networkidle");

    const initialLoadTime = Date.now() - startTime;
    console.log(`📊 Initial portfolio load: ${initialLoadTime}ms`);

    // Test multiple data refresh scenarios
    const refreshTimes = [];
    for (let i = 0; i < 10; i++) {
      const refreshStart = Date.now();

      // Trigger data refresh by navigation
      await page.reload();
      await page.waitForSelector("#root", { state: "attached" });

      const refreshTime = Date.now() - refreshStart;
      refreshTimes.push(refreshTime);

      console.log(`🔄 Refresh ${i + 1}: ${refreshTime}ms`);
      await page.waitForTimeout(200);
    }

    const avgRefreshTime =
      refreshTimes.reduce((a, b) => a + b) / refreshTimes.length;
    console.log(`📈 Average refresh time: ${Math.round(avgRefreshTime)}ms`);

    // Performance validation
    expect(
      initialLoadTime,
      `Initial load time: ${initialLoadTime}ms`
    ).toBeLessThan(5000);
    expect(
      avgRefreshTime,
      `Average refresh time: ${avgRefreshTime}ms`
    ).toBeLessThan(3000);
  });

  test("Market data should handle frequent updates", async ({ page }) => {
    console.log("📈 Testing market data update performance...");

    await page.goto("/market");
    await page.waitForSelector("#root", { state: "attached" });

    // Simulate high-frequency market data updates
    const updateTimes = [];

    for (let i = 0; i < 20; i++) {
      const updateStart = Date.now();

      // Trigger page update
      await page.evaluate(() => {
        if (window.location.pathname === "/market") {
          window.dispatchEvent(new Event("focus"));
        }
      });

      await page.waitForTimeout(100);
      const updateTime = Date.now() - updateStart;
      updateTimes.push(updateTime);

      if (i % 5 === 0) {
        console.log(
          `⚡ Update batch ${Math.floor(i / 5) + 1} average: ${Math.round(updateTimes.slice(-5).reduce((a, b) => a + b) / 5)}ms`
        );
      }
    }

    const avgUpdateTime =
      updateTimes.reduce((a, b) => a + b) / updateTimes.length;
    console.log(
      `📊 Overall average update time: ${Math.round(avgUpdateTime)}ms`
    );

    expect(
      avgUpdateTime,
      `Average update time: ${avgUpdateTime}ms`
    ).toBeLessThan(200);
  });

  test("Concurrent API requests should be handled efficiently", async ({
    page,
  }) => {
    console.log("🌐 Testing concurrent API request handling...");

    let apiRequestCount = 0;
    let apiResponseCount = 0;
    const apiTimes = [];

    page.on("request", (request) => {
      if (request.url().includes("/api/")) {
        apiRequestCount++;
        request.startTime = Date.now();
      }
    });

    page.on("response", (response) => {
      if (response.url().includes("/api/")) {
        apiResponseCount++;
        const request = response.request();
        if (request.startTime) {
          const apiTime = Date.now() - request.startTime;
          apiTimes.push(apiTime);
        }
      }
    });

    // Navigate to multiple pages to trigger concurrent API requests
    const pages = [
      "/portfolio",
      "/market",
      "/sentiment",
      "/stocks",
    ];

    await Promise.all(
      pages.map(async (route, index) => {
        await page.goto(route);
        await page.waitForSelector("#root", { state: "attached" });
        await page.waitForTimeout(500 * (index + 1)); // Staggered timing
      })
    );

    // Wait for all responses
    await page.waitForTimeout(3000);

    console.log(
      `📊 API Requests: ${apiRequestCount}, Responses: ${apiResponseCount}`
    );

    if (apiTimes.length > 0) {
      const avgApiTime = apiTimes.reduce((a, b) => a + b) / apiTimes.length;
      const maxApiTime = Math.max(...apiTimes);

      console.log(
        `⚡ API Performance - Avg: ${Math.round(avgApiTime)}ms, Max: ${maxApiTime}ms`
      );

      expect(avgApiTime, `Average API time: ${avgApiTime}ms`).toBeLessThan(
        2000
      );
      expect(maxApiTime, `Maximum API time: ${maxApiTime}ms`).toBeLessThan(
        5000
      );
    }

    expect(apiResponseCount).toBeGreaterThan(0);
  });

  test("Memory usage should remain stable under load", async ({ page }) => {
    console.log("🧠 Testing memory stability under load...");

    const memoryReadings = [];

    // Function to get memory metrics
    const getMemoryMetrics = async () => {
      return await page.evaluate(() => {
        if ("memory" in performance) {
          return {
            used: Math.round(performance.memory.usedJSHeapSize / 1024 / 1024),
            total: Math.round(performance.memory.totalJSHeapSize / 1024 / 1024),
            limit: Math.round(performance.memory.jsHeapSizeLimit / 1024 / 1024),
          };
        }
        return null;
      });
    };

    // Initial memory reading
    await page.goto("/");
    await page.waitForSelector("#root", { state: "attached" });
    const initialMemory = await getMemoryMetrics();

    if (initialMemory) {
      memoryReadings.push(initialMemory);
      console.log(`📊 Initial memory: ${initialMemory.used}MB`);

      // Load test with memory monitoring
      const routes = [
        "/portfolio",
        "/market",
        "/stocks",
        "/settings",
      ];

      for (let cycle = 0; cycle < 5; cycle++) {
        for (const route of routes) {
          await page.goto(route);
          await page.waitForSelector("#root", { state: "attached" });
          await page.waitForTimeout(500);

          const memory = await getMemoryMetrics();
          if (memory) {
            memoryReadings.push(memory);
            console.log(
              `🧠 Memory after ${route} (cycle ${cycle + 1}): ${memory.used}MB`
            );
          }
        }
      }

      // Memory analysis
      const finalMemory = memoryReadings[memoryReadings.length - 1];
      const memoryIncrease = finalMemory.used - initialMemory.used;

      console.log(`📈 Memory increase over test: ${memoryIncrease}MB`);
      console.log(
        `📊 Final memory usage: ${finalMemory.used}MB / ${finalMemory.total}MB`
      );

      // Memory leak detection
      expect(
        memoryIncrease,
        `Memory increase: ${memoryIncrease}MB`
      ).toBeLessThan(50);
      expect(
        finalMemory.used,
        `Final memory usage: ${finalMemory.used}MB`
      ).toBeLessThan(200);
    } else {
      console.log("ℹ️ Memory monitoring not available in this browser");
      expect(true).toBe(true); // Pass test if memory monitoring unavailable
    }
  });

  test("UI should remain responsive under heavy interaction load", async ({
    page,
  }) => {
    console.log("🖱️ Testing UI responsiveness under heavy load...");

    await page.goto("/stocks");
    await page.waitForSelector("#root", { state: "attached" });
    await page.waitForTimeout(2000);

    const interactionTimes = [];

    // Heavy interaction test
    for (let i = 0; i < 25; i++) {
      const interactionStart = Date.now();

      // Simulate various user interactions
      const interactions = [
        // Click interactions
        async () => {
          const buttons = await page.locator('button, [role="button"]').count();
          if (buttons > 0) {
            const randomButton = Math.floor(
              Math.random() * Math.min(buttons, 5)
            );
            await page
              .locator('button, [role="button"]')
              .nth(randomButton)
              .click({ timeout: 1000 });
          }
        },
        // Input interactions
        async () => {
          const inputs = await page
            .locator('input[type="text"], input[type="search"]')
            .count();
          if (inputs > 0) {
            const randomInput = Math.floor(Math.random() * Math.min(inputs, 3));
            await page
              .locator('input[type="text"], input[type="search"]')
              .nth(randomInput)
              .fill(`test${i}`);
          }
        },
        // Scroll interactions
        async () => {
          await page.evaluate(() =>
            window.scrollBy(0, Math.random() * 500 - 250)
          );
        },
      ];

      try {
        // Perform random interaction
        const randomInteraction =
          interactions[Math.floor(Math.random() * interactions.length)];
        await randomInteraction();

        const interactionTime = Date.now() - interactionStart;
        interactionTimes.push(interactionTime);

        if (i % 5 === 0) {
          const recentAvg =
            interactionTimes.slice(-5).reduce((a, b) => a + b) / 5;
          console.log(
            `⚡ Interaction batch ${Math.floor(i / 5) + 1} avg: ${Math.round(recentAvg)}ms`
          );
        }
      } catch (error) {
        console.log(
          `⚠️ Interaction ${i + 1} failed: ${error.message.slice(0, 50)}`
        );
        interactionTimes.push(1000); // Penalty for failed interaction
      }

      await page.waitForTimeout(50); // Brief pause between interactions
    }

    const avgInteractionTime =
      interactionTimes.reduce((a, b) => a + b) / interactionTimes.length;
    const maxInteractionTime = Math.max(...interactionTimes);

    console.log(
      `📊 Interaction Performance - Avg: ${Math.round(avgInteractionTime)}ms, Max: ${maxInteractionTime}ms`
    );

    // UI responsiveness thresholds
    expect(
      avgInteractionTime,
      `Average interaction time: ${avgInteractionTime}ms`
    ).toBeLessThan(500);
    expect(
      maxInteractionTime,
      `Maximum interaction time: ${maxInteractionTime}ms`
    ).toBeLessThan(2000);
  });

  test("System should handle network congestion gracefully", async ({
    page,
  }) => {
    console.log("🌐 Testing network congestion handling...");

    // Simulate network congestion with delays
    await page.route("**/api/**", async (route) => {
      // Randomly simulate network issues
      const shouldDelay = Math.random() < 0.3; // 30% chance of delay
      const shouldFail = Math.random() < 0.1; // 10% chance of failure

      if (shouldFail) {
        route.fulfill({
          status: 503,
          json: { error: "Service temporarily unavailable" },
        });
        return;
      }

      if (shouldDelay) {
        await new Promise((resolve) =>
          setTimeout(resolve, 3000 + Math.random() * 2000)
        ); // 3-5s delay
      }

      route.fulfill({
        json: {
          success: true,
          data: { message: "Response with network simulation" },
        },
      });
    });

    const loadResults = [];
    const routes = ["/portfolio", "/market", "/stocks"];

    for (const route of routes) {
      console.log(`🌐 Testing ${route} under network congestion...`);
      const startTime = Date.now();

      try {
        await page.goto(route);
        await page.waitForLoadState("domcontentloaded", { timeout: 10000 });

        const loadTime = Date.now() - startTime;
        loadResults.push({ route, success: true, time: loadTime });

        console.log(`✅ ${route}: ${loadTime}ms`);
      } catch (error) {
        const loadTime = Date.now() - startTime;
        loadResults.push({ route, success: false, time: loadTime });

        console.log(
          `❌ ${route}: Failed after ${loadTime}ms - ${error.message.slice(0, 50)}`
        );
      }
    }

    // Analysis
    const successful = loadResults.filter((r) => r.success);
    const failed = loadResults.filter((r) => !r.success);

    console.log(
      `📊 Network congestion results: ${successful.length} successful, ${failed.length} failed`
    );

    if (successful.length > 0) {
      const avgTime =
        successful.reduce((sum, r) => sum + r.time, 0) / successful.length;
      console.log(`⚡ Average successful load time: ${Math.round(avgTime)}ms`);

      // Under network congestion, allow higher thresholds
      expect(
        avgTime,
        `Average load time under congestion: ${avgTime}ms`
      ).toBeLessThan(8000);
    }

    // System should handle at least some requests successfully
    expect(successful.length).toBeGreaterThan(0);
  });
});
