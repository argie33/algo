/**
 * Optimization Engine Unit Tests
 * Comprehensive tests for portfolio optimization functionality
 */

const OptimizationEngine = require('../../services/optimizationEngine');

// Mock dependencies
jest.mock('../../utils/portfolioMath', () => ({
  calculateExpectedReturns: jest.fn(),
  calculateCovarianceMatrix: jest.fn(),
  calculateCorrelationMatrix: jest.fn(),
  meanVarianceOptimization: jest.fn(),
  generateEfficientFrontier: jest.fn(),
  calculateRiskMetrics: jest.fn()
}));

jest.mock('../../utils/database', () => ({
  query: jest.fn()
}));

describe('Optimization Engine Unit Tests', () => {
  let optimizationEngine;
  let mockPortfolioMath;
  let mockQuery;

  beforeEach(() => {
    optimizationEngine = new OptimizationEngine();
    
    // Get mocked modules
    mockPortfolioMath = require('../../utils/portfolioMath');
    mockQuery = require('../../utils/database').query;
    
    // Reset all mocks
    jest.clearAllMocks();
  });

  describe('Service Initialization', () => {
    test('initializes with default risk-free rate', () => {
      expect(optimizationEngine.riskFreeRate).toBe(0.02);
    });

    test('has all required methods', () => {
      expect(typeof optimizationEngine.runOptimization).toBe('function');
      expect(typeof optimizationEngine.getCurrentPortfolio).toBe('function');
      expect(typeof optimizationEngine.getDemoPortfolio).toBe('function');
      expect(typeof optimizationEngine.getOptimizationUniverse).toBe('function');
      expect(typeof optimizationEngine.calculateRebalancing).toBe('function');
      expect(typeof optimizationEngine.generateOptimizationInsights).toBe('function');
    });
  });

  describe('Current Portfolio Retrieval', () => {
    test('retrieves portfolio from database successfully', async () => {
      const mockDbResult = {
        rows: [
          {
            symbol: 'AAPL',
            quantity: '100',
            market_value: '15000',
            avg_cost: '150',
            pnl: '2000',
            pnl_percent: '15.4'
          },
          {
            symbol: 'MSFT',
            quantity: '50',
            market_value: '12500',
            avg_cost: '200',
            pnl: '2500',
            pnl_percent: '25.0'
          }
        ]
      };

      mockQuery.mockResolvedValue(mockDbResult);

      const portfolio = await optimizationEngine.getCurrentPortfolio(123);

      expect(portfolio).toBeDefined();
      expect(portfolio.holdings).toHaveLength(2);
      expect(portfolio.totalValue).toBe(27500);
      expect(portfolio.numPositions).toBe(2);
      
      // Check first holding
      expect(portfolio.holdings[0]).toEqual({
        symbol: 'AAPL',
        quantity: 100,
        marketValue: 15000,
        weight: 15000 / 27500,
        avgCost: 150,
        pnl: 2000,
        pnlPercent: 15.4
      });
      
      expect(mockQuery).toHaveBeenCalledWith(
        expect.stringContaining('SELECT'),
        [123]
      );
    });

    test('returns demo portfolio when database query fails', async () => {
      mockQuery.mockRejectedValue(new Error('Database connection failed'));

      const portfolio = await optimizationEngine.getCurrentPortfolio(123);

      expect(portfolio).toBeDefined();
      expect(portfolio.holdings).toHaveLength(4);
      expect(portfolio.totalValue).toBe(50000);
      expect(portfolio.holdings[0].symbol).toBe('AAPL');
    });

    test('returns demo portfolio when no holdings found', async () => {
      mockQuery.mockResolvedValue({ rows: [] });

      const portfolio = await optimizationEngine.getCurrentPortfolio(123);

      expect(portfolio).toBeDefined();
      expect(portfolio.holdings).toHaveLength(4);
      expect(portfolio.totalValue).toBe(50000);
    });

    test('calculates portfolio weights correctly', async () => {
      const mockDbResult = {
        rows: [
          { symbol: 'AAPL', quantity: '100', market_value: '30000', avg_cost: '300', pnl: '5000', pnl_percent: '20' },
          { symbol: 'MSFT', quantity: '200', market_value: '20000', avg_cost: '100', pnl: '10000', pnl_percent: '100' }
        ]
      };

      mockQuery.mockResolvedValue(mockDbResult);

      const portfolio = await optimizationEngine.getCurrentPortfolio(123);

      expect(portfolio.holdings[0].weight).toBe(0.6); // 30000/50000
      expect(portfolio.holdings[1].weight).toBe(0.4); // 20000/50000
    });
  });

  describe('Demo Portfolio', () => {
    test('generates consistent demo portfolio', () => {
      const portfolio = optimizationEngine.getDemoPortfolio();

      expect(portfolio).toBeDefined();
      expect(portfolio.holdings).toHaveLength(4);
      expect(portfolio.totalValue).toBe(50000);
      expect(portfolio.numPositions).toBe(4);

      // Check specific holdings
      const aapl = portfolio.holdings.find(h => h.symbol === 'AAPL');
      expect(aapl).toBeDefined();
      expect(aapl.marketValue).toBe(17500);
      expect(aapl.weight).toBe(0.35);
    });

    test('demo portfolio weights sum to 1', () => {
      const portfolio = optimizationEngine.getDemoPortfolio();
      const totalWeight = portfolio.holdings.reduce((sum, h) => sum + h.weight, 0);
      
      expect(totalWeight).toBeCloseTo(1.0, 10); // Use toBeCloseTo for floating point precision
    });
  });

  describe('Optimization Universe', () => {
    test('creates universe from current holdings', async () => {
      const currentPortfolio = {
        holdings: [
          { symbol: 'AAPL' },
          { symbol: 'MSFT' },
          { symbol: 'GOOGL' }
        ]
      };

      const universe = await optimizationEngine.getOptimizationUniverse(currentPortfolio);

      expect(universe).toContain('AAPL');
      expect(universe).toContain('MSFT');
      expect(universe).toContain('GOOGL');
    });

    test('includes additional assets for diversification', async () => {
      const currentPortfolio = {
        holdings: [
          { symbol: 'AAPL' },
          { symbol: 'MSFT' }
        ]
      };

      const universe = await optimizationEngine.getOptimizationUniverse(currentPortfolio);

      expect(universe.length).toBeGreaterThan(2);
      expect(universe).toContain('AAPL');
      expect(universe).toContain('MSFT');
    });

    test('respects include and exclude assets', async () => {
      const currentPortfolio = {
        holdings: [{ symbol: 'AAPL' }]
      };

      const universe = await optimizationEngine.getOptimizationUniverse(
        currentPortfolio,
        ['TSLA', 'NVDA'], // include
        ['AAPL'] // exclude
      );

      expect(universe).toContain('TSLA');
      expect(universe).toContain('NVDA');
      expect(universe).not.toContain('AAPL');
    });

    test('limits universe size to 20 assets', async () => {
      const currentPortfolio = {
        holdings: Array.from({ length: 25 }, (_, i) => ({ symbol: `STOCK${i}` }))
      };

      const universe = await optimizationEngine.getOptimizationUniverse(currentPortfolio);

      expect(universe.length).toBeLessThanOrEqual(20);
    });
  });

  describe('Historical Price Data', () => {
    test('generates mock price data for symbols', async () => {
      const symbols = ['AAPL', 'MSFT'];
      const lookbackDays = 30;

      const priceData = await optimizationEngine.getHistoricalPrices(symbols, lookbackDays);

      expect(Object.keys(priceData)).toEqual(['AAPL', 'MSFT']);
      expect(priceData.AAPL).toHaveLength(30);
      expect(priceData.MSFT).toHaveLength(30);

      // Check price data structure
      expect(priceData.AAPL[0]).toHaveProperty('date');
      expect(priceData.AAPL[0]).toHaveProperty('close');
      expect(priceData.AAPL[0]).toHaveProperty('symbol');
      expect(priceData.AAPL[0].symbol).toBe('AAPL');
    });

    test('generates realistic price movements', async () => {
      const priceData = await optimizationEngine.getHistoricalPrices(['AAPL'], 100);
      const prices = priceData.AAPL.map(d => d.close);
      
      // Check that prices are positive
      prices.forEach(price => {
        expect(price).toBeGreaterThan(0);
      });

      // Check that prices have reasonable variance
      const minPrice = Math.min(...prices);
      const maxPrice = Math.max(...prices);
      const volatility = (maxPrice - minPrice) / minPrice;
      
      expect(volatility).toBeGreaterThan(0);
      expect(volatility).toBeLessThan(2); // Reasonable bounds
    });
  });

  describe('Returns Matrix Calculation', () => {
    test('calculates returns matrix from price data', () => {
      const mockPriceData = {
        AAPL: [
          { date: '2023-01-01', close: 100, symbol: 'AAPL' },
          { date: '2023-01-02', close: 105, symbol: 'AAPL' },
          { date: '2023-01-03', close: 102, symbol: 'AAPL' }
        ],
        MSFT: [
          { date: '2023-01-01', close: 200, symbol: 'MSFT' },
          { date: '2023-01-02', close: 210, symbol: 'MSFT' },
          { date: '2023-01-03', close: 205, symbol: 'MSFT' }
        ]
      };

      const returnsData = optimizationEngine.calculateReturnsMatrix(mockPriceData);

      expect(returnsData.returns).toHaveLength(2); // 3 prices -> 2 returns
      expect(returnsData.symbols).toEqual(['AAPL', 'MSFT']);
      expect(returnsData.dates).toEqual(['2023-01-02', '2023-01-03']);

      // Check calculated returns
      expect(returnsData.returns[0]).toHaveLength(2); // 2 assets
      expect(returnsData.returns[0][0]).toBeCloseTo(0.05); // AAPL: (105-100)/100 = 5%
      expect(returnsData.returns[0][1]).toBeCloseTo(0.05); // MSFT: (210-200)/200 = 5%
      expect(returnsData.returns[1][0]).toBeCloseTo(-0.0286, 3); // AAPL: (102-105)/105 ≈ -2.86%
      expect(returnsData.returns[1][1]).toBeCloseTo(-0.0238, 3); // MSFT: (205-210)/210 ≈ -2.38%
    });

    test('handles empty price data', () => {
      const returnsData = optimizationEngine.calculateReturnsMatrix({});

      expect(returnsData.returns).toEqual([]);
      expect(returnsData.dates).toEqual([]);
      expect(returnsData.symbols).toEqual([]);
    });

    test('handles single price point', () => {
      const mockPriceData = {
        AAPL: [{ date: '2023-01-01', close: 100, symbol: 'AAPL' }]
      };

      const returnsData = optimizationEngine.calculateReturnsMatrix(mockPriceData);

      expect(returnsData.returns).toEqual([]);
      expect(returnsData.dates).toEqual([]);
    });
  });

  describe('Rebalancing Calculations', () => {
    test('calculates rebalancing trades correctly', async () => {
      const currentPortfolio = {
        totalValue: 100000,
        holdings: [
          { symbol: 'AAPL', weight: 0.5, marketValue: 50000 },
          { symbol: 'MSFT', weight: 0.3, marketValue: 30000 },
          { symbol: 'GOOGL', weight: 0.2, marketValue: 20000 }
        ]
      };
      const universe = ['AAPL', 'MSFT', 'GOOGL'];
      const targetWeights = [0.4, 0.4, 0.2]; // Target allocations

      const rebalancing = await optimizationEngine.calculateRebalancing(
        currentPortfolio, 
        universe, 
        targetWeights
      );

      expect(rebalancing).toHaveLength(2); // Only AAPL and MSFT need rebalancing (>1% threshold)
      
      const aaplTrade = rebalancing.find(r => r.symbol === 'AAPL');
      const msftTrade = rebalancing.find(r => r.symbol === 'MSFT');

      expect(aaplTrade).toEqual({
        symbol: 'AAPL',
        currentWeight: 50,
        targetWeight: 40,
        currentValue: 50000,
        targetValue: 40000,
        tradeValue: -10000,
        action: 'SELL',
        priority: 'High'
      });

      expect(msftTrade).toEqual({
        symbol: 'MSFT',
        currentWeight: 30,
        targetWeight: 40,
        currentValue: 30000,
        targetValue: 40000,
        tradeValue: 10000,
        action: 'BUY',
        priority: 'High'
      });
    });

    test('ignores small weight differences', async () => {
      const currentPortfolio = {
        totalValue: 100000,
        holdings: [
          { symbol: 'AAPL', weight: 0.305, marketValue: 30500 }
        ]
      };
      const universe = ['AAPL'];
      const targetWeights = [0.30]; // Only 0.5% difference

      const rebalancing = await optimizationEngine.calculateRebalancing(
        currentPortfolio, 
        universe, 
        targetWeights
      );

      expect(rebalancing).toHaveLength(0); // Below 1% threshold
    });

    test('sorts trades by priority and value', async () => {
      const currentPortfolio = {
        totalValue: 100000,
        holdings: [
          { symbol: 'AAPL', weight: 0.4, marketValue: 40000 },
          { symbol: 'MSFT', weight: 0.3, marketValue: 30000 },
          { symbol: 'GOOGL', weight: 0.3, marketValue: 30000 }
        ]
      };
      const universe = ['AAPL', 'MSFT', 'GOOGL'];
      const targetWeights = [0.5, 0.25, 0.25]; // Different rebalancing amounts

      const rebalancing = await optimizationEngine.calculateRebalancing(
        currentPortfolio, 
        universe, 
        targetWeights
      );

      // Should be sorted by priority first, then by absolute trade value
      expect(rebalancing[0].priority).toBe('High');
      expect(Math.abs(rebalancing[0].tradeValue)).toBeGreaterThanOrEqual(
        Math.abs(rebalancing[rebalancing.length - 1].tradeValue)
      );
    });
  });

  describe('Optimization Insights', () => {
    test('generates risk warning for high volatility', () => {
      const optimization = { sharpeRatio: 1.0, weights: [0.5, 0.5] };
      const riskMetrics = { volatility: 0.25 };
      const corrMatrix = [];
      const universe = ['AAPL', 'MSFT'];
      const currentPortfolio = {};

      const insights = optimizationEngine.generateOptimizationInsights(
        currentPortfolio, optimization, riskMetrics, corrMatrix, universe
      );

      const riskInsight = insights.find(i => i.category === 'Risk');
      expect(riskInsight).toBeDefined();
      expect(riskInsight.type).toBe('warning');
      expect(riskInsight.title).toBe('High Portfolio Volatility');
    });

    test('generates diversification insight for small portfolios', () => {
      const optimization = { sharpeRatio: 1.0, weights: [0.5, 0.5] };
      const riskMetrics = { volatility: 0.15 };
      const corrMatrix = [];
      const universe = ['AAPL', 'MSFT']; // Only 2 assets
      const currentPortfolio = {};

      const insights = optimizationEngine.generateOptimizationInsights(
        currentPortfolio, optimization, riskMetrics, corrMatrix, universe
      );

      const diversificationInsight = insights.find(i => i.category === 'Diversification');
      expect(diversificationInsight).toBeDefined();
      expect(diversificationInsight.type).toBe('info');
      expect(diversificationInsight.title).toBe('Limited Diversification');
    });

    test('generates positive insight for high Sharpe ratio', () => {
      const optimization = { sharpeRatio: 1.8, weights: [0.5, 0.5] };
      const riskMetrics = { volatility: 0.15 };
      const corrMatrix = [];
      const universe = ['AAPL', 'MSFT', 'GOOGL', 'AMZN', 'TSLA', 'NVDA', 'META', 'NFLX', 'JPM', 'JNJ'];
      const currentPortfolio = {};

      const insights = optimizationEngine.generateOptimizationInsights(
        currentPortfolio, optimization, riskMetrics, corrMatrix, universe
      );

      const performanceInsight = insights.find(i => i.category === 'Performance');
      expect(performanceInsight).toBeDefined();
      expect(performanceInsight.type).toBe('success');
      expect(performanceInsight.title).toBe('Excellent Risk-Adjusted Returns');
    });

    test('generates concentration warning for large positions', () => {
      const optimization = { sharpeRatio: 1.0, weights: [0.6, 0.4] }; // 60% concentration
      const riskMetrics = { volatility: 0.15 };
      const corrMatrix = [];
      const universe = ['AAPL', 'MSFT'];
      const currentPortfolio = {};

      const insights = optimizationEngine.generateOptimizationInsights(
        currentPortfolio, optimization, riskMetrics, corrMatrix, universe
      );

      const concentrationInsight = insights.find(i => i.category === 'Concentration');
      expect(concentrationInsight).toBeDefined();
      expect(concentrationInsight.type).toBe('warning');
      expect(concentrationInsight.title).toBe('High Concentration Risk');
    });
  });

  describe('Formatting Functions', () => {
    test('formats weights correctly', () => {
      const universe = ['AAPL', 'MSFT', 'GOOGL'];
      const weights = [0.4567, 0.3210, 0.2223];

      const formatted = optimizationEngine.formatWeights(universe, weights);

      expect(formatted).toHaveLength(3);
      expect(formatted[0]).toEqual({
        symbol: 'AAPL',
        weight: 45.67,
        allocation: 0.4567
      });
      expect(formatted[1]).toEqual({
        symbol: 'MSFT',
        weight: 32.1,
        allocation: 0.3210
      });
    });

    test('formats portfolio summary correctly', () => {
      const portfolio = {
        totalValue: 123456.78,
        numPositions: 5,
        holdings: [
          { symbol: 'AAPL', weight: 0.3567, marketValue: 44000, pnl: 5000, pnlPercent: 12.8 },
          { symbol: 'MSFT', weight: 0.2234, marketValue: 27500, pnl: 2500, pnlPercent: 10.0 },
          { symbol: 'GOOGL', weight: 0.1999, marketValue: 24680, pnl: 1680, pnlPercent: 7.3 },
          { symbol: 'AMZN', weight: 0.1200, marketValue: 14800, pnl: 800, pnlPercent: 5.7 },
          { symbol: 'TSLA', weight: 0.1000, marketValue: 12347, pnl: -653, pnlPercent: -5.0 }
        ]
      };

      const formatted = optimizationEngine.formatPortfolioSummary(portfolio);

      expect(formatted.totalValue).toBe(123456.78);
      expect(formatted.numPositions).toBe(5);
      expect(formatted.topHoldings).toHaveLength(5);
      expect(formatted.topHoldings[0]).toEqual({
        symbol: 'AAPL',
        weight: 35.67,
        marketValue: 44000,
        pnl: 5000,
        pnlPercent: 12.8
      });
    });

    test('formats correlation matrix correctly', () => {
      const universe = ['AAPL', 'MSFT', 'GOOGL'];
      const mockCorrMatrix = {
        get: jest.fn((i, j) => {
          const correlations = {
            '0,1': 0.85, // AAPL-MSFT high correlation
            '0,2': 0.45, // AAPL-GOOGL moderate correlation (filtered out)
            '1,2': 0.92  // MSFT-GOOGL very high correlation
          };
          return correlations[`${i},${j}`] || 0;
        })
      };

      const formatted = optimizationEngine.formatCorrelationMatrix(universe, mockCorrMatrix);

      expect(formatted).toHaveLength(2); // Only high correlations (>0.7)
      expect(formatted[0]).toEqual({
        asset1: 'MSFT',
        asset2: 'GOOGL',
        correlation: 0.92,
        strength: 'Very High'
      });
      expect(formatted[1]).toEqual({
        asset1: 'AAPL',
        asset2: 'MSFT',
        correlation: 0.85,
        strength: 'High'
      });
    });
  });

  describe('Data Quality Assessment', () => {
    test('assesses high-quality data correctly', () => {
      const priceData = {
        AAPL: [
          { close: 150.0 },
          { close: 151.5 },
          { close: 149.8 }
        ],
        MSFT: [
          { close: 250.0 },
          { close: 252.5 },
          { close: 248.7 }
        ]
      };
      const returnsData = {}; // Not used in assessment

      const quality = optimizationEngine.assessDataQuality(priceData, returnsData);

      expect(quality.score).toBe(100);
      expect(quality.assessment).toBe('Excellent');
      expect(quality.totalDataPoints).toBe(6);
      expect(quality.missingDataPoints).toBe(0);
      expect(quality.symbols).toBe(2);
    });

    test('identifies missing data points', () => {
      const priceData = {
        AAPL: [
          { close: 150.0 },
          { close: null }, // Missing data
          { close: 149.8 }
        ],
        MSFT: [
          { close: 250.0 },
          { close: 0 }, // Invalid price
          { close: 248.7 }
        ]
      };
      const returnsData = {};

      const quality = optimizationEngine.assessDataQuality(priceData, returnsData);

      expect(quality.score).toBe(67); // 4 good out of 6 total
      expect(quality.assessment).toBe('Poor'); // 67% is Poor (< 80%)
      expect(quality.missingDataPoints).toBe(2);
    });
  });

  describe('Fallback Optimization', () => {
    test('generates fallback optimization with demo data', () => {
      const fallback = optimizationEngine.generateFallbackOptimization(123, 'maxSharpe');

      expect(fallback.success).toBe(true);
      expect(fallback.optimization.objective).toBe('maxSharpe');
      expect(fallback.optimization.weights).toHaveLength(5);
      expect(fallback.currentPortfolio).toBeDefined();
      expect(fallback.rebalancing).toHaveLength(1);
      expect(fallback.insights).toHaveLength(1);
      expect(fallback.insights[0].title).toBe('Using Demo Data');
    });

    test('uses equal weights for equalWeight objective', () => {
      const fallback = optimizationEngine.generateFallbackOptimization(123, 'equalWeight');

      fallback.optimization.weights.forEach(weight => {
        expect(weight.weight).toBe(20); // 20% each for 5 assets
      });
    });

    test('generates mock efficient frontier', () => {
      const frontier = optimizationEngine.generateMockEfficientFrontier();

      expect(frontier).toHaveLength(20);
      frontier.forEach(point => {
        expect(point).toHaveProperty('volatility');
        expect(point).toHaveProperty('expectedReturn');
        expect(point).toHaveProperty('sharpeRatio');
        expect(point.volatility).toBeGreaterThan(0);
        expect(point.expectedReturn).toBeGreaterThan(0);
      });

      // Check risk-return relationship (higher volatility should generally mean higher return)
      expect(frontier[0].volatility).toBeLessThan(frontier[19].volatility);
      expect(frontier[0].expectedReturn).toBeLessThan(frontier[19].expectedReturn);
    });
  });

  describe('Full Optimization Integration', () => {
    test('runs complete optimization successfully', async () => {
      // Mock all dependencies
      mockQuery.mockResolvedValue({
        rows: [
          { symbol: 'AAPL', quantity: '100', market_value: '15000', avg_cost: '150', pnl: '2000', pnl_percent: '15' }
        ]
      });

      mockPortfolioMath.calculateExpectedReturns.mockReturnValue([0.10, 0.08, 0.12]);
      mockPortfolioMath.calculateCovarianceMatrix.mockReturnValue([[0.04, 0.02], [0.02, 0.03]]);
      mockPortfolioMath.calculateCorrelationMatrix.mockReturnValue({
        get: jest.fn().mockReturnValue(0.5)
      });
      mockPortfolioMath.meanVarianceOptimization.mockReturnValue({
        weights: [0.4, 0.3, 0.3],
        expectedReturn: 0.10,
        volatility: 0.15,
        sharpeRatio: 1.2
      });
      mockPortfolioMath.generateEfficientFrontier.mockReturnValue([
        { volatility: 0.1, expectedReturn: 0.08, sharpeRatio: 0.8 }
      ]);
      mockPortfolioMath.calculateRiskMetrics.mockReturnValue({
        expectedReturn: 0.10,
        volatility: 0.15,
        sharpeRatio: 1.2,
        beta: 1.05
      });

      const result = await optimizationEngine.runOptimization({
        userId: 123,
        objective: 'maxSharpe'
      });

      expect(result.success).toBe(true);
      expect(result.optimization).toBeDefined();
      expect(result.currentPortfolio).toBeDefined();
      expect(result.rebalancing).toBeDefined();
      expect(result.riskMetrics).toBeDefined();
      expect(result.efficientFrontier).toBeDefined();
      expect(result.metadata).toBeDefined();

      // Verify all PortfolioMath functions were called
      expect(mockPortfolioMath.calculateExpectedReturns).toHaveBeenCalled();
      expect(mockPortfolioMath.meanVarianceOptimization).toHaveBeenCalled();
      expect(mockPortfolioMath.generateEfficientFrontier).toHaveBeenCalled();
    });

    test('falls back to demo optimization on error', async () => {
      // Mock database to throw error
      mockQuery.mockRejectedValue(new Error('Database connection failed'));

      const result = await optimizationEngine.runOptimization({
        userId: 123,
        objective: 'maxSharpe'
      });

      expect(result.success).toBe(true);
      expect(result.insights).toHaveLength(1);
      expect(result.insights[0]).toHaveProperty('title', 'Using Demo Data');
      expect(result.metadata.dataQuality.assessment).toBe('Demo Data');
    });
  });

  describe('Mock Price Data Generation', () => {
    test('generates price data with correct structure', () => {
      const startDate = new Date('2023-01-01');
      const endDate = new Date('2023-01-10');
      
      const prices = optimizationEngine.generateMockPriceData('AAPL', startDate, endDate);

      expect(prices).toHaveLength(9); // Jan 1-9 is 9 days, not 10
      prices.forEach((price, index) => {
        expect(price).toHaveProperty('date');
        expect(price).toHaveProperty('close');
        expect(price).toHaveProperty('symbol', 'AAPL');
        expect(price.close).toBeGreaterThan(0);
      });
    });

    test('applies different volatility for different assets', () => {
      const startDate = new Date('2023-01-01');
      const endDate = new Date('2023-01-30');
      
      const tslaPrices = optimizationEngine.generateMockPriceData('TSLA', startDate, endDate);
      const spyPrices = optimizationEngine.generateMockPriceData('SPY', startDate, endDate);

      // TSLA should have higher volatility than SPY
      const tslaVolatility = calculateVolatility(tslaPrices.map(p => p.close));
      const spyVolatility = calculateVolatility(spyPrices.map(p => p.close));

      expect(tslaVolatility).toBeGreaterThan(spyVolatility);
    });
  });
});

// Helper function to calculate price volatility
function calculateVolatility(prices) {
  const returns = [];
  for (let i = 1; i < prices.length; i++) {
    returns.push((prices[i] - prices[i-1]) / prices[i-1]);
  }
  
  const meanReturn = returns.reduce((sum, r) => sum + r, 0) / returns.length;
  const variance = returns.reduce((sum, r) => sum + Math.pow(r - meanReturn, 2), 0) / returns.length;
  
  return Math.sqrt(variance);
}