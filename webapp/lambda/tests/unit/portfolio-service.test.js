/**
 * Portfolio Service Unit Tests
 * Tests for real database integration portfolio service
 */

// Mock AlpacaService before importing portfolioService to avoid API key requirement
jest.mock('../../utils/alpacaService', () => {
  return jest.fn().mockImplementation(() => ({
    getPositions: jest.fn().mockResolvedValue([]),
    getAccount: jest.fn().mockResolvedValue({
      account_number: 'TEST123',
      account_type: 'margin',
      equity: 50000.00,
      buying_power: 25000.00,
      cash: 5000.00,
      daytrade_count: 2
    })
  }));
});

const portfolioService = require('../../services/portfolioService');
const { dbTestUtils } = require('../utils/database-test-utils');

describe('Portfolio Service Unit Tests', () => {
  let testUser;

  beforeAll(async () => {
    // Initialize database connection for tests
    await dbTestUtils.initialize();
  });

  beforeEach(async () => {
    // Create a test user for each test
    testUser = await dbTestUtils.createTestUser({
      email: `portfolio-test-${Date.now()}@example.com`,
      username: `portfoliouser${Date.now()}`
    });
  });

  afterEach(async () => {
    // Clean up test data after each test
    if (testUser) {
      await dbTestUtils.query('DELETE FROM portfolio_holdings WHERE user_id = $1', [testUser.user_id]);
      await dbTestUtils.query('DELETE FROM portfolio_metadata WHERE user_id = $1', [testUser.user_id]);
      await dbTestUtils.query('DELETE FROM users WHERE user_id = $1', [testUser.user_id]);
    }
  });

  afterAll(async () => {
    // Close database connection after all tests
    await dbTestUtils.cleanup();
  });

  describe('Portfolio CRUD Operations', () => {
    test('should retrieve empty portfolio for new user', async () => {
      const portfolio = await portfolioService.getUserPortfolio(testUser.user_id);
      
      expect(portfolio).toBeDefined();
      expect(portfolio.userId).toBe(testUser.user_id);
      expect(portfolio.holdings).toHaveLength(0);
      expect(portfolio.summary.totalPositions).toBe(0);
      expect(portfolio.summary.totalMarketValue).toBe(0);
    });

    test('should update portfolio holdings successfully', async () => {
      const holdings = [
        {
          symbol: 'AAPL',
          quantity: 100,
          avgCost: 150.00,
          currentPrice: 155.00,
          marketValue: 15500.00,
          unrealizedPL: 500.00,
          sector: 'Technology'
        },
        {
          symbol: 'MSFT',
          quantity: 50,
          avgCost: 300.00,
          currentPrice: 310.00,
          marketValue: 15500.00,
          unrealizedPL: 500.00,
          sector: 'Technology'
        }
      ];

      const result = await portfolioService.updatePortfolioHoldings(testUser.user_id, holdings);
      
      expect(result.success).toBe(true);
      expect(result.updatedPositions).toBe(2);

      // Verify holdings were saved
      const portfolio = await portfolioService.getUserPortfolio(testUser.user_id);
      expect(portfolio.holdings).toHaveLength(2);
      expect(portfolio.summary.totalMarketValue).toBe(31000.00);
    });

    test('should save portfolio metadata successfully', async () => {
      const metadata = {
        accountId: 'TEST123456',
        accountType: 'margin',
        totalEquity: 50000.00,
        buyingPower: 25000.00,
        cash: 5000.00,
        dayTradeCount: 2
      };

      const result = await portfolioService.savePortfolioMetadata(testUser.user_id, metadata);
      
      expect(result.success).toBe(true);

      // Verify metadata was saved
      const portfolio = await portfolioService.getUserPortfolio(testUser.user_id);
      expect(portfolio.metadata).toBeDefined();
      expect(portfolio.metadata.account_id).toBe('TEST123456');
      expect(parseFloat(portfolio.metadata.total_equity)).toBe(50000.00);
    });

    test('should handle upsert for existing holdings', async () => {
      // First insert
      const initialHoldings = [{
        symbol: 'AAPL',
        quantity: 100,
        avgCost: 150.00,
        currentPrice: 155.00,
        marketValue: 15500.00,
        unrealizedPL: 500.00,
        sector: 'Technology'
      }];

      await portfolioService.updatePortfolioHoldings(testUser.user_id, initialHoldings);

      // Update with new values
      const updatedHoldings = [{
        symbol: 'AAPL',
        quantity: 150,
        avgCost: 148.00,
        currentPrice: 160.00,
        marketValue: 24000.00,
        unrealizedPL: 1800.00,
        sector: 'Technology'
      }];

      await portfolioService.updatePortfolioHoldings(testUser.user_id, updatedHoldings);

      const portfolio = await portfolioService.getUserPortfolio(testUser.user_id);
      expect(portfolio.holdings).toHaveLength(1);
      expect(parseFloat(portfolio.holdings[0].quantity)).toBe(150);
      expect(parseFloat(portfolio.holdings[0].market_value)).toBe(24000.00);
    });
  });

  describe('Portfolio Performance Calculations', () => {
    test('should calculate portfolio performance metrics', async () => {
      // Setup test portfolio with some history
      const holdings = [{
        symbol: 'AAPL',
        quantity: 100,
        avgCost: 150.00,
        currentPrice: 155.00,
        marketValue: 15500.00,
        unrealizedPL: 500.00,
        sector: 'Technology'
      }];

      await portfolioService.updatePortfolioHoldings(testUser.user_id, holdings);

      const performance = await portfolioService.getPortfolioPerformance(testUser.user_id, '1M');
      
      expect(performance).toBeDefined();
      expect(performance.period).toBe('1M');
      expect(typeof performance.totalReturn).toBe('number');
      expect(typeof performance.totalReturnPercent).toBe('number');
      expect(typeof performance.volatility).toBe('number');
      expect(typeof performance.sharpeRatio).toBe('number');
      expect(typeof performance.maxDrawdown).toBe('number');
    });

    test('should handle empty portfolio history gracefully', async () => {
      const performance = await portfolioService.getPortfolioPerformance(testUser.user_id, '1M');
      
      expect(performance.totalReturn).toBe(0);
      expect(performance.totalReturnPercent).toBe(0);
      expect(performance.dailyReturns).toHaveLength(0);
      expect(performance.volatility).toBe(0);
    });
  });

  describe('Portfolio Optimization Integration', () => {
    test('should format portfolio for optimization service', async () => {
      const holdings = [
        {
          symbol: 'AAPL',
          quantity: 100,
          avgCost: 150.00,
          currentPrice: 155.00,
          marketValue: 15500.00,
          unrealizedPL: 500.00,
          sector: 'Technology'
        },
        {
          symbol: 'MSFT',
          quantity: 50,
          avgCost: 300.00,
          currentPrice: 310.00,
          marketValue: 15500.00,
          unrealizedPL: 500.00,
          sector: 'Technology'
        }
      ];

      const metadata = {
        accountId: 'TEST123456',
        accountType: 'margin',
        totalEquity: 50000.00,
        buyingPower: 25000.00,
        cash: 5000.00,
        dayTradeCount: 2
      };

      await portfolioService.updatePortfolioHoldings(testUser.user_id, holdings);
      await portfolioService.savePortfolioMetadata(testUser.user_id, metadata);

      const optimizationPortfolio = await portfolioService.getPortfolioForOptimization(testUser.user_id);
      
      expect(optimizationPortfolio).toBeDefined();
      expect(optimizationPortfolio.userId).toBe(testUser.user_id);
      expect(optimizationPortfolio.positions).toHaveLength(2);
      expect(optimizationPortfolio.constraints).toBeDefined();
      expect(optimizationPortfolio.constraints.totalValue).toBe(31000.00);
      expect(optimizationPortfolio.constraints.cash).toBe(5000.00);

      // Check position formatting
      const applePosition = optimizationPortfolio.positions.find(p => p.symbol === 'AAPL');
      expect(applePosition).toBeDefined();
      expect(applePosition.quantity).toBe(100);
      expect(applePosition.weight).toBeCloseTo(0.5, 2); // 15500/31000
    });

    test('should save optimization results to database', async () => {
      const optimizationResults = {
        type: 'THRESHOLD',
        parameters: { rebalanceThreshold: 0.05 },
        trades: [
          {
            symbol: 'AAPL',
            action: 'SELL',
            quantity: 10,
            estimatedPrice: 155.00,
            rationale: 'Rebalance overweight position',
            priority: 'medium'
          }
        ],
        metrics: {
          expectedReturn: 0.08,
          expectedVolatility: 0.15
        }
      };

      const result = await portfolioService.saveOptimizationResults(testUser.user_id, optimizationResults);
      
      expect(result.success).toBe(true);
      expect(result.optimizationId).toBeDefined();
      expect(result.tradesCount).toBe(1);

      // Verify data was saved
      const savedOptimizations = await dbTestUtils.query(`
        SELECT * FROM portfolio_optimizations WHERE user_id = $1
      `, [testUser.user_id]);

      expect(savedOptimizations.rows).toHaveLength(1);
      expect(savedOptimizations.rows[0].optimization_type).toBe('THRESHOLD');
    });
  });

  describe('Error Handling', () => {
    test('should handle invalid user ID gracefully', async () => {
      await expect(portfolioService.getUserPortfolio(999999))
        .resolves.toBeDefined(); // Should return empty portfolio, not throw
    });

    test('should handle database connection errors', async () => {
      // Mock a database error by using invalid data
      await expect(portfolioService.updatePortfolioHoldings(testUser.user_id, [
        {
          symbol: 'INVALID_SYMBOL_TOO_LONG_FOR_DATABASE',
          quantity: 'invalid_quantity',
          avgCost: 'invalid_cost'
        }
      ])).rejects.toThrow();
    });

    test('should validate required fields', async () => {
      await expect(portfolioService.updatePortfolioHoldings(testUser.user_id, [
        {
          // Missing required fields
          symbol: 'AAPL'
          // quantity, avgCost, etc. missing
        }
      ])).rejects.toThrow();
    });
  });

  describe('Service Health Check', () => {
    test('should return healthy status when database is available', async () => {
      const health = await portfolioService.healthCheck();
      
      expect(health.status).toBe('healthy');
      expect(health.service).toBe('portfolio');
      expect(health.database).toBeDefined();
      expect(health.timestamp).toBeDefined();
    });
  });
});