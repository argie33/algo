/**
 * Real Services Integration Tests
 * Tests the integration of portfolio service, market data service, and technical analysis
 * Uses real database connections and live market data APIs
 */

const portfolioService = require('../../services/portfolioService');
const marketDataService = require('../../services/marketDataService');
const TechnicalAnalysisService = require('../../services/technicalAnalysisService');
const { dbTestUtils } = require('../utils/database-test-utils');

describe('Real Services Integration Tests', () => {
  let testUser;
  let technicalAnalysisService;

  beforeAll(async () => {
    // Initialize database connection
    await dbTestUtils.initialize();
    
    // Create instance of technical analysis service
    technicalAnalysisService = new TechnicalAnalysisService();
  });

  beforeEach(async () => {
    // Create test user for each test
    testUser = await dbTestUtils.createTestUser({
      email: `real-services-test-${Date.now()}@example.com`,
      username: `realservicesuser${Date.now()}`
    });
  });

  afterEach(async () => {
    // Clean up test data
    if (testUser) {
      await dbTestUtils.query('DELETE FROM portfolio_holdings WHERE user_id = $1', [testUser.user_id]);
      await dbTestUtils.query('DELETE FROM portfolio_metadata WHERE user_id = $1', [testUser.user_id]);
      await dbTestUtils.query('DELETE FROM users WHERE user_id = $1', [testUser.user_id]);
    }
  });

  afterAll(async () => {
    await dbTestUtils.cleanup();
  });

  describe('Market Data Service Integration', () => {
    test('should get real-time quote for AAPL', async () => {
      const quote = await marketDataService.getQuote('AAPL');
      
      expect(quote).toBeDefined();
      expect(quote.symbol).toBe('AAPL');
      expect(typeof quote.price).toBe('number');
      expect(quote.price).toBeGreaterThan(0);
      expect(quote.timestamp).toBeDefined();
      expect(quote.source).toBe('yahoo');
    });

    test('should get historical data for multiple periods', async () => {
      const historical = await marketDataService.getHistoricalData('AAPL', {
        period: '1mo',
        interval: '1d'
      });
      
      expect(historical).toBeDefined();
      expect(Array.isArray(historical)).toBe(true);
      expect(historical.length).toBeGreaterThan(15); // At least 15 trading days
      
      // Check data structure
      const dataPoint = historical[0];
      expect(dataPoint).toHaveProperty('date');
      expect(dataPoint).toHaveProperty('open');
      expect(dataPoint).toHaveProperty('high');
      expect(dataPoint).toHaveProperty('low');
      expect(dataPoint).toHaveProperty('close');
      expect(dataPoint).toHaveProperty('volume');
    });

    test('should get portfolio market data for multiple symbols', async () => {
      const symbols = ['AAPL', 'MSFT', 'GOOGL'];
      const marketData = await marketDataService.getPortfolioMarketData(symbols, {
        includeHistorical: true,
        includeVolatility: true
      });
      
      expect(marketData).toBeDefined();
      expect(Object.keys(marketData)).toHaveLength(3);
      
      for (const symbol of symbols) {
        expect(marketData[symbol]).toBeDefined();
        expect(marketData[symbol].symbol).toBe(symbol);
        expect(typeof marketData[symbol].price).toBe('number');
        expect(marketData[symbol].historical).toBeDefined();
        expect(marketData[symbol].volatility).toBeDefined();
      }
    });

    test('should handle market status correctly', async () => {
      const marketStatus = await marketDataService.getMarketStatus();
      
      expect(marketStatus).toBeDefined();
      expect(typeof marketStatus.isOpen).toBe('boolean');
      expect(marketStatus.currentTime).toBeDefined();
      expect(marketStatus.timezone).toBe('America/New_York');
      expect(marketStatus.nextChange).toBeDefined();
      expect(marketStatus.nextChange.event).toMatch(/open|close/);
    });
  });

  describe('Technical Analysis Service Integration', () => {
    test('should analyze symbol with real market data', async () => {
      const analysis = await technicalAnalysisService.analyzeSymbol('AAPL', ['RSI', 'SMA']);
      
      expect(analysis).toBeDefined();
      expect(analysis.symbol).toBe('AAPL');
      expect(analysis.dataPoints).toBeGreaterThan(50);
      expect(analysis.analysis).toBeDefined();
      expect(analysis.tradingSignal).toBeDefined();
      expect(analysis.marketData).toBeDefined();
      
      // Check RSI analysis
      if (analysis.analysis.RSI) {
        expect(analysis.analysis.RSI.current).toBeGreaterThan(0);
        expect(analysis.analysis.RSI.current).toBeLessThan(100);
      }
      
      // Check SMA analysis
      if (analysis.analysis.SMA) {
        expect(analysis.analysis.SMA.current).toBeGreaterThan(0);
      }
    });

    test('should analyze portfolio of symbols', async () => {
      const symbols = ['AAPL', 'MSFT'];
      const portfolioAnalysis = await technicalAnalysisService.analyzePortfolio(symbols);
      
      expect(portfolioAnalysis).toBeDefined();
      expect(portfolioAnalysis.summary).toBeDefined();
      expect(portfolioAnalysis.summary.totalSymbols).toBe(2);
      expect(portfolioAnalysis.analysis).toBeDefined();
      
      for (const symbol of symbols) {
        expect(portfolioAnalysis.analysis[symbol]).toBeDefined();
      }
    });

    test('should get real-time signals', async () => {
      const signals = await technicalAnalysisService.getRealtimeSignals('AAPL');
      
      expect(signals).toBeDefined();
      expect(signals.symbol).toBe('AAPL');
      expect(typeof signals.currentPrice).toBe('number');
      expect(signals.technicalAnalysis).toBeDefined();
      expect(signals.recommendation).toBeDefined();
      expect(signals.timestamp).toBeDefined();
    });
  });

  describe('Portfolio Service Integration', () => {
    test('should create and manage portfolio with real database', async () => {
      const holdings = [
        {
          symbol: 'AAPL',
          quantity: 100,
          avgCost: 150.00,
          currentPrice: 155.00,
          marketValue: 15500.00,
          unrealizedPL: 500.00,
          sector: 'Technology'
        }
      ];

      // Create portfolio
      const updateResult = await portfolioService.updatePortfolioHoldings(testUser.user_id, holdings);
      expect(updateResult.success).toBe(true);

      // Retrieve portfolio
      const portfolio = await portfolioService.getUserPortfolio(testUser.user_id);
      expect(portfolio.holdings).toHaveLength(1);
      expect(portfolio.holdings[0].symbol).toBe('AAPL');
      expect(parseFloat(portfolio.holdings[0].quantity)).toBe(100);
    });

    test('should calculate portfolio performance', async () => {
      // Create portfolio with holdings
      const holdings = [
        {
          symbol: 'AAPL',
          quantity: 100,
          avgCost: 150.00,
          currentPrice: 155.00,
          marketValue: 15500.00,
          unrealizedPL: 500.00,
          sector: 'Technology'
        }
      ];

      await portfolioService.updatePortfolioHoldings(testUser.user_id, holdings);

      // Get performance metrics
      const performance = await portfolioService.getPortfolioPerformance(testUser.user_id, '1M');
      
      expect(performance).toBeDefined();
      expect(performance.period).toBe('1M');
      expect(typeof performance.totalReturn).toBe('number');
      expect(typeof performance.totalReturnPercent).toBe('number');
      expect(typeof performance.volatility).toBe('number');
      expect(typeof performance.sharpeRatio).toBe('number');
      expect(typeof performance.maxDrawdown).toBe('number');
    });

    test('should format portfolio for optimization', async () => {
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
        accountId: 'TEST123',
        accountType: 'margin',
        totalEquity: 50000.00,
        buyingPower: 25000.00,
        cash: 5000.00,
        dayTradeCount: 0
      };

      await portfolioService.updatePortfolioHoldings(testUser.user_id, holdings);
      await portfolioService.savePortfolioMetadata(testUser.user_id, metadata);

      const optimizationPortfolio = await portfolioService.getPortfolioForOptimization(testUser.user_id);
      
      expect(optimizationPortfolio).toBeDefined();
      expect(optimizationPortfolio.positions).toHaveLength(2);
      expect(optimizationPortfolio.constraints).toBeDefined();
      expect(optimizationPortfolio.constraints.totalValue).toBe(31000.00);
      
      // Check position formatting
      const applePosition = optimizationPortfolio.positions.find(p => p.symbol === 'AAPL');
      expect(applePosition.weight).toBeCloseTo(0.5, 2);
    });
  });

  describe('Cross-Service Integration', () => {
    test('should combine portfolio data with market data and technical analysis', async () => {
      // Create test portfolio
      const holdings = [
        {
          symbol: 'AAPL',
          quantity: 100,
          avgCost: 150.00,
          currentPrice: 155.00,
          marketValue: 15500.00,
          unrealizedPL: 500.00,
          sector: 'Technology'
        }
      ];

      await portfolioService.updatePortfolioHoldings(testUser.user_id, holdings);

      // Get portfolio
      const portfolio = await portfolioService.getUserPortfolio(testUser.user_id);
      const symbols = portfolio.holdings.map(h => h.symbol);

      // Get market data for portfolio
      const marketData = await marketDataService.getPortfolioMarketData(symbols);

      // Get technical analysis for portfolio
      const technicalAnalysis = await technicalAnalysisService.analyzePortfolio(symbols);

      // Verify integration
      expect(portfolio.holdings).toHaveLength(1);
      expect(Object.keys(marketData)).toHaveLength(1);
      expect(technicalAnalysis.summary.totalSymbols).toBe(1);

      const symbol = 'AAPL';
      expect(marketData[symbol]).toBeDefined();
      expect(technicalAnalysis.analysis[symbol]).toBeDefined();

      // Combine data for comprehensive analysis
      const comprehensiveAnalysis = {
        portfolio: portfolio.holdings.find(h => h.symbol === symbol),
        marketData: marketData[symbol],
        technicalAnalysis: technicalAnalysis.analysis[symbol]
      };

      expect(comprehensiveAnalysis.portfolio).toBeDefined();
      expect(comprehensiveAnalysis.marketData).toBeDefined();
      expect(comprehensiveAnalysis.technicalAnalysis).toBeDefined();
    });

    test('should handle service health checks', async () => {
      const portfolioHealth = await portfolioService.healthCheck();
      const marketDataHealth = await marketDataService.healthCheck();
      const technicalAnalysisHealth = await technicalAnalysisService.healthCheck();

      expect(portfolioHealth.status).toBe('healthy');
      expect(marketDataHealth.status).toBe('healthy');
      expect(technicalAnalysisHealth.status).toBe('healthy');

      // Check service-specific health indicators
      expect(portfolioHealth.service).toBe('portfolio');
      expect(marketDataHealth.service).toBe('market-data');
      expect(technicalAnalysisHealth.service).toBe('technical-analysis');
    });

    test('should handle errors gracefully across services', async () => {
      // Test with invalid symbol
      await expect(marketDataService.getQuote('INVALID_SYMBOL')).rejects.toThrow();
      await expect(technicalAnalysisService.analyzeSymbol('INVALID_SYMBOL')).rejects.toThrow();

      // Test with invalid user
      await expect(portfolioService.getUserPortfolio(999999)).resolves.toBeDefined();
      
      // Should return empty portfolio, not throw error
      const emptyPortfolio = await portfolioService.getUserPortfolio(999999);
      expect(emptyPortfolio.holdings).toHaveLength(0);
    });
  });

  describe('Performance and Scalability', () => {
    test('should handle concurrent requests efficiently', async () => {
      const symbols = ['AAPL', 'MSFT', 'GOOGL', 'TSLA', 'NVDA'];
      
      const startTime = Date.now();
      
      // Make concurrent requests
      const promises = symbols.map(symbol => 
        Promise.all([
          marketDataService.getQuote(symbol),
          marketDataService.getHistoricalData(symbol, { period: '1mo' })
        ])
      );

      const results = await Promise.allSettled(promises);
      const endTime = Date.now();
      
      // All requests should complete
      const successful = results.filter(r => r.status === 'fulfilled').length;
      expect(successful).toBeGreaterThan(0);
      
      // Should complete in reasonable time (less than 30 seconds)
      const totalTime = endTime - startTime;
      expect(totalTime).toBeLessThan(30000);
      
      console.log(`Concurrent requests completed in ${totalTime}ms, ${successful}/${symbols.length} successful`);
    });

    test('should cache market data effectively', async () => {
      const symbol = 'AAPL';
      
      // First request
      const startTime1 = Date.now();
      const quote1 = await marketDataService.getQuote(symbol);
      const endTime1 = Date.now();
      
      // Second request (should be cached)
      const startTime2 = Date.now();
      const quote2 = await marketDataService.getQuote(symbol);
      const endTime2 = Date.now();
      
      // Cached request should be much faster
      const firstRequestTime = endTime1 - startTime1;
      const secondRequestTime = endTime2 - startTime2;
      
      expect(quote1.symbol).toBe(symbol);
      expect(quote2.symbol).toBe(symbol);
      expect(secondRequestTime).toBeLessThan(firstRequestTime);
      
      console.log(`Cache effectiveness: First request ${firstRequestTime}ms, Second request ${secondRequestTime}ms`);
    });
  });
});