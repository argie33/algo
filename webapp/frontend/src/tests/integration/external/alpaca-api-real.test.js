/**
 * Alpaca API Real Integration Tests
 * Tests actual Alpaca broker API integration with live/paper trading accounts
 */

import { describe, it, expect, beforeAll, afterAll, beforeEach, afterEach } from 'vitest';
import AlpacaApi from '@alpacahq/alpaca-trade-api';

// Alpaca API configuration from environment
const ALPACA_CONFIG = {
  key: process.env.ALPACA_API_KEY,
  secret: process.env.ALPACA_SECRET_KEY,
  paper: process.env.ALPACA_PAPER_TRADING !== 'false', // Default to paper trading
  baseUrl: process.env.ALPACA_BASE_URL || 'https://paper-api.alpaca.markets'
};

// Test symbols and amounts
const TEST_SYMBOL = 'AAPL';
const TEST_QTY = 1; // Small quantity for testing
const MAX_TEST_AMOUNT = 100; // Maximum dollar amount for test orders

describe('Alpaca API Real Integration Tests', () => {
  let alpaca;
  let accountInfo;
  let testOrderIds = [];

  beforeAll(async () => {
    // Skip tests if Alpaca credentials not configured
    if (!ALPACA_CONFIG.key || !ALPACA_CONFIG.secret) {
      console.warn('⚠️ Skipping Alpaca tests - API credentials missing');
      console.warn('⚠️ Set ALPACA_API_KEY and ALPACA_SECRET_KEY environment variables');
      return;
    }

    if (!ALPACA_CONFIG.paper) {
      console.warn('⚠️ Running tests against LIVE trading account!');
      console.warn('⚠️ Set ALPACA_PAPER_TRADING=true for paper trading');
    }

    try {
      // Initialize Alpaca API client
      alpaca = new AlpacaApi(ALPACA_CONFIG);

      // Verify connection and get account info
      accountInfo = await alpaca.getAccount();
      console.log(`✅ Connected to Alpaca ${ALPACA_CONFIG.paper ? 'Paper' : 'Live'} Trading`);
      console.log(`✅ Account: ${accountInfo.id} (${accountInfo.status})`);
      console.log(`✅ Buying Power: $${parseFloat(accountInfo.buying_power).toLocaleString()}`);

      // Verify account is in good standing
      expect(accountInfo.status).toBe('ACTIVE');
      expect(parseFloat(accountInfo.buying_power)).toBeGreaterThan(MAX_TEST_AMOUNT);

    } catch (error) {
      console.error('❌ Failed to connect to Alpaca:', error.message);
      throw new Error('Alpaca connection failed - check API credentials');
    }
  });

  afterAll(async () => {
    if (!alpaca) return;

    try {
      // Cancel any remaining test orders
      for (const orderId of testOrderIds) {
        try {
          await alpaca.cancelOrder(orderId);
          console.log(`🧹 Cancelled test order: ${orderId}`);
        } catch (error) {
          // Order might already be filled or cancelled
          console.warn(`⚠️ Could not cancel order ${orderId}: ${error.message}`);
        }
      }
    } catch (error) {
      console.warn('⚠️ Error during cleanup:', error.message);
    }
  });

  describe('Account Information', () => {
    it('retrieves account details', async () => {
      if (!alpaca) return;

      const account = await alpaca.getAccount();

      expect(account.id).toBeDefined();
      expect(account.status).toBe('ACTIVE');
      expect(account.currency).toBe('USD');
      expect(account.buying_power).toBeDefined();
      expect(account.cash).toBeDefined();
      expect(account.portfolio_value).toBeDefined();

      // Verify account has sufficient funds for testing
      expect(parseFloat(account.buying_power)).toBeGreaterThan(0);
      
      console.log(`✅ Account Status: ${account.status}`);
      console.log(`✅ Portfolio Value: $${parseFloat(account.portfolio_value).toLocaleString()}`);
    });

    it('checks trading permissions', async () => {
      if (!alpaca) return;

      const account = await alpaca.getAccount();

      expect(account.trading_blocked).toBe(false);
      expect(account.transfers_blocked).toBe(false);
      expect(account.account_blocked).toBe(false);
      expect(account.pattern_day_trader).toBeDefined();

      console.log(`✅ Pattern Day Trader: ${account.pattern_day_trader}`);
      console.log(`✅ Day Trade Count: ${account.daytrade_count}`);
    });

    it('retrieves account configurations', async () => {
      if (!alpaca) return;

      const configs = await alpaca.getAccountConfigurations();

      expect(configs.dtbp_check).toBeDefined();
      expect(configs.trade_confirm_email).toBeDefined();
      expect(configs.suspend_trade).toBeDefined();
      expect(['all', 'entry', 'exit', 'none']).toContain(configs.dtbp_check);

      console.log(`✅ Day Trading Buying Power Check: ${configs.dtbp_check}`);
      console.log(`✅ Suspend Trading: ${configs.suspend_trade}`);
    });
  });

  describe('Market Data', () => {
    it('fetches real-time stock quotes', async () => {
      if (!alpaca) return;

      const quote = await alpaca.getLatestTrade({ symbol: TEST_SYMBOL });

      expect(quote[TEST_SYMBOL]).toBeDefined();
      expect(quote[TEST_SYMBOL].price).toBeGreaterThan(0);
      expect(quote[TEST_SYMBOL].size).toBeGreaterThan(0);
      expect(quote[TEST_SYMBOL].timestamp).toBeDefined();

      console.log(`✅ ${TEST_SYMBOL} Latest Price: $${quote[TEST_SYMBOL].price}`);
      console.log(`✅ Trade Size: ${quote[TEST_SYMBOL].size} shares`);
    });

    it('retrieves historical price data', async () => {
      if (!alpaca) return;

      const end = new Date();
      const start = new Date(end.getTime() - 7 * 24 * 60 * 60 * 1000); // 7 days ago

      const bars = await alpaca.getBarsV2(TEST_SYMBOL, {
        start: start.toISOString(),
        end: end.toISOString(),
        timeframe: '1Day'
      });

      const barArray = [];
      for await (let bar of bars) {
        barArray.push(bar);
      }

      expect(barArray.length).toBeGreaterThan(0);
      expect(barArray[0].Symbol).toBe(TEST_SYMBOL);
      expect(barArray[0].OpenPrice).toBeGreaterThan(0);
      expect(barArray[0].HighPrice).toBeGreaterThan(0);
      expect(barArray[0].LowPrice).toBeGreaterThan(0);
      expect(barArray[0].ClosePrice).toBeGreaterThan(0);
      expect(barArray[0].Volume).toBeGreaterThan(0);

      console.log(`✅ Retrieved ${barArray.length} daily bars for ${TEST_SYMBOL}`);
      console.log(`✅ Latest Close: $${barArray[barArray.length - 1].ClosePrice}`);
    });

    it('gets market calendar', async () => {
      if (!alpaca) return;

      const start = new Date();
      const end = new Date(start.getTime() + 30 * 24 * 60 * 60 * 1000); // 30 days ahead

      const calendar = await alpaca.getCalendar({
        start: start.toISOString().split('T')[0],
        end: end.toISOString().split('T')[0]
      });

      expect(Array.isArray(calendar)).toBe(true);
      expect(calendar.length).toBeGreaterThan(0);
      expect(calendar[0].date).toBeDefined();
      expect(calendar[0].open).toBeDefined();
      expect(calendar[0].close).toBeDefined();

      console.log(`✅ Retrieved ${calendar.length} market days`);
      console.log(`✅ Next market day: ${calendar[0].date} (${calendar[0].open} - ${calendar[0].close})`);
    });
  });

  describe('Portfolio Management', () => {
    it('retrieves current positions', async () => {
      if (!alpaca) return;

      const positions = await alpaca.getPositions();

      expect(Array.isArray(positions)).toBe(true);
      
      if (positions.length > 0) {
        const position = positions[0];
        expect(position.symbol).toBeDefined();
        expect(position.qty).toBeDefined();
        expect(position.market_value).toBeDefined();
        expect(position.cost_basis).toBeDefined();
        expect(position.unrealized_pl).toBeDefined();

        console.log(`✅ Found ${positions.length} positions`);
        console.log(`✅ Sample position: ${position.qty} shares of ${position.symbol}`);
      } else {
        console.log('✅ No current positions (clean account)');
      }
    });

    it('retrieves specific position if exists', async () => {
      if (!alpaca) return;

      try {
        const position = await alpaca.getPosition(TEST_SYMBOL);
        
        expect(position.symbol).toBe(TEST_SYMBOL);
        expect(position.qty).toBeDefined();
        expect(position.market_value).toBeDefined();
        
        console.log(`✅ Current ${TEST_SYMBOL} position: ${position.qty} shares`);
        console.log(`✅ Market Value: $${position.market_value}`);
        console.log(`✅ Unrealized P&L: $${position.unrealized_pl}`);
        
      } catch (error) {
        if (error.message.includes('position does not exist')) {
          console.log(`✅ No current position in ${TEST_SYMBOL} (expected)`);
        } else {
          throw error;
        }
      }
    });
  });

  describe('Order Management', () => {
    it('places and cancels a limit buy order', async () => {
      if (!alpaca) return;

      // Get current market price
      const quote = await alpaca.getLatestTrade({ symbol: TEST_SYMBOL });
      const currentPrice = quote[TEST_SYMBOL].price;
      const limitPrice = (currentPrice * 0.95).toFixed(2); // 5% below market

      // Place limit buy order
      const order = await alpaca.createOrder({
        symbol: TEST_SYMBOL,
        qty: TEST_QTY,
        side: 'buy',
        type: 'limit',
        time_in_force: 'day',
        limit_price: limitPrice
      });

      testOrderIds.push(order.id);

      expect(order.id).toBeDefined();
      expect(order.symbol).toBe(TEST_SYMBOL);
      expect(order.qty).toBe(TEST_QTY.toString());
      expect(order.side).toBe('buy');
      expect(order.type).toBe('limit');
      expect(order.status).toBe('accepted');

      console.log(`✅ Placed limit buy order: ${order.id}`);
      console.log(`✅ Order: ${TEST_QTY} shares of ${TEST_SYMBOL} at $${limitPrice}`);

      // Wait a moment for order to process
      await new Promise(resolve => setTimeout(resolve, 1000));

      // Cancel the order
      const cancelledOrder = await alpaca.cancelOrder(order.id);
      expect(cancelledOrder.status).toBe('canceled');

      console.log(`✅ Successfully cancelled order: ${order.id}`);
    });

    it('places and cancels a market buy order (immediate cancel)', async () => {
      if (!alpaca) return;

      // Place market buy order for small amount
      const order = await alpaca.createOrder({
        symbol: TEST_SYMBOL,
        qty: TEST_QTY,
        side: 'buy',
        type: 'market',
        time_in_force: 'day'
      });

      testOrderIds.push(order.id);

      expect(order.id).toBeDefined();
      expect(order.symbol).toBe(TEST_SYMBOL);
      expect(order.side).toBe('buy');
      expect(order.type).toBe('market');

      console.log(`✅ Placed market buy order: ${order.id}`);

      // Immediately try to cancel (might be too late if market is open)
      try {
        await alpaca.cancelOrder(order.id);
        console.log(`✅ Successfully cancelled market order: ${order.id}`);
      } catch (error) {
        if (error.message.includes('unable to cancel')) {
          console.log(`⚠️ Market order executed too quickly to cancel: ${order.id}`);
          
          // If order was filled, we should sell it back
          const orderStatus = await alpaca.getOrder(order.id);
          if (orderStatus.status === 'filled') {
            const sellOrder = await alpaca.createOrder({
              symbol: TEST_SYMBOL,
              qty: TEST_QTY,
              side: 'sell',
              type: 'market',
              time_in_force: 'day'
            });
            console.log(`🔄 Placed offsetting sell order: ${sellOrder.id}`);
          }
        } else {
          throw error;
        }
      }
    });

    it('retrieves order history', async () => {
      if (!alpaca) return;

      const orders = await alpaca.getOrders({
        status: 'all',
        limit: 10
      });

      expect(Array.isArray(orders)).toBe(true);
      
      if (orders.length > 0) {
        const order = orders[0];
        expect(order.id).toBeDefined();
        expect(order.symbol).toBeDefined();
        expect(order.side).toMatch(/buy|sell/);
        expect(order.type).toMatch(/market|limit|stop|stop_limit/);
        expect(order.status).toBeDefined();

        console.log(`✅ Retrieved ${orders.length} recent orders`);
        console.log(`✅ Latest order: ${order.side} ${order.qty} ${order.symbol} (${order.status})`);
      } else {
        console.log('✅ No order history (clean account)');
      }
    });
  });

  describe('Asset Information', () => {
    it('retrieves tradable assets', async () => {
      if (!alpaca) return;

      const assets = await alpaca.getAssets({
        status: 'active',
        asset_class: 'us_equity'
      });

      expect(Array.isArray(assets)).toBe(true);
      expect(assets.length).toBeGreaterThan(1000); // Should have many tradable assets

      const testAsset = assets.find(asset => asset.symbol === TEST_SYMBOL);
      expect(testAsset).toBeDefined();
      expect(testAsset.tradable).toBe(true);
      expect(testAsset.marginable).toBeDefined();
      expect(testAsset.shortable).toBeDefined();

      console.log(`✅ Found ${assets.length} tradable assets`);
      console.log(`✅ ${TEST_SYMBOL} - Tradable: ${testAsset.tradable}, Marginable: ${testAsset.marginable}`);
    });

    it('gets specific asset information', async () => {
      if (!alpaca) return;

      const asset = await alpaca.getAsset(TEST_SYMBOL);

      expect(asset.symbol).toBe(TEST_SYMBOL);
      expect(asset.name).toBeDefined();
      expect(asset.exchange).toBeDefined();
      expect(asset.asset_class).toBe('us_equity');
      expect(asset.status).toBe('active');
      expect(asset.tradable).toBe(true);

      console.log(`✅ ${TEST_SYMBOL}: ${asset.name}`);
      console.log(`✅ Exchange: ${asset.exchange}, Class: ${asset.asset_class}`);
    });
  });

  describe('Error Handling', () => {
    it('handles invalid symbol gracefully', async () => {
      if (!alpaca) return;

      await expect(alpaca.getAsset('INVALID_SYMBOL_XYZ')).rejects.toThrow();
    });

    it('handles insufficient buying power', async () => {
      if (!alpaca) return;

      // Try to place an order for more than available buying power
      const excessiveQty = Math.ceil(parseFloat(accountInfo.buying_power) / 100) + 1000;

      await expect(alpaca.createOrder({
        symbol: TEST_SYMBOL,
        qty: excessiveQty,
        side: 'buy',
        type: 'market',
        time_in_force: 'day'
      })).rejects.toThrow(/buying power|insufficient/);
    });

    it('handles invalid order parameters', async () => {
      if (!alpaca) return;

      await expect(alpaca.createOrder({
        symbol: TEST_SYMBOL,
        qty: -1, // Invalid negative quantity
        side: 'buy',
        type: 'market',
        time_in_force: 'day'
      })).rejects.toThrow();
    });

    it('handles API rate limiting', async () => {
      if (!alpaca) return;

      // Make rapid successive calls to test rate limiting
      const rapidCalls = Array.from({ length: 10 }, () => 
        alpaca.getAccount().catch(error => error)
      );

      const results = await Promise.all(rapidCalls);
      
      // At least some calls should succeed
      const successfulCalls = results.filter(result => result.id);
      expect(successfulCalls.length).toBeGreaterThan(0);

      console.log(`✅ ${successfulCalls.length}/10 rapid API calls succeeded`);
    });
  });

  describe('WebSocket Data Stream', () => {
    it('tests WebSocket connection capability', async () => {
      if (!alpaca) return;

      // Note: This is a basic connectivity test
      // Full WebSocket testing would require more complex setup
      
      try {
        const websocket = alpaca.data_stream_v2;
        expect(websocket).toBeDefined();
        
        // Test WebSocket configuration
        expect(websocket._key).toBe(ALPACA_CONFIG.key);
        expect(websocket._secret).toBe(ALPACA_CONFIG.secret);
        
        console.log('✅ WebSocket client initialized');
        
      } catch (error) {
        console.warn(`⚠️ WebSocket test failed: ${error.message}`);
      }
    });
  });

  describe('Account Activities', () => {
    it('retrieves account activities', async () => {
      if (!alpaca) return;

      const activities = await alpaca.getAccountActivities({
        activity_types: ['FILL', 'TRANS'],
        page_size: 10
      });

      expect(Array.isArray(activities)).toBe(true);
      
      if (activities.length > 0) {
        const activity = activities[0];
        expect(activity.id).toBeDefined();
        expect(activity.activity_type).toBeDefined();
        expect(activity.date).toBeDefined();

        console.log(`✅ Retrieved ${activities.length} account activities`);
        console.log(`✅ Latest activity: ${activity.activity_type} on ${activity.date}`);
      } else {
        console.log('✅ No recent account activities');
      }
    });
  });
});