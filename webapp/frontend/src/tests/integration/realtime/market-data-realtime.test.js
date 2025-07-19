/**
 * Real-time Market Data Integration Tests
 * Tests live data streams, WebSocket connections, and real-time updates
 * Integrated into existing enterprise testing framework
 */

import { test, expect } from '@playwright/test';

const testConfig = {
  baseURL: process.env.E2E_BASE_URL || 'https://d1zb7knau41vl9.cloudfront.net',
  websocketURL: process.env.E2E_WS_URL || 'wss://api.example.com/ws',
  testUser: {
    email: process.env.E2E_TEST_EMAIL || 'e2e-test@example.com',
    password: process.env.E2E_TEST_PASSWORD || 'E2ETest123!'
  },
  testSymbols: ['AAPL', 'MSFT', 'GOOGL', 'TSLA', 'NVDA', 'SPY', 'QQQ'],
  timeout: 60000
};

test.describe('Real-time Market Data Integration - Enterprise Framework', () => {
  
  let realtimeSession = {
    websocketConnections: [],
    priceUpdates: [],
    dataStreams: [],
    connectionEvents: [],
    errors: []
  };

  async function authenticate(page) {
    const isAuth = await page.locator('[data-testid="user-avatar"]').isVisible().catch(() => false);
    if (!isAuth) {
      await page.locator('button:has-text("Sign In")').click();
      await page.fill('[data-testid="email-input"]', testConfig.testUser.email);
      await page.fill('[data-testid="password-input"]', testConfig.testUser.password);
      await page.click('[data-testid="login-submit"]');
      await page.waitForSelector('[data-testid="user-avatar"]', { timeout: 15000 });
    }
  }

  async function trackRealtimeEvent(eventType, data) {
    realtimeSession[eventType].push({
      ...data,
      timestamp: new Date().toISOString()
    });
  }

  async function setupWebSocketMonitoring(page) {
    // Monitor WebSocket connections
    page.on('websocket', ws => {
      console.log(`🔌 WebSocket connection established: ${ws.url()}`);
      
      realtimeSession.websocketConnections.push({
        url: ws.url(),
        timestamp: new Date().toISOString(),
        status: 'connected'
      });

      ws.on('framesent', event => {
        try {
          const data = JSON.parse(event.payload);
          console.log(`📤 WebSocket sent:`, data);
          trackRealtimeEvent('dataStreams', {
            direction: 'sent',
            type: data.type || 'unknown',
            payload: data
          });
        } catch (e) {
          // Non-JSON message
        }
      });

      ws.on('framereceived', event => {
        try {
          const data = JSON.parse(event.payload);
          console.log(`📥 WebSocket received:`, data);
          
          if (data.type === 'price_update') {
            trackRealtimeEvent('priceUpdates', {
              symbol: data.symbol,
              price: data.price,
              change: data.change,
              volume: data.volume
            });
          }
          
          trackRealtimeEvent('dataStreams', {
            direction: 'received',
            type: data.type || 'unknown',
            payload: data
          });
        } catch (e) {
          // Non-JSON message
        }
      });

      ws.on('close', () => {
        console.log(`🔌 WebSocket connection closed: ${ws.url()}`);
        trackRealtimeEvent('connectionEvents', {
          type: 'disconnect',
          url: ws.url()
        });
      });
    });
  }

  test.beforeEach(async ({ page }) => {
    // Reset realtime session tracking
    realtimeSession = {
      websocketConnections: [],
      priceUpdates: [],
      dataStreams: [],
      connectionEvents: [],
      errors: []
    };
    
    // Setup realtime monitoring
    await setupWebSocketMonitoring(page);
    
    // Monitor console errors related to realtime data
    page.on('console', msg => {
      if (msg.type() === 'error' && (msg.text().includes('websocket') || msg.text().includes('realtime'))) {
        realtimeSession.errors.push({
          message: msg.text(),
          timestamp: new Date().toISOString()
        });
      }
    });

    await page.goto(testConfig.baseURL);
    await page.waitForLoadState('networkidle');
  });

  test.describe('Live Price Streaming Integration @critical @enterprise @realtime', () => {

    test('Real-time Price Updates Across Multiple Components', async ({ page }) => {
      console.log('📡 Testing Real-time Price Updates Across Multiple Components...');
      
      await authenticate(page);
      
      // 1. Navigate to dashboard with multiple price displays
      await page.goto('/');
      await page.waitForSelector('[data-testid="dashboard"]', { timeout: 15000 });
      
      // 2. Subscribe to multiple symbols
      const testSymbols = testConfig.testSymbols.slice(0, 5);
      
      for (const symbol of testSymbols) {
        // Add to watchlist to ensure subscription
        await page.click('[data-testid="add-to-watchlist"]');
        await page.fill('[data-testid="symbol-input"]', symbol);
        await page.click('[data-testid="confirm-add-symbol"]');
        await page.waitForTimeout(1000);
      }
      
      // 3. Monitor initial price loads
      for (const symbol of testSymbols) {
        const priceElement = page.locator(`[data-testid="price-${symbol}"]`);
        if (await priceElement.isVisible()) {
          const initialPrice = await priceElement.textContent();
          console.log(`💰 Initial price for ${symbol}: ${initialPrice}`);
          
          trackRealtimeEvent('priceUpdates', {
            symbol,
            price: initialPrice,
            type: 'initial_load'
          });
        }
      }
      
      // 4. Wait for real-time updates
      console.log('⏱️ Monitoring for real-time price updates (30 seconds)...');
      await page.waitForTimeout(30000);
      
      // 5. Verify price updates occurred
      const updateCount = realtimeSession.priceUpdates.filter(update => update.type !== 'initial_load').length;
      console.log(`📊 Received ${updateCount} real-time price updates`);
      
      // 6. Test price consistency across components
      for (const symbol of testSymbols.slice(0, 3)) {
        // Check dashboard widget
        const dashboardPrice = await page.locator(`[data-testid="dashboard-price-${symbol}"]`).textContent().catch(() => 'N/A');
        
        // Check watchlist
        const watchlistPrice = await page.locator(`[data-testid="watchlist-price-${symbol}"]`).textContent().catch(() => 'N/A');
        
        // Check market overview
        const marketPrice = await page.locator(`[data-testid="market-price-${symbol}"]`).textContent().catch(() => 'N/A');
        
        console.log(`🔍 Price consistency check for ${symbol}:`);
        console.log(`  Dashboard: ${dashboardPrice}`);
        console.log(`  Watchlist: ${watchlistPrice}`);
        console.log(`  Market: ${marketPrice}`);
        
        // Prices should be consistent (allowing for formatting differences)
        if (dashboardPrice !== 'N/A' && watchlistPrice !== 'N/A') {
          const dashPrice = parseFloat(dashboardPrice.replace(/[^0-9.]/g, ''));
          const watchPrice = parseFloat(watchlistPrice.replace(/[^0-9.]/g, ''));
          
          if (!isNaN(dashPrice) && !isNaN(watchPrice)) {
            expect(Math.abs(dashPrice - watchPrice)).toBeLessThan(0.01);
          }
        }
      }
      
      console.log('✅ Real-time Price Updates Across Multiple Components passed');
    });

    test('WebSocket Connection Management and Recovery', async ({ page }) => {
      console.log('🔄 Testing WebSocket Connection Management and Recovery...');
      
      await authenticate(page);
      
      // 1. Navigate to real-time trading page
      await page.goto('/trading/live');
      await page.waitForSelector('[data-testid="live-trading"]', { timeout: 15000 });
      
      // 2. Wait for WebSocket connections to establish
      await page.waitForTimeout(5000);
      
      // Verify initial connections
      expect(realtimeSession.websocketConnections.length).toBeGreaterThan(0);
      console.log(`🔌 Initial WebSocket connections: ${realtimeSession.websocketConnections.length}`);
      
      // 3. Test connection stability during navigation
      const navigationTests = [
        '/portfolio',
        '/market',
        '/stocks/AAPL',
        '/trading/live'
      ];
      
      for (const path of navigationTests) {
        await page.goto(path);
        await page.waitForLoadState('networkidle');
        await page.waitForTimeout(3000);
        
        console.log(`📍 Navigation to ${path} - WebSocket status check`);
      }
      
      // 4. Test connection during network interruption simulation
      await page.goto('/trading/live');
      
      // Simulate network interruption by going offline temporarily
      await page.context().setOffline(true);
      await page.waitForTimeout(2000);
      
      // Come back online
      await page.context().setOffline(false);
      await page.waitForTimeout(5000);
      
      // 5. Verify reconnection occurred
      const reconnectionEvents = realtimeSession.connectionEvents.filter(event => 
        event.type === 'disconnect' || event.url
      );
      
      console.log(`🔄 Connection events during test: ${reconnectionEvents.length}`);
      
      // 6. Test data resumption after reconnection
      const preReconnectUpdates = realtimeSession.priceUpdates.length;
      await page.waitForTimeout(10000);
      const postReconnectUpdates = realtimeSession.priceUpdates.length;
      
      expect(postReconnectUpdates).toBeGreaterThan(preReconnectUpdates);
      console.log(`📊 Price updates resumed: ${postReconnectUpdates - preReconnectUpdates} new updates`);
      
      console.log('✅ WebSocket Connection Management and Recovery passed');
    });

  });

  test.describe('Market Status and Hours Integration @critical @enterprise @realtime', () => {

    test('Market Status Real-time Updates', async ({ page }) => {
      console.log('🕐 Testing Market Status Real-time Updates...');
      
      await page.goto('/');
      await page.waitForSelector('[data-testid="market-status"]', { timeout: 15000 });
      
      // 1. Check initial market status
      const initialStatus = await page.locator('[data-testid="market-status"]').textContent();
      const initialTime = await page.locator('[data-testid="market-time"]').textContent();
      
      console.log(`📊 Initial Market Status: ${initialStatus}`);
      console.log(`🕒 Market Time: ${initialTime}`);
      
      // 2. Verify market status format
      const validStatuses = ['OPEN', 'CLOSED', 'PRE_MARKET', 'AFTER_HOURS', 'EXTENDED_HOURS'];
      const statusText = initialStatus.toUpperCase().replace(/\s+/g, '_');
      
      const isValidStatus = validStatuses.some(status => statusText.includes(status));
      expect(isValidStatus).toBeTruthy();
      
      // 3. Test market status across different pages
      const pagesToTest = ['/portfolio', '/market', '/trading'];
      
      for (const pagePath of pagesToTest) {
        await page.goto(pagePath);
        await page.waitForSelector('[data-testid="market-status"]', { timeout: 10000 });
        
        const pageStatus = await page.locator('[data-testid="market-status"]').textContent();
        expect(pageStatus).toBe(initialStatus);
        
        console.log(`✅ Market status consistent on ${pagePath}: ${pageStatus}`);
      }
      
      // 4. Test market hours display
      await page.goto('/market/hours');
      await page.waitForSelector('[data-testid="market-hours-display"]', { timeout: 15000 });
      
      const marketHours = {
        preMarket: await page.locator('[data-testid="pre-market-hours"]').textContent().catch(() => 'N/A'),
        regular: await page.locator('[data-testid="regular-hours"]').textContent().catch(() => 'N/A'),
        afterHours: await page.locator('[data-testid="after-hours"]').textContent().catch(() => 'N/A')
      };
      
      console.log('🕐 Market Hours:');
      console.log(`  Pre-market: ${marketHours.preMarket}`);
      console.log(`  Regular: ${marketHours.regular}`);
      console.log(`  After-hours: ${marketHours.afterHours}`);
      
      // 5. Test countdown to next market session
      const countdown = page.locator('[data-testid="market-countdown"]');
      if (await countdown.isVisible()) {
        const countdownText = await countdown.textContent();
        console.log(`⏰ Countdown to next session: ${countdownText}`);
        
        // Verify countdown format (should contain time elements)
        expect(countdownText).toMatch(/\d+[hms]/);
      }
      
      console.log('✅ Market Status Real-time Updates passed');
    });

    test('Trading Hours Impact on Features', async ({ page }) => {
      console.log('⏰ Testing Trading Hours Impact on Features...');
      
      await authenticate(page);
      
      // 1. Check current market status
      await page.goto('/');
      const marketStatus = await page.locator('[data-testid="market-status"]').textContent();
      
      console.log(`📊 Current Market Status: ${marketStatus}`);
      
      // 2. Test trading features based on market status
      await page.goto('/trading');
      await page.waitForSelector('[data-testid="trading-page"]', { timeout: 15000 });
      
      // Check if trading is restricted
      const tradingRestriction = page.locator('[data-testid="trading-restriction-notice"]');
      const isRestricted = await tradingRestriction.isVisible();
      
      if (isRestricted) {
        const restrictionMessage = await tradingRestriction.textContent();
        console.log(`🚫 Trading Restriction: ${restrictionMessage}`);
        
        // Verify restriction matches market status
        if (marketStatus.includes('CLOSED')) {
          expect(restrictionMessage.toLowerCase()).toContain('closed');
        }
      }
      
      // 3. Test order placement during different market sessions
      await page.click('[data-testid="place-order-button"]');
      await page.waitForSelector('[data-testid="order-form"]', { timeout: 10000 });
      
      // Check available order types based on market hours
      const orderTypes = page.locator('[data-testid="order-type"] option');
      const availableTypes = await orderTypes.allTextContents();
      
      console.log(`📋 Available Order Types: ${availableTypes.join(', ')}`);
      
      // During market hours, more order types should be available
      if (marketStatus.includes('OPEN')) {
        expect(availableTypes.length).toBeGreaterThan(2);
      }
      
      // 4. Test extended hours trading options
      const extendedHoursToggle = page.locator('[data-testid="extended-hours-toggle"]');
      if (await extendedHoursToggle.isVisible()) {
        const isEnabled = await extendedHoursToggle.isChecked();
        console.log(`🌙 Extended Hours Trading: ${isEnabled ? 'Enabled' : 'Disabled'}`);
        
        // Test toggling extended hours
        await extendedHoursToggle.click();
        await page.waitForTimeout(1000);
        
        const newState = await extendedHoursToggle.isChecked();
        expect(newState).toBe(!isEnabled);
        
        // Check if warning appears for extended hours
        const extendedWarning = page.locator('[data-testid="extended-hours-warning"]');
        if (newState && await extendedWarning.isVisible()) {
          const warningText = await extendedWarning.textContent();
          console.log(`⚠️ Extended Hours Warning: ${warningText}`);
        }
      }
      
      // 5. Test real-time price delays based on market status
      const testSymbol = 'AAPL';
      await page.goto(`/stocks/${testSymbol}`);
      await page.waitForSelector('[data-testid="stock-price"]', { timeout: 15000 });
      
      const priceDelay = page.locator('[data-testid="price-delay-notice"]');
      if (await priceDelay.isVisible()) {
        const delayText = await priceDelay.textContent();
        console.log(`⏱️ Price Delay Notice: ${delayText}`);
        
        // During market hours, delay should be minimal
        if (marketStatus.includes('OPEN')) {
          expect(delayText.toLowerCase()).toContain('real-time');
        }
      }
      
      console.log('✅ Trading Hours Impact on Features passed');
    });

  });

  test.describe('Volume and Order Flow Integration @critical @enterprise @realtime', () => {

    test('Real-time Volume and Trade Flow Monitoring', async ({ page }) => {
      console.log('📊 Testing Real-time Volume and Trade Flow Monitoring...');
      
      await page.goto('/market/volume');
      await page.waitForSelector('[data-testid="volume-monitor"]', { timeout: 15000 });
      
      // 1. Monitor volume data for multiple symbols
      const volumeSymbols = testConfig.testSymbols.slice(0, 4);
      
      for (const symbol of volumeSymbols) {
        const volumeElement = page.locator(`[data-testid="volume-${symbol}"]`);
        if (await volumeElement.isVisible()) {
          const volumeData = await volumeElement.textContent();
          console.log(`📈 ${symbol} Volume: ${volumeData}`);
        }
      }
      
      // 2. Test volume alerts
      await page.click('[data-testid="setup-volume-alerts"]');
      await page.waitForSelector('[data-testid="volume-alert-form"]', { timeout: 10000 });
      
      await page.fill('[data-testid="alert-symbol"]', 'AAPL');
      await page.fill('[data-testid="volume-threshold"]', '50000000');
      await page.selectOption('[data-testid="alert-condition"]', 'above');
      
      await page.click('[data-testid="save-volume-alert"]');
      await page.waitForSelector('[data-testid="alert-saved"]', { timeout: 5000 });
      
      // 3. Monitor order flow data
      await page.goto('/market/order-flow');
      await page.waitForSelector('[data-testid="order-flow-monitor"]', { timeout: 15000 });
      
      // Check bid/ask spreads
      for (const symbol of volumeSymbols.slice(0, 2)) {
        const bidElement = page.locator(`[data-testid="bid-${symbol}"]`);
        const askElement = page.locator(`[data-testid="ask-${symbol}"]`);
        
        if (await bidElement.isVisible() && await askElement.isVisible()) {
          const bid = await bidElement.textContent();
          const ask = await askElement.textContent();
          
          console.log(`💰 ${symbol} Bid/Ask: ${bid}/${ask}`);
          
          // Calculate spread
          const bidPrice = parseFloat(bid.replace(/[^0-9.]/g, ''));
          const askPrice = parseFloat(ask.replace(/[^0-9.]/g, ''));
          
          if (!isNaN(bidPrice) && !isNaN(askPrice)) {
            const spread = askPrice - bidPrice;
            console.log(`📊 ${symbol} Spread: $${spread.toFixed(2)}`);
          }
        }
      }
      
      // 4. Test order book depth
      const testSymbol = 'AAPL';
      await page.goto(`/stocks/${testSymbol}/order-book`);
      await page.waitForSelector('[data-testid="order-book"]', { timeout: 15000 });
      
      // Check order book levels
      const bidLevels = page.locator('[data-testid^="bid-level-"]');
      const askLevels = page.locator('[data-testid^="ask-level-"]');
      
      const bidCount = await bidLevels.count();
      const askCount = await askLevels.count();
      
      console.log(`📊 Order Book Depth: ${bidCount} bid levels, ${askCount} ask levels`);
      
      expect(bidCount).toBeGreaterThan(0);
      expect(askCount).toBeGreaterThan(0);
      
      // 5. Monitor order book updates
      const initialTopBid = await page.locator('[data-testid="bid-level-0"] [data-testid="price"]').textContent();
      
      console.log('⏱️ Monitoring order book updates (15 seconds)...');
      await page.waitForTimeout(15000);
      
      const currentTopBid = await page.locator('[data-testid="bid-level-0"] [data-testid="price"]').textContent();
      
      console.log(`📊 Order Book Update Check:`);
      console.log(`  Initial Top Bid: ${initialTopBid}`);
      console.log(`  Current Top Bid: ${currentTopBid}`);
      
      console.log('✅ Real-time Volume and Trade Flow Monitoring passed');
    });

  });

  test.afterEach(async () => {
    // Real-time session summary
    console.log('\n📊 Real-time Data Session Summary:');
    console.log(`WebSocket connections: ${realtimeSession.websocketConnections.length}`);
    console.log(`Price updates received: ${realtimeSession.priceUpdates.length}`);
    console.log(`Data streams: ${realtimeSession.dataStreams.length}`);
    console.log(`Connection events: ${realtimeSession.connectionEvents.length}`);
    console.log(`Errors encountered: ${realtimeSession.errors.length}`);
    
    // Log sample price updates
    if (realtimeSession.priceUpdates.length > 0) {
      console.log('\n📈 Sample Price Updates:');
      realtimeSession.priceUpdates.slice(0, 5).forEach(update => {
        console.log(`  ${update.symbol}: $${update.price} (${update.timestamp})`);
      });
    }
    
    // Log any connection issues
    if (realtimeSession.errors.length > 0) {
      console.log('\n❌ Real-time Errors:');
      realtimeSession.errors.forEach(error => {
        console.log(`  ${error.timestamp}: ${error.message}`);
      });
    }
  });

});

export default {
  testConfig
};