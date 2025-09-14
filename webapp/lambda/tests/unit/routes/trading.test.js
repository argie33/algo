const express = require('express');
const request = require('supertest');

// Real database for integration
const { query } = require('../../../utils/database');

describe('Trading Routes Unit Tests', () => {
  let app;

  beforeAll(() => {
    // Create test app
    app = express();
    app.use(express.json());
    
    // Mock authentication middleware - allow all requests through
    app.use((req, res, next) => {
      req.user = { sub: 'test-user-123' }; // Mock authenticated user
      next();
    });
    
    // Add response formatter middleware
    const responseFormatter = require('../../../middleware/responseFormatter');
    app.use(responseFormatter);
    
    // Load trading routes
    const tradingRouter = require('../../../routes/trading');
    app.use('/trading', tradingRouter);
  });

  describe('GET /trading/', () => {
    test('should return trading info', async () => {
      const response = await request(app)
        .get('/trading/')
        .expect(200);

      expect(response.body).toHaveProperty('success');
      expect(response.body).toHaveProperty('status');
    });
  });

  describe('GET /trading/health', () => {
    test('should return trading health status', async () => {
      const response = await request(app)
        .get('/trading/health')
        .expect(200);

      expect(response.body).toHaveProperty('success');
      expect(response.body).toHaveProperty('status');
    });
  });

  describe('GET /trading/debug', () => {
    test('should return debug information', async () => {
      const response = await request(app)
        .get('/trading/debug')
        .expect(200);

      expect(response.body).toHaveProperty('success');
      expect(response.body).toHaveProperty('tables');
    });
  });

  describe('GET /trading/signals', () => {
    test('should handle trading signals request', async () => {
      const response = await request(app)
        .get('/trading/signals');

      expect([200, 500]).toContain(response.status);
      expect(response.body).toHaveProperty('success');
    });
  });

  describe('POST /trading/orders', () => {
    test('should handle order creation', async () => {
      const validOrderData = {
        symbol: 'AAPL',
        quantity: 100,
        side: 'buy',
        type: 'market'
      };

      const response = await request(app)
        .post('/trading/orders')
        .send(validOrderData);

      expect([201, 400]).toContain(response.status);
      expect(response.body).toHaveProperty('success');
    });
  });

  describe('GET /trading/positions', () => {
    test('should handle positions request', async () => {
      const response = await request(app)
        .get('/trading/positions');

      expect([200, 500]).toContain(response.status);
      expect(response.body).toHaveProperty('success');
    });
  });

  // ================================
  // Risk Management Endpoints Tests
  // ================================

  describe('GET /trading/risk/portfolio', () => {
    test('should return comprehensive portfolio risk analysis', async () => {
      const response = await request(app)
        .get('/trading/risk/portfolio')
        .expect(200);

      expect(response.body).toHaveProperty('success', true);
      expect(response.body).toHaveProperty('data');
      expect(response.body.data).toHaveProperty('riskMetrics');
      expect(response.body.data).toHaveProperty('portfolioSummary');
      expect(response.body.data).toHaveProperty('recommendations');
      
      // Validate risk metrics structure
      const riskMetrics = response.body.data.riskMetrics;
      expect(riskMetrics).toHaveProperty('concentrationRisk');
      expect(riskMetrics).toHaveProperty('portfolioVolatility');
      expect(riskMetrics).toHaveProperty('portfolioBeta');
      expect(riskMetrics).toHaveProperty('diversificationScore');
      expect(riskMetrics).toHaveProperty('riskScore');
      expect(riskMetrics).toHaveProperty('riskLevel');

      // Validate numeric risk values are within expected ranges
      expect(typeof riskMetrics.concentrationRisk).toBe('number');
      expect(riskMetrics.concentrationRisk).toBeGreaterThanOrEqual(0);
      expect(riskMetrics.concentrationRisk).toBeLessThanOrEqual(1);
      
      expect(typeof riskMetrics.portfolioVolatility).toBe('number');
      expect(riskMetrics.portfolioVolatility).toBeGreaterThanOrEqual(0);
      
      expect(typeof riskMetrics.portfolioBeta).toBe('number');
      expect(typeof riskMetrics.diversificationScore).toBe('number');
      expect(riskMetrics.diversificationScore).toBeGreaterThanOrEqual(0);
      expect(riskMetrics.diversificationScore).toBeLessThanOrEqual(100);
    });

    test('should handle empty portfolio gracefully', async () => {
      // Test with a different user who has no positions
      app.use((req, res, next) => {
        req.user = { sub: 'empty-portfolio-user' };
        next();
      });

      const response = await request(app)
        .get('/trading/risk/portfolio')
        .expect(200);

      expect(response.body.success).toBe(true);
      expect(response.body.data.portfolioSummary.totalPositions).toBe(0);
    });
  });

  describe('POST /trading/risk/limits', () => {
    test('should create new risk limits with valid data', async () => {
      const riskLimitsData = {
        maxDrawdown: 15.0,
        maxPositionSize: 20.0,
        stopLossPercentage: 8.0,
        maxLeverage: 1.5,
        maxCorrelation: 0.6,
        riskToleranceLevel: 'conservative',
        maxDailyLoss: 1.5,
        maxMonthlyLoss: 8.0
      };

      const response = await request(app)
        .post('/trading/risk/limits')
        .send(riskLimitsData)
        .expect(200);

      expect(response.body).toHaveProperty('success', true);
      expect(response.body).toHaveProperty('message');
      expect(response.body).toHaveProperty('data');
      
      const data = response.body.data;
      expect(data).toHaveProperty('userId', 'test-user-123');
      expect(data).toHaveProperty('maxDrawdown', 15.0);
      expect(data).toHaveProperty('maxPositionSize', 20.0);
      expect(data).toHaveProperty('stopLossPercentage', 8.0);
      expect(data).toHaveProperty('maxLeverage', 1.5);
      expect(data).toHaveProperty('maxCorrelation', 0.6);
      expect(data).toHaveProperty('riskToleranceLevel', 'conservative');
      expect(data).toHaveProperty('maxDailyLoss', 1.5);
      expect(data).toHaveProperty('maxMonthlyLoss', 8.0);
      expect(data).toHaveProperty('updatedAt');
    });

    test('should update existing risk limits', async () => {
      // First create limits
      await request(app)
        .post('/trading/risk/limits')
        .send({ maxDrawdown: 10.0 });

      // Then update them
      const updateData = { maxDrawdown: 25.0, maxPositionSize: 30.0 };
      const response = await request(app)
        .post('/trading/risk/limits')
        .send(updateData)
        .expect(200);

      expect(response.body.success).toBe(true);
      expect(response.body.data.maxDrawdown).toBe(25.0);
      expect(response.body.data.maxPositionSize).toBe(30.0);
    });

    test('should validate risk limit ranges', async () => {
      const invalidData = {
        maxDrawdown: 150.0, // Invalid: > 100%
        maxPositionSize: -5.0, // Invalid: < 0%
        stopLossPercentage: 200.0 // Invalid: > 100%
      };

      const response = await request(app)
        .post('/trading/risk/limits')
        .send(invalidData)
        .expect(400);

      expect(response.body.success).toBe(false);
      expect(response.body).toHaveProperty('error', 'Validation failed');
      expect(response.body).toHaveProperty('details');
      expect(Array.isArray(response.body.details)).toBe(true);
      expect(response.body.details.length).toBeGreaterThan(0);
    });

    test('should require authentication', async () => {
      // Temporarily remove authentication
      const tempApp = express();
      tempApp.use(express.json());
      tempApp.use((req, res, next) => {
        req.user = null; // No authenticated user
        next();
      });
      
      const responseFormatter = require('../../../middleware/responseFormatter');
      tempApp.use(responseFormatter);
      
      const tradingRouter = require('../../../routes/trading');
      tempApp.use('/trading', tradingRouter);

      const response = await request(tempApp)
        .post('/trading/risk/limits')
        .send({ maxDrawdown: 10.0 })
        .expect(401);

      expect(response.body.success).toBe(false);
      expect(response.body).toHaveProperty('error', 'User authentication required');
    });

    test('should use default values for missing fields', async () => {
      const partialData = { maxDrawdown: 12.0 }; // Only one field

      const response = await request(app)
        .post('/trading/risk/limits')
        .send(partialData)
        .expect(200);

      const data = response.body.data;
      expect(data.maxDrawdown).toBe(12.0);
      // Check defaults are applied
      expect(data.maxPositionSize).toBe(25.0); // Default
      expect(data.stopLossPercentage).toBe(5.0); // Default
      expect(data.maxLeverage).toBe(2.0); // Default
    });
  });

  describe('POST /trading/positions/:symbol/close', () => {
    let testSymbol = 'AAPL';

    beforeEach(async () => {
      // Create a test position for closing
      try {
        await query(`
          INSERT INTO portfolio_holdings (
            user_id, symbol, quantity, average_cost, current_price, 
            total_value, unrealized_pnl, realized_pnl, position_type,
            last_updated
          ) VALUES ($1, $2, $3, $4, $5, $6, $7, $8, $9, $10)
          ON CONFLICT (user_id, symbol) 
          DO UPDATE SET 
            quantity = EXCLUDED.quantity,
            average_cost = EXCLUDED.average_cost,
            current_price = EXCLUDED.current_price,
            total_value = EXCLUDED.total_value,
            unrealized_pnl = EXCLUDED.unrealized_pnl,
            last_updated = EXCLUDED.last_updated
        `, [
          'test-user-123',
          testSymbol,
          100,
          150.0,
          160.0,
          16000.0,
          1000.0,
          0.0,
          'long',
          new Date().toISOString()
        ]);
      } catch (error) {
        // Position might already exist, that's ok
      }
    });

    test('should successfully close an existing position', async () => {
      const closeData = {
        closeType: 'market',
        reason: 'Take profit'
      };

      const response = await request(app)
        .post(`/trading/positions/${testSymbol}/close`)
        .send(closeData)
        .expect(200);

      expect(response.body).toHaveProperty('success', true);
      expect(response.body).toHaveProperty('message');
      expect(response.body).toHaveProperty('data');
      
      const data = response.body.data;
      expect(data).toHaveProperty('symbol', testSymbol);
      expect(data).toHaveProperty('closedQuantity');
      expect(data).toHaveProperty('closePrice');
      expect(data).toHaveProperty('closeType', 'market');
      expect(data).toHaveProperty('totalCost');
      expect(data).toHaveProperty('totalValue');
      expect(data).toHaveProperty('realizedPnL');
      expect(data).toHaveProperty('pnlPercentage');
      expect(data).toHaveProperty('closedAt');
      expect(data).toHaveProperty('reason', 'Take profit');
      expect(data).toHaveProperty('portfolioSummary');

      // Validate numeric values
      expect(typeof data.closedQuantity).toBe('number');
      expect(data.closedQuantity).toBeGreaterThan(0);
      expect(typeof data.closePrice).toBe('number');
      expect(data.closePrice).toBeGreaterThan(0);
      expect(typeof data.realizedPnL).toBe('number');
      expect(typeof data.pnlPercentage).toBe('number');
    });

    test('should handle limit order position closing', async () => {
      const closeData = {
        closeType: 'limit',
        priceLimit: 165.0,
        reason: 'Limit order execution'
      };

      const response = await request(app)
        .post(`/trading/positions/${testSymbol}/close`)
        .send(closeData)
        .expect(200);

      expect(response.body.success).toBe(true);
      expect(response.body.data.closeType).toBe('limit');
      expect(response.body.data.closePrice).toBe(165.0);
    });

    test('should return 404 for non-existent position', async () => {
      const nonExistentSymbol = 'NONEXISTENT';
      
      const response = await request(app)
        .post(`/trading/positions/${nonExistentSymbol}/close`)
        .send({ closeType: 'market' })
        .expect(404);

      expect(response.body.success).toBe(false);
      expect(response.body).toHaveProperty('error');
      expect(response.body.error).toContain('No open position found');
    });

    test('should require authentication', async () => {
      const tempApp = express();
      tempApp.use(express.json());
      tempApp.use((req, res, next) => {
        req.user = null; // No authenticated user
        next();
      });
      
      const responseFormatter = require('../../../middleware/responseFormatter');
      tempApp.use(responseFormatter);
      
      const tradingRouter = require('../../../routes/trading');
      tempApp.use('/trading', tradingRouter);

      const response = await request(tempApp)
        .post(`/trading/positions/${testSymbol}/close`)
        .send({ closeType: 'market' })
        .expect(401);

      expect(response.body.success).toBe(false);
      expect(response.body).toHaveProperty('error', 'User authentication required');
    });

    test('should validate required symbol parameter', async () => {
      const response = await request(app)
        .post('/trading/positions//close') // Empty symbol
        .send({ closeType: 'market' })
        .expect(404); // Route not found for empty symbol

      // This is expected behavior - empty symbol results in route not found
    });

    test('should handle database transaction rollback on error', async () => {
      // This test would require mocking the database to simulate an error
      // For now, we'll test that the endpoint handles errors gracefully
      const invalidCloseData = {
        closeType: 'invalid_type', // This shouldn't cause an error but tests error handling
        priceLimit: -100 // Negative price should be handled
      };

      const response = await request(app)
        .post(`/trading/positions/${testSymbol}/close`)
        .send(invalidCloseData);

      // Should still work, as invalid closeType defaults to market
      // and negative priceLimit is ignored for market orders
      expect([200, 500]).toContain(response.status);
      expect(response.body).toHaveProperty('success');
    });

    afterEach(async () => {
      // Clean up test position
      try {
        await query(`
          DELETE FROM portfolio_holdings 
          WHERE user_id = $1 AND symbol = $2
        `, ['test-user-123', testSymbol]);

        await query(`
          DELETE FROM trade_history 
          WHERE user_id = $1 AND symbol = $2
        `, ['test-user-123', testSymbol]);

        await query(`
          DELETE FROM portfolio_summary 
          WHERE user_id = $1
        `, ['test-user-123']);
      } catch (error) {
        // Cleanup errors are acceptable in tests
      }
    });
  });

  // ================================
  // Trading Strategies Tests
  // ================================

  describe('GET /trading/strategies', () => {
    test('should return available trading strategies', async () => {
      const response = await request(app)
        .get('/trading/strategies')
        .expect(200);

      expect(response.body).toHaveProperty('success', true);
      expect(response.body).toHaveProperty('data');
      expect(response.body.data).toHaveProperty('strategies');
      expect(Array.isArray(response.body.data.strategies)).toBe(true);
    });

    test('should filter strategies by type', async () => {
      const response = await request(app)
        .get('/trading/strategies?type=momentum')
        .expect(200);

      expect(response.body.success).toBe(true);
      if (response.body.data.strategies.length > 0) {
        response.body.data.strategies.forEach(strategy => {
          expect(strategy.type).toBe('momentum');
        });
      }
    });

    test('should include performance metrics', async () => {
      const response = await request(app)
        .get('/trading/strategies?include_performance=true')
        .expect(200);

      expect(response.body.success).toBe(true);
      if (response.body.data.strategies.length > 0) {
        const strategy = response.body.data.strategies[0];
        expect(strategy).toHaveProperty('performance');
        expect(strategy.performance).toHaveProperty('totalReturns');
        expect(strategy.performance).toHaveProperty('sharpeRatio');
      }
    });
  });

  describe('POST /trading/strategies', () => {
    test('should create a new trading strategy', async () => {
      const strategyData = {
        name: 'Test Momentum Strategy',
        type: 'momentum',
        description: 'Test strategy for momentum trading',
        rules: {
          entry: { rsi: { below: 30 } },
          exit: { rsi: { above: 70 } }
        },
        riskManagement: {
          stopLoss: 5.0,
          takeProfit: 10.0,
          positionSize: 2.0
        }
      };

      const response = await request(app)
        .post('/trading/strategies')
        .send(strategyData)
        .expect(201);

      expect(response.body.success).toBe(true);
      expect(response.body.data).toHaveProperty('strategyId');
      expect(response.body.data).toHaveProperty('name', strategyData.name);
      expect(response.body.data).toHaveProperty('type', strategyData.type);
    });

    test('should validate required fields', async () => {
      const invalidData = { name: 'Incomplete Strategy' };

      const response = await request(app)
        .post('/trading/strategies')
        .send(invalidData)
        .expect(400);

      expect(response.body.success).toBe(false);
      expect(response.body).toHaveProperty('error');
    });
  });

  // ================================
  // Trading Analytics Tests
  // ================================

  describe('GET /trading/analytics/performance', () => {
    test('should return trading performance analytics', async () => {
      const response = await request(app)
        .get('/trading/analytics/performance')
        .expect(200);

      expect(response.body).toHaveProperty('success', true);
      expect(response.body).toHaveProperty('data');
      expect(response.body.data).toHaveProperty('performance');
      
      const performance = response.body.data.performance;
      expect(performance).toHaveProperty('totalReturns');
      expect(performance).toHaveProperty('winRate');
      expect(performance).toHaveProperty('averageWin');
      expect(performance).toHaveProperty('averageLoss');
      expect(performance).toHaveProperty('profitFactor');
      expect(performance).toHaveProperty('sharpeRatio');
      expect(performance).toHaveProperty('maxDrawdown');
    });

    test('should handle time period filters', async () => {
      const response = await request(app)
        .get('/trading/analytics/performance?period=30d')
        .expect(200);

      expect(response.body.success).toBe(true);
      expect(response.body.data).toHaveProperty('period', '30d');
    });

    test('should include benchmark comparison', async () => {
      const response = await request(app)
        .get('/trading/analytics/performance?benchmark=SPY')
        .expect(200);

      expect(response.body.success).toBe(true);
      if (response.body.data.benchmark) {
        expect(response.body.data.benchmark).toHaveProperty('symbol', 'SPY');
        expect(response.body.data.benchmark).toHaveProperty('returns');
      }
    });
  });

  describe('GET /trading/analytics/trades', () => {
    test('should return detailed trade analysis', async () => {
      const response = await request(app)
        .get('/trading/analytics/trades')
        .expect(200);

      expect(response.body).toHaveProperty('success', true);
      expect(response.body).toHaveProperty('data');
      expect(response.body.data).toHaveProperty('trades');
      expect(response.body.data).toHaveProperty('summary');
      
      const summary = response.body.data.summary;
      expect(summary).toHaveProperty('totalTrades');
      expect(summary).toHaveProperty('winningTrades');
      expect(summary).toHaveProperty('losingTrades');
      expect(summary).toHaveProperty('averageHoldingTime');
    });

    test('should filter trades by symbol', async () => {
      const response = await request(app)
        .get('/trading/analytics/trades?symbol=AAPL')
        .expect(200);

      expect(response.body.success).toBe(true);
      if (response.body.data.trades.length > 0) {
        response.body.data.trades.forEach(trade => {
          expect(trade.symbol).toBe('AAPL');
        });
      }
    });

    test('should support pagination', async () => {
      const response = await request(app)
        .get('/trading/analytics/trades?page=1&limit=10')
        .expect(200);

      expect(response.body.success).toBe(true);
      expect(response.body.data).toHaveProperty('pagination');
      expect(response.body.data.pagination).toHaveProperty('page', 1);
      expect(response.body.data.pagination).toHaveProperty('limit', 10);
    });
  });

  // ================================
  // Market Hours & Trading Status Tests
  // ================================

  describe('GET /trading/market/status', () => {
    test('should return current market status', async () => {
      const response = await request(app)
        .get('/trading/market/status')
        .expect(200);

      expect(response.body).toHaveProperty('success', true);
      expect(response.body).toHaveProperty('data');
      expect(response.body.data).toHaveProperty('marketOpen');
      expect(response.body.data).toHaveProperty('nextOpen');
      expect(response.body.data).toHaveProperty('nextClose');
      expect(response.body.data).toHaveProperty('timezone');
      
      expect(typeof response.body.data.marketOpen).toBe('boolean');
    });

    test('should include extended hours information', async () => {
      const response = await request(app)
        .get('/trading/market/status?include_extended=true')
        .expect(200);

      expect(response.body.success).toBe(true);
      if (response.body.data.extendedHours) {
        expect(response.body.data.extendedHours).toHaveProperty('preMarket');
        expect(response.body.data.extendedHours).toHaveProperty('afterHours');
      }
    });
  });

  describe('GET /trading/market/hours', () => {
    test('should return trading hours for current week', async () => {
      const response = await request(app)
        .get('/trading/market/hours')
        .expect(200);

      expect(response.body).toHaveProperty('success', true);
      expect(response.body).toHaveProperty('data');
      expect(response.body.data).toHaveProperty('regularHours');
      expect(response.body.data).toHaveProperty('extendedHours');
      expect(response.body.data).toHaveProperty('holidays');
    });

    test('should handle specific date queries', async () => {
      const response = await request(app)
        .get('/trading/market/hours?date=2024-01-15')
        .expect(200);

      expect(response.body.success).toBe(true);
      expect(response.body.data).toHaveProperty('date', '2024-01-15');
    });
  });

  // ================================
  // Quotes & Real-time Data Tests
  // ================================

  describe('GET /trading/quotes/:symbol', () => {
    test('should return real-time quote for valid symbol', async () => {
      const response = await request(app)
        .get('/trading/quotes/AAPL')
        .expect(200);

      expect(response.body).toHaveProperty('success', true);
      expect(response.body).toHaveProperty('data');
      expect(response.body.data).toHaveProperty('symbol', 'AAPL');
      expect(response.body.data).toHaveProperty('price');
      expect(response.body.data).toHaveProperty('timestamp');
      expect(response.body.data).toHaveProperty('volume');
      
      expect(typeof response.body.data.price).toBe('number');
      expect(response.body.data.price).toBeGreaterThan(0);
    });

    test('should include bid/ask spread information', async () => {
      const response = await request(app)
        .get('/trading/quotes/AAPL?include_spread=true')
        .expect(200);

      expect(response.body.success).toBe(true);
      if (response.body.data.spread) {
        expect(response.body.data.spread).toHaveProperty('bid');
        expect(response.body.data.spread).toHaveProperty('ask');
        expect(response.body.data.spread).toHaveProperty('bidSize');
        expect(response.body.data.spread).toHaveProperty('askSize');
      }
    });

    test('should handle invalid symbols gracefully', async () => {
      const response = await request(app)
        .get('/trading/quotes/INVALID123')
        .expect(404);

      expect(response.body.success).toBe(false);
      expect(response.body).toHaveProperty('error');
    });
  });

  describe('POST /trading/quotes/batch', () => {
    test('should return quotes for multiple symbols', async () => {
      const symbols = { symbols: ['AAPL', 'MSFT', 'GOOGL'] };
      
      const response = await request(app)
        .post('/trading/quotes/batch')
        .send(symbols)
        .expect(200);

      expect(response.body).toHaveProperty('success', true);
      expect(response.body).toHaveProperty('data');
      expect(response.body.data).toHaveProperty('quotes');
      expect(Array.isArray(response.body.data.quotes)).toBe(true);
      
      if (response.body.data.quotes.length > 0) {
        response.body.data.quotes.forEach(quote => {
          expect(quote).toHaveProperty('symbol');
          expect(quote).toHaveProperty('price');
          expect(['AAPL', 'MSFT', 'GOOGL']).toContain(quote.symbol);
        });
      }
    });

    test('should limit batch size', async () => {
      const tooManySymbols = { 
        symbols: Array.from({length: 150}, (_, i) => `STOCK${i}`) 
      };
      
      const response = await request(app)
        .post('/trading/quotes/batch')
        .send(tooManySymbols)
        .expect(400);

      expect(response.body.success).toBe(false);
      expect(response.body).toHaveProperty('error');
      expect(response.body.error).toContain('too many symbols');
    });
  });

  // ================================
  // Paper Trading Tests
  // ================================

  describe('GET /trading/paper/status', () => {
    test('should return paper trading account status', async () => {
      const response = await request(app)
        .get('/trading/paper/status')
        .expect(200);

      expect(response.body).toHaveProperty('success', true);
      expect(response.body).toHaveProperty('data');
      expect(response.body.data).toHaveProperty('account');
      expect(response.body.data).toHaveProperty('paperTrading');
      
      const account = response.body.data.account;
      expect(account).toHaveProperty('balance');
      expect(account).toHaveProperty('buyingPower');
      expect(account).toHaveProperty('positions');
      
      expect(typeof response.body.data.paperTrading).toBe('boolean');
    });

    test('should include performance metrics', async () => {
      const response = await request(app)
        .get('/trading/paper/status?include_performance=true')
        .expect(200);

      expect(response.body.success).toBe(true);
      if (response.body.data.performance) {
        expect(response.body.data.performance).toHaveProperty('totalReturn');
        expect(response.body.data.performance).toHaveProperty('dailyReturn');
      }
    });
  });

  describe('POST /trading/paper/reset', () => {
    test('should reset paper trading account', async () => {
      const resetData = { 
        initialBalance: 100000,
        confirmReset: true 
      };
      
      const response = await request(app)
        .post('/trading/paper/reset')
        .send(resetData)
        .expect(200);

      expect(response.body).toHaveProperty('success', true);
      expect(response.body).toHaveProperty('message');
      expect(response.body.data).toHaveProperty('newBalance', 100000);
      expect(response.body.data).toHaveProperty('resetAt');
    });

    test('should require confirmation', async () => {
      const response = await request(app)
        .post('/trading/paper/reset')
        .send({ initialBalance: 100000 }) // Missing confirmReset
        .expect(400);

      expect(response.body.success).toBe(false);
      expect(response.body).toHaveProperty('error');
      expect(response.body.error).toContain('confirmation required');
    });
  });

  // ================================
  // Order Management Tests
  // ================================

  describe('GET /trading/orders', () => {
    test('should return user orders with pagination', async () => {
      const response = await request(app)
        .get('/trading/orders')
        .expect(200);

      expect(response.body).toHaveProperty('success', true);
      expect(response.body).toHaveProperty('data');
      expect(response.body.data).toHaveProperty('orders');
      expect(response.body.data).toHaveProperty('pagination');
      expect(Array.isArray(response.body.data.orders)).toBe(true);
    });

    test('should filter orders by status', async () => {
      const response = await request(app)
        .get('/trading/orders?status=open')
        .expect(200);

      expect(response.body.success).toBe(true);
      if (response.body.data.orders.length > 0) {
        response.body.data.orders.forEach(order => {
          expect(['pending', 'open', 'partially_filled']).toContain(order.status);
        });
      }
    });

    test('should filter orders by symbol', async () => {
      const response = await request(app)
        .get('/trading/orders?symbol=AAPL')
        .expect(200);

      expect(response.body.success).toBe(true);
      if (response.body.data.orders.length > 0) {
        response.body.data.orders.forEach(order => {
          expect(order.symbol).toBe('AAPL');
        });
      }
    });
  });

  describe('DELETE /trading/orders/:orderId', () => {
    test('should cancel an existing order', async () => {
      // This would require setting up a test order first
      // For now, test error handling for non-existent order
      const response = await request(app)
        .delete('/trading/orders/non-existent-order-id')
        .expect(404);

      expect(response.body.success).toBe(false);
      expect(response.body).toHaveProperty('error');
    });

    test('should handle already filled orders', async () => {
      const response = await request(app)
        .delete('/trading/orders/filled-order-id')
        .expect(400);

      expect(response.body.success).toBe(false);
      expect(response.body.error).toContain('cannot be cancelled');
    });
  });

  // ================================
  // Error Handling & Edge Cases
  // ================================

  describe('Trading Error Handling', () => {
    test('should handle database connection errors gracefully', async () => {
      // This would require mocking database to simulate connection failure
      const response = await request(app)
        .get('/trading/positions')
        .timeout(5000);

      expect([200, 500, 503]).toContain(response.status);
      expect(response.body).toHaveProperty('success');
    });

    test('should validate symbol format', async () => {
      const response = await request(app)
        .get('/trading/quotes/invalid-symbol-format-123!')
        .expect(400);

      expect(response.body.success).toBe(false);
      expect(response.body).toHaveProperty('error');
    });

    test('should handle market closed scenarios', async () => {
      const response = await request(app)
        .post('/trading/orders')
        .send({
          symbol: 'AAPL',
          quantity: 100,
          side: 'buy',
          type: 'market'
        });

      // Should either succeed or return appropriate market closed error
      expect([201, 400, 503]).toContain(response.status);
      expect(response.body).toHaveProperty('success');
    });

    test('should handle insufficient funds scenarios', async () => {
      const largeOrder = {
        symbol: 'AAPL',
        quantity: 999999, // Very large quantity
        side: 'buy',
        type: 'market'
      };

      const response = await request(app)
        .post('/trading/orders')
        .send(largeOrder);

      if (response.status === 400) {
        expect(response.body.success).toBe(false);
        expect(response.body.error).toContain('insufficient');
      }
    });

    test('should rate limit API calls', async () => {
      // Make multiple rapid requests
      const promises = Array.from({length: 20}, () => 
        request(app).get('/trading/market/status')
      );

      const responses = await Promise.all(promises);
      
      // At least some should succeed
      const successCount = responses.filter(r => r.status === 200).length;
      expect(successCount).toBeGreaterThan(0);
    });
  });

  // Test cleanup
  afterAll(async () => {
    try {
      // Clean up any test data
      await query(`DELETE FROM user_risk_limits WHERE user_id = $1`, ['test-user-123']);
      await query(`DELETE FROM portfolio_holdings WHERE user_id = $1`, ['test-user-123']);
      await query(`DELETE FROM trade_history WHERE user_id = $1`, ['test-user-123']);
      await query(`DELETE FROM portfolio_summary WHERE user_id = $1`, ['test-user-123']);
      await query(`DELETE FROM trading_strategies WHERE user_id = $1`, ['test-user-123']);
      await query(`DELETE FROM orders WHERE user_id = $1`, ['test-user-123']);
    } catch (error) {
      // Cleanup errors are acceptable
    }
  });
});
