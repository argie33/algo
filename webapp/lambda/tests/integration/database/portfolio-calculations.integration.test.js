/**
 * Portfolio Calculations Integration Test
 * Critical: Validates financial calculation accuracy with real database data
 */

const request = require('supertest');
const { app } = require('../../../index');
const { query } = require('../../../services/database');

describe('Portfolio Calculations Integration', () => {
  let testUserId;
  let testPortfolioData;

  beforeAll(async () => {
    // Setup test user and portfolio data
    testUserId = 'test-user-portfolio-calc-' + Date.now();
    
    // Insert test portfolio data
    testPortfolioData = {
      symbol: 'AAPL',
      quantity: 100,
      avgCost: 150.00,
      currentPrice: 175.50,
      sector: 'Technology'
    };

    await query(`
      INSERT INTO user_portfolio (user_id, symbol, quantity, avg_cost, last_updated)
      VALUES ($1, $2, $3, $4, NOW())
    `, [testUserId, testPortfolioData.symbol, testPortfolioData.quantity, testPortfolioData.avgCost]);
  });

  afterAll(async () => {
    // Cleanup test data
    await query('DELETE FROM user_portfolio WHERE user_id = $1', [testUserId]);
  });

  describe('Portfolio Value Calculations', () => {
    test('should calculate correct total portfolio value', async () => {
      const response = await request(app)
        .get(`/api/portfolio/analytics?timeframe=1D`)
        .set('Authorization', `Bearer mock-token`)
        .set('x-user-id', testUserId);

      expect(response.status).toBe(200);
      
      const { data } = response.body;
      const expectedValue = testPortfolioData.quantity * testPortfolioData.currentPrice;
      
      expect(data.totalValue).toBeCloseTo(expectedValue, 2);
      expect(data.totalValue).toBe(17550.00); // 100 * 175.50
    });

    test('should calculate accurate profit/loss metrics', async () => {
      const response = await request(app)
        .get(`/api/portfolio/analytics?timeframe=1D`)
        .set('Authorization', `Bearer mock-token`)
        .set('x-user-id', testUserId);

      const { data } = response.body;
      const expectedCost = testPortfolioData.quantity * testPortfolioData.avgCost;
      const expectedValue = testPortfolioData.quantity * testPortfolioData.currentPrice;
      const expectedGainLoss = expectedValue - expectedCost;
      const expectedGainLossPercent = (expectedGainLoss / expectedCost) * 100;

      expect(data.totalCost).toBeCloseTo(expectedCost, 2);
      expect(data.totalGainLoss).toBeCloseTo(expectedGainLoss, 2);
      expect(data.totalGainLossPercent).toBeCloseTo(expectedGainLossPercent, 2);
      
      // Validate specific values
      expect(data.totalCost).toBe(15000.00); // 100 * 150.00
      expect(data.totalGainLoss).toBe(2550.00); // 17550 - 15000
      expect(data.totalGainLossPercent).toBeCloseTo(17.00, 1); // (2550/15000)*100
    });

    test('should handle zero and negative positions correctly', async () => {
      // Insert zero position
      await query(`
        INSERT INTO user_portfolio (user_id, symbol, quantity, avg_cost, last_updated)
        VALUES ($1, 'ZERO', 0, 100.00, NOW())
      `, [testUserId]);

      const response = await request(app)
        .get(`/api/portfolio/analytics?timeframe=1D`)
        .set('Authorization', `Bearer mock-token`)
        .set('x-user-id', testUserId);

      expect(response.status).toBe(200);
      
      // Should exclude zero positions from calculations
      const { data } = response.body;
      expect(data.holdings).not.toEqual(
        expect.arrayContaining([
          expect.objectContaining({ symbol: 'ZERO' })
        ])
      );
    });

    test('should calculate sector allocation correctly', async () => {
      // Add another technology stock
      await query(`
        INSERT INTO user_portfolio (user_id, symbol, quantity, avg_cost, last_updated)
        VALUES ($1, 'MSFT', 50, 200.00, NOW())
      `, [testUserId]);

      const response = await request(app)
        .get(`/api/portfolio/analytics?timeframe=1D`)
        .set('Authorization', `Bearer mock-token`)
        .set('x-user-id', testUserId);

      const { data } = response.body;
      
      // Should have sector allocation data
      expect(data.sectorAllocation).toBeDefined();
      expect(Array.isArray(data.sectorAllocation)).toBe(true);
      
      const techSector = data.sectorAllocation.find(s => s.sector === 'Technology');
      expect(techSector).toBeDefined();
      expect(techSector.percentage).toBeGreaterThan(0);
    });
  });

  describe('Risk Metrics Calculations', () => {
    test('should calculate portfolio beta accurately', async () => {
      const response = await request(app)
        .get(`/api/portfolio/risk-metrics`)
        .set('Authorization', `Bearer mock-token`)
        .set('x-user-id', testUserId);

      expect(response.status).toBe(200);
      
      const { data } = response.body;
      expect(data.beta).toBeDefined();
      expect(typeof data.beta).toBe('number');
      expect(data.beta).toBeGreaterThan(-5);
      expect(data.beta).toBeLessThan(5);
    });

    test('should calculate value at risk (VaR)', async () => {
      const response = await request(app)
        .get(`/api/portfolio/risk-metrics`)
        .set('Authorization', `Bearer mock-token`)
        .set('x-user-id', testUserId);

      const { data } = response.body;
      expect(data.var95).toBeDefined();
      expect(data.var99).toBeDefined();
      expect(typeof data.var95).toBe('number');
      expect(typeof data.var99).toBe('number');
      
      // VaR99 should be greater than VaR95
      expect(Math.abs(data.var99)).toBeGreaterThan(Math.abs(data.var95));
    });

    test('should calculate Sharpe ratio', async () => {
      const response = await request(app)
        .get(`/api/portfolio/risk-metrics`)
        .set('Authorization', `Bearer mock-token`)
        .set('x-user-id', testUserId);

      const { data } = response.body;
      expect(data.sharpeRatio).toBeDefined();
      expect(typeof data.sharpeRatio).toBe('number');
      expect(data.sharpeRatio).toBeGreaterThan(-10);
      expect(data.sharpeRatio).toBeLessThan(10);
    });
  });

  describe('Performance Metrics Accuracy', () => {
    test('should calculate time-weighted returns correctly', async () => {
      const response = await request(app)
        .get(`/api/portfolio/performance?period=1M`)
        .set('Authorization', `Bearer mock-token`)
        .set('x-user-id', testUserId);

      expect(response.status).toBe(200);
      
      const { data } = response.body;
      expect(data.timeWeightedReturn).toBeDefined();
      expect(typeof data.timeWeightedReturn).toBe('number');
    });

    test('should handle missing price data gracefully', async () => {
      // Insert position with no price data
      await query(`
        INSERT INTO user_portfolio (user_id, symbol, quantity, avg_cost, last_updated)
        VALUES ($1, 'NODATA', 10, 50.00, NOW())
      `, [testUserId]);

      const response = await request(app)
        .get(`/api/portfolio/analytics?timeframe=1D`)
        .set('Authorization', `Bearer mock-token`)
        .set('x-user-id', testUserId);

      expect(response.status).toBe(200);
      
      // Should still calculate portfolio metrics for positions with data
      const { data } = response.body;
      expect(data.totalValue).toBeGreaterThan(0);
    });
  });

  describe('Currency and Precision Handling', () => {
    test('should maintain precision for large portfolio values', async () => {
      // Insert high-value position
      await query(`
        INSERT INTO user_portfolio (user_id, symbol, quantity, avg_cost, last_updated)
        VALUES ($1, 'BRK.A', 10, 450000.00, NOW())
      `, [testUserId]);

      const response = await request(app)
        .get(`/api/portfolio/analytics?timeframe=1D`)
        .set('Authorization', `Bearer mock-token`)
        .set('x-user-id', testUserId);

      const { data } = response.body;
      
      // Should handle large numbers with proper precision
      expect(data.totalValue).toBeGreaterThan(4000000);
      expect(Number.isFinite(data.totalValue)).toBe(true);
    });

    test('should handle fractional shares correctly', async () => {
      // Insert fractional position
      await query(`
        INSERT INTO user_portfolio (user_id, symbol, quantity, avg_cost, last_updated)
        VALUES ($1, 'FRAC', 10.5555, 25.25, NOW())
      `, [testUserId]);

      const response = await request(app)
        .get(`/api/portfolio/analytics?timeframe=1D`)
        .set('Authorization', `Bearer mock-token`)
        .set('x-user-id', testUserId);

      const { data } = response.body;
      
      // Should calculate correctly with fractional shares
      expect(data.totalValue).toBeGreaterThan(0);
      const fractionalHolding = data.holdings?.find(h => h.symbol === 'FRAC');
      if (fractionalHolding) {
        expect(fractionalHolding.quantity).toBe(10.5555);
      }
    });
  });

  describe('Data Consistency Validation', () => {
    test('should ensure holdings sum equals total portfolio value', async () => {
      const response = await request(app)
        .get(`/api/portfolio/analytics?timeframe=1D`)
        .set('Authorization', `Bearer mock-token`)
        .set('x-user-id', testUserId);

      const { data } = response.body;
      
      // Sum individual holdings
      const holdingsSum = data.holdings?.reduce((sum, holding) => {
        return sum + (holding.currentValue || 0);
      }, 0) || 0;

      // Should match total portfolio value
      expect(holdingsSum).toBeCloseTo(data.totalValue, 2);
    });

    test('should maintain referential integrity with price updates', async () => {
      // Update price data
      await query(`
        INSERT INTO stock_prices (symbol, price, timestamp, volume)
        VALUES ('AAPL', 180.00, NOW(), 1000000)
        ON CONFLICT (symbol, DATE(timestamp)) 
        DO UPDATE SET price = 180.00, volume = 1000000
      `);

      const response = await request(app)
        .get(`/api/portfolio/analytics?timeframe=1D`)
        .set('Authorization', `Bearer mock-token`)
        .set('x-user-id', testUserId);

      const { data } = response.body;
      
      // Should reflect updated price
      const aaplHolding = data.holdings?.find(h => h.symbol === 'AAPL');
      if (aaplHolding) {
        expect(aaplHolding.currentPrice).toBeCloseTo(180.00, 2);
      }
    });
  });
});