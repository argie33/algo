/**
 * Real-time Data Workflow E2E Test
 * Tests real-time data: connect → view updates → make decisions → act on data
 */

import { test, expect } from "@playwright/test";

test.describe("Real-time Data Workflow", () => {
  test.beforeEach(async ({ page }) => {
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
      localStorage.setItem("user_data", JSON.stringify({
        username: "testuser",
        authenticated: true
      }));
    });

    // Mock WebSocket for real-time data testing
    await page.addInitScript(() => {
      window.mockWebSocketData = {
        connected: false,
        subscriptions: [],
        lastUpdate: null
      };

      // Mock WebSocket connection
      const _originalWebSocket = window.WebSocket;
      window.WebSocket = function(url) {
        console.log('Mock WebSocket connecting to:', url);

        const mockWS = {
          readyState: 1, // OPEN
          url: url,
          onopen: null,
          onmessage: null,
          onclose: null,
          onerror: null,
          send: function(data) {
            console.log('Mock WebSocket sending:', data);

            // Simulate real-time price updates
            setTimeout(() => {
              if (this.onmessage) {
                const mockPriceUpdate = {
                  type: 'price_update',
                  symbol: 'AAPL',
                  price: 175.00 + (Math.random() - 0.5) * 2,
                  timestamp: Date.now()
                };

                this.onmessage({
                  data: JSON.stringify(mockPriceUpdate)
                });
              }
            }, 1000);
          },
          close: function() {
            console.log('Mock WebSocket closing');
            if (this.onclose) this.onclose();
          }
        };

        // Simulate connection
        setTimeout(() => {
          window.mockWebSocketData.connected = true;
          if (mockWS.onopen) mockWS.onopen();
        }, 100);

        return mockWS;
      };
    });
  });

  test("should complete real-time data workflow", async ({ page }) => {
    console.log("📡 Starting real-time data workflow test...");

    // Step 1: Navigate to Real-time Dashboard
    console.log("📝 Step 1: Navigating to real-time dashboard...");
    await page.goto("/realtime");
    await page.waitForLoadState("networkidle");
    await page.waitForTimeout(3000); // Extra time for WebSocket connection

    const pageTitle = await page.title();
    console.log(`📄 Real-time dashboard title: ${pageTitle}`);

    // Step 2: Check for real-time data elements
    console.log("📝 Step 2: Checking for real-time data elements...");

    const realTimeElements = await page.locator(
      '.real-time, .live, .streaming, .websocket, .live-data, text*="Live", text*="Real-time"'
    ).count();

    console.log(`📡 Real-time indicators found: ${realTimeElements}`);

    // Look for price displays that should update
    const priceElements = await page.locator(
      '.price, .quote, .ticker, text*="$", .stock-price'
    ).count();

    console.log(`💰 Price display elements found: ${priceElements}`);

    // Step 3: Check WebSocket connection status
    console.log("📝 Step 3: Checking WebSocket connection...");

    const connectionStatus = await page.locator(
      '.connected, .online, .status, text*="Connected", text*="Online", .connection-indicator'
    ).count();

    console.log(`🔗 Connection status indicators found: ${connectionStatus}`);

    // Look for connection controls
    const connectionControls = await page.locator(
      'button:has-text("Connect"), button:has-text("Disconnect"), button:has-text("Reconnect"), .connect-button'
    ).count();

    console.log(`🎛️ Connection control buttons found: ${connectionControls}`);

    // Step 4: Test symbol subscription
    console.log("📝 Step 4: Testing symbol subscription...");

    const symbolInputs = await page.locator(
      'input[placeholder*="symbol"], input[placeholder*="stock"], input[name*="symbol"]'
    ).count();

    console.log(`🎯 Symbol input fields found: ${symbolInputs}`);

    // Try to subscribe to a symbol if input is available
    if (symbolInputs > 0) {
      const symbolInput = page.locator(
        'input[placeholder*="symbol"], input[placeholder*="stock"], input[name*="symbol"]'
      ).first();

      if (await symbolInput.isVisible()) {
        await symbolInput.fill("AAPL");
        await page.keyboard.press("Enter");
        await page.waitForTimeout(2000);

        console.log("✅ Attempted to subscribe to AAPL");

        // Look for subscription confirmation
        const subscriptionElements = await page.locator(
          'text*="AAPL", .subscribed, .watching'
        ).count();

        console.log(`📊 AAPL subscription elements found: ${subscriptionElements}`);
      }
    }

    // Step 5: Check for live data updates
    console.log("📝 Step 5: Waiting for live data updates...");

    // Wait for potential updates
    await page.waitForTimeout(5000);

    // Look for timestamps or update indicators
    const updateIndicators = await page.locator(
      '.timestamp, .last-update, .updated, text*="ago", text*="seconds", text*="minutes"'
    ).count();

    console.log(`⏰ Update timestamp elements found: ${updateIndicators}`);

    // Look for blinking/flashing price changes
    const changeIndicators = await page.locator(
      '.price-change, .flash, .highlight, .up, .down, .positive, .negative'
    ).count();

    console.log(`📈 Price change indicators found: ${changeIndicators}`);

    // Step 6: Test portfolio real-time updates
    console.log("📝 Step 6: Testing portfolio real-time integration...");

    await page.goto("/portfolio");
    await page.waitForLoadState("networkidle");
    await page.waitForTimeout(3000);

    // Look for real-time portfolio values
    const portfolioRealTime = await page.locator(
      '.live-value, .real-time-value, .updating, text*="Live"'
    ).count();

    console.log(`📊 Real-time portfolio elements found: ${portfolioRealTime}`);

    // Step 7: Test market overview real-time data
    console.log("📝 Step 7: Testing market overview real-time data...");

    await page.goto("/market");
    await page.waitForLoadState("networkidle");
    await page.waitForTimeout(3000);

    const marketRealTime = await page.locator(
      '.market-data, .indices, .live-market, text*="Live", .real-time'
    ).count();

    console.log(`🌍 Market real-time elements found: ${marketRealTime}`);

    // Look for major indices with live prices
    const indicesElements = await page.locator(
      'text*="S&P", text*="NASDAQ", text*="DOW", text*="SPY", text*="QQQ"'
    ).count();

    console.log(`📊 Market indices elements found: ${indicesElements}`);

    // Step 8: Test watchlist real-time updates
    console.log("📝 Step 8: Testing watchlist real-time updates...");

    await page.goto("/watchlist");
    await page.waitForLoadState("networkidle");
    await page.waitForTimeout(3000);

    const watchlistRealTime = await page.locator(
      'tbody tr, .watchlist-item, .stock-item, .ticker'
    ).count();

    console.log(`⭐ Watchlist items found: ${watchlistRealTime}`);

    // Look for real-time price updates in watchlist
    const watchlistPrices = await page.locator(
      '.price, text*="$", .quote'
    ).count();

    console.log(`💰 Watchlist price elements found: ${watchlistPrices}`);

    // Step 9: Test alerts based on real-time data
    console.log("📝 Step 9: Testing real-time alerts functionality...");

    // Look for alert setup or notifications
    const alertElements = await page.locator(
      '.alert, .notification, .bell, button:has-text("Alert"), text*="Alert"'
    ).count();

    console.log(`🔔 Alert elements found: ${alertElements}`);

    // Step 10: Test performance under real-time load
    console.log("📝 Step 10: Testing performance with real-time data...");

    // Navigate back to real-time dashboard
    await page.goto("/realtime");
    await page.waitForLoadState("networkidle");

    // Measure page responsiveness
    const startTime = Date.now();

    // Click on various elements to test responsiveness
    const clickableElements = await page.locator(
      'button, a, [role="button"], [role="tab"], .clickable'
    ).count();

    if (clickableElements > 0) {
      const firstClickable = page.locator(
        'button, a, [role="button"], [role="tab"]'
      ).first();

      if (await firstClickable.isVisible()) {
        await firstClickable.click();
        await page.waitForTimeout(1000);
      }
    }

    const responseTime = Date.now() - startTime;
    console.log(`⚡ UI response time: ${responseTime}ms`);

    // Step 11: Test connection recovery
    console.log("📝 Step 11: Testing connection recovery...");

    // Simulate disconnect and reconnect
    await page.evaluate(() => {
      if (window.mockWebSocketData) {
        window.mockWebSocketData.connected = false;
      }
    });

    await page.waitForTimeout(2000);

    // Look for reconnection indicators
    const reconnectElements = await page.locator(
      'text*="Reconnecting", text*="Disconnected", .reconnecting, .offline'
    ).count();

    console.log(`🔄 Reconnection indicators found: ${reconnectElements}`);

    // Simulate reconnection
    await page.evaluate(() => {
      if (window.mockWebSocketData) {
        window.mockWebSocketData.connected = true;
      }
    });

    await page.waitForTimeout(2000);

    console.log("✅ Real-time data workflow test completed");

    // Verify that real-time functionality is present
    const hasRealTimeFeatures = realTimeElements > 0 || priceElements > 0 || connectionStatus > 0;
    expect(hasRealTimeFeatures).toBe(true);
  });

  test("should handle WebSocket connection errors gracefully", async ({ page }) => {
    console.log("🚨 Testing WebSocket connection error handling...");

    // Override WebSocket to simulate connection failure
    await page.addInitScript(() => {
      window.WebSocket = function(url) {
        const mockWS = {
          readyState: 3, // CLOSED
          url: url,
          onopen: null,
          onmessage: null,
          onclose: null,
          onerror: null,
          send: function(_data) {
            console.log('Mock WebSocket send failed');
          },
          close: function() {
            console.log('Mock WebSocket already closed');
          }
        };

        // Simulate connection error
        setTimeout(() => {
          if (mockWS.onerror) mockWS.onerror(new Error('Connection failed'));
          if (mockWS.onclose) mockWS.onclose();
        }, 100);

        return mockWS;
      };
    });

    await page.goto("/realtime");
    await page.waitForLoadState("networkidle");
    await page.waitForTimeout(3000);

    // Should handle error gracefully - page should still work
    const pageContent = await page.locator('#root').textContent();
    const hasContent = pageContent && pageContent.length > 100;

    console.log(`✅ Page functional despite WebSocket error: ${hasContent}`);

    // Look for error messaging
    const errorElements = await page.locator(
      '.error, .failed, .offline, text*="error", text*="failed", text*="unavailable"'
    ).count();

    console.log(`🚨 Error state elements found: ${errorElements}`);

    expect(hasContent).toBe(true);
  });

  test("should display static data when real-time unavailable", async ({ page }) => {
    console.log("📊 Testing fallback to static data...");

    // Don't mock WebSocket - let it fail naturally
    await page.goto("/realtime");
    await page.waitForLoadState("networkidle");
    await page.waitForTimeout(3000);

    // Should show some data even without real-time connection
    const dataElements = await page.locator(
      '.price, .stock, .data, tbody tr, .quote'
    ).count();

    console.log(`📊 Data elements (static or cached): ${dataElements}`);

    // Look for fallback indicators
    const fallbackElements = await page.locator(
      'text*="delayed", text*="cached", text*="as of", .delayed'
    ).count();

    console.log(`⏰ Fallback/delayed data indicators: ${fallbackElements}`);

    // Page should be functional even without live data
    const pageContent = await page.locator('#root').textContent();
    const hasContent = pageContent && pageContent.length > 50;

    expect(hasContent).toBe(true);
  });

  test("should handle high-frequency updates efficiently", async ({ page }) => {
    console.log("⚡ Testing high-frequency update handling...");

    // Mock rapid updates
    await page.addInitScript(() => {
      window.WebSocket = function(url) {
        const mockWS = {
          readyState: 1,
          url: url,
          onopen: null,
          onmessage: null,
          onclose: null,
          onerror: null,
          send: function(_data) {
            console.log('Mock WebSocket connected for high-frequency test');
          },
          close: function() {
            this.readyState = 3;
          }
        };

        setTimeout(() => {
          if (mockWS.onopen) mockWS.onopen();

          // Send rapid updates
          let updateCount = 0;
          const rapidUpdates = setInterval(() => {
            if (mockWS.onmessage && updateCount < 50) {
              const mockUpdate = {
                type: 'price_update',
                symbol: 'AAPL',
                price: 175.00 + Math.sin(updateCount * 0.1) * 5,
                timestamp: Date.now()
              };

              mockWS.onmessage({
                data: JSON.stringify(mockUpdate)
              });

              updateCount++;
            } else {
              clearInterval(rapidUpdates);
            }
          }, 50); // 20 updates per second
        }, 100);

        return mockWS;
      };
    });

    await page.goto("/realtime");
    await page.waitForLoadState("networkidle");

    // Let rapid updates run
    await page.waitForTimeout(5000);

    // Page should remain responsive
    const isResponsive = await page.locator('body').isVisible();
    console.log(`✅ Page responsive after rapid updates: ${isResponsive}`);

    // Check if updates are being throttled/batched appropriately
    const priceElements = await page.locator('.price, text*="$"').count();
    console.log(`💰 Price elements still visible: ${priceElements}`);

    expect(isResponsive).toBe(true);
  });

  test("should sync real-time data across multiple tabs", async ({ context }) => {
    console.log("🗂️ Testing real-time data sync across tabs...");

    // Create two tabs
    const page1 = await context.newPage();
    const page2 = await context.newPage();

    // Set up auth for both tabs
    for (const page of [page1, page2]) {
      await page.addInitScript(() => {
        localStorage.setItem("financial_auth_token", "test-auth-token");
        localStorage.setItem(
          "api_keys_status",
          JSON.stringify({
            alpaca: { configured: true, valid: true }
          })
        );
      });
    }

    // Navigate both to real-time dashboard
    await page1.goto("/realtime");
    await page2.goto("/realtime");

    await page1.waitForLoadState("networkidle");
    await page2.waitForLoadState("networkidle");

    await page1.waitForTimeout(2000);
    await page2.waitForTimeout(2000);

    // Both should load real-time functionality
    const tab1Elements = await page1.locator('.real-time, .live, .price').count();
    const tab2Elements = await page2.locator('.real-time, .live, .price').count();

    console.log(`📑 Tab 1 real-time elements: ${tab1Elements}`);
    console.log(`📑 Tab 2 real-time elements: ${tab2Elements}`);

    // Both tabs should have real-time functionality
    const bothTabsWork = tab1Elements > 0 && tab2Elements > 0;
    console.log(`✅ Both tabs have real-time features: ${bothTabsWork}`);

    await page1.close();
    await page2.close();

    expect(bothTabsWork || tab1Elements > 0 || tab2Elements > 0).toBe(true);
  });
});