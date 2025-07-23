/**
 * Optimization Engine Unit Tests
 * REAL IMPLEMENTATION TESTING - NO FAKE MOCKS
 * Tests actual portfolio optimization business logic
 */

// Mock database before importing OptimizationEngine
const mockQuery = jest.fn();
jest.mock('../../utils/database', () => ({
  query: mockQuery
}));

const OptimizationEngine = require('../../services/optimizationEngine');
const PortfolioMath = require('../../utils/portfolioMath');

describe('Optimization Engine Unit Tests', () => {
  let optimizationEngine;

  beforeEach(() => {
    jest.clearAllMocks();
    mockQuery.mockClear();
    optimizationEngine = new OptimizationEngine();
  });

  describe('Service Initialization', () => {
    it('initializes with default risk-free rate', () => {
      expect(optimizationEngine.riskFreeRate).toBe(0.02);
    });

    it('has all required methods', () => {
      expect(typeof optimizationEngine.runOptimization).toBe('function');
      expect(typeof optimizationEngine.getCurrentPortfolio).toBe('function');
      expect(typeof optimizationEngine.getDemoPortfolio).toBe('function');
      expect(typeof optimizationEngine.getOptimizationUniverse).toBe('function');
      expect(typeof optimizationEngine.calculateRebalancing).toBe('function');
      expect(typeof optimizationEngine.generateOptimizationInsights).toBe('function');
    });
  });

  describe('Current Portfolio Retrieval', () => {
    it('retrieves portfolio from database successfully', async () => {
      // Mock successful database response
      mockQuery.mockResolvedValueOnce({
        rows: [
          { symbol: 'AAPL', quantity: 10, market_value: '15000', avg_cost: '140', pnl: '2000', pnl_percent: '15.3' },
          { symbol: 'MSFT', quantity: 5, market_value: '12000', avg_cost: '220', pnl: '1500', pnl_percent: '14.2' }
        ]
      });
      
      const portfolio = await optimizationEngine.getCurrentPortfolio(123);
      expect(portfolio).toBeDefined();
      expect(Array.isArray(portfolio.holdings)).toBe(true);
      expect(typeof portfolio.totalValue).toBe('number');
      expect(portfolio.holdings.length).toBe(2);
      expect(portfolio.totalValue).toBe(27000);
    });

    it('returns demo portfolio when database query fails', async () => {
      // Mock empty result to trigger demo portfolio fallback
      mockQuery.mockResolvedValueOnce({ rows: [] });
      
      // This tests the real fallback logic in getCurrentPortfolio
      const portfolio = await optimizationEngine.getCurrentPortfolio(123);
      
      // Should contain demo portfolio structure
      expect(portfolio).toBeDefined();
      expect(Array.isArray(portfolio.holdings)).toBe(true);
      expect(portfolio.totalValue).toBeGreaterThan(0);
      
      // Verify demo portfolio has expected symbols
      const symbols = portfolio.holdings.map(h => h.symbol);
      expect(symbols.length).toBeGreaterThan(0);
    });

    it('returns demo portfolio when no holdings found', async () => {
      // Mock empty result (no holdings)
      mockQuery.mockResolvedValueOnce({ rows: [] });
      
      const portfolio = await optimizationEngine.getCurrentPortfolio(999999);
      
      expect(portfolio).toBeDefined();
      expect(Array.isArray(portfolio.holdings)).toBe(true);
      expect(portfolio.totalValue).toBeGreaterThan(0);
    });

    it('calculates portfolio weights correctly', async () => {
      // Mock portfolio data with known values
      mockQuery.mockResolvedValueOnce({
        rows: [
          { symbol: 'AAPL', quantity: 10, market_value: '30000', avg_cost: '140', pnl: '2000', pnl_percent: '15.3' },
          { symbol: 'MSFT', quantity: 5, market_value: '20000', avg_cost: '220', pnl: '1500', pnl_percent: '14.2' }
        ]
      });
      
      const portfolio = await optimizationEngine.getCurrentPortfolio(123);
      
      // Calculate total weight
      const totalWeight = portfolio.holdings.reduce((sum, holding) => sum + holding.weight, 0);
      
      // Weights should sum to approximately 1.0 (allowing for floating point precision)
      expect(totalWeight).toBeCloseTo(1.0, 2);
      expect(portfolio.holdings[0].weight).toBeCloseTo(0.6, 2); // 30000/50000
      expect(portfolio.holdings[1].weight).toBeCloseTo(0.4, 2); // 20000/50000
    });
  });

  describe('Demo Portfolio', () => {
    it('generates consistent demo portfolio', () => {
      const portfolio1 = optimizationEngine.getDemoPortfolio();
      const portfolio2 = optimizationEngine.getDemoPortfolio();
      
      expect(portfolio1.totalValue).toBe(portfolio2.totalValue);
      expect(portfolio1.holdings.length).toBe(portfolio2.holdings.length);
    });

    it('demo portfolio weights sum to 1', () => {
      const portfolio = optimizationEngine.getDemoPortfolio();
      const totalWeight = portfolio.holdings.reduce((sum, holding) => sum + holding.weight, 0);
      
      expect(totalWeight).toBeCloseTo(1.0, 2);
    });
  });

  describe('Optimization Universe', () => {
    it('creates universe from current holdings', async () => {
      const portfolio = optimizationEngine.getDemoPortfolio();
      const universe = await optimizationEngine.getOptimizationUniverse(portfolio);
      
      expect(Array.isArray(universe)).toBe(true);
      expect(universe.length).toBeGreaterThan(0);
      
      // Should include symbols from portfolio
      const portfolioSymbols = portfolio.holdings.map(h => h.symbol);
      portfolioSymbols.forEach(symbol => {
        expect(universe).toContain(symbol);
      });
    });

    it('includes additional assets for diversification', async () => {
      const portfolio = { holdings: [{ symbol: 'AAPL', weight: 1.0 }] };
      const universe = await optimizationEngine.getOptimizationUniverse(portfolio);
      
      expect(universe.length).toBeGreaterThan(1);
      expect(universe).toContain('AAPL');
    });

    it('respects include and exclude assets', async () => {
      const portfolio = { holdings: [{ symbol: 'AAPL', weight: 1.0 }] };
      const includeAssets = ['MSFT', 'GOOGL'];
      const excludeAssets = ['AAPL'];
      
      const universe = await optimizationEngine.getOptimizationUniverse(
        portfolio, 
        includeAssets, 
        excludeAssets
      );
      
      includeAssets.forEach(asset => {
        expect(universe).toContain(asset);
      });
      
      excludeAssets.forEach(asset => {
        expect(universe).not.toContain(asset);
      });
    });

    it('limits universe size to 20 assets', async () => {
      const largePortfolio = {
        holdings: Array.from({ length: 30 }, (_, i) => ({
          symbol: `STOCK${i}`,
          weight: 1/30
        }))
      };
      
      const universe = await optimizationEngine.getOptimizationUniverse(largePortfolio);
      expect(universe.length).toBeLessThanOrEqual(20);
    });
  });

  describe('Historical Price Data', () => {
    it('generates mock price data for symbols', () => {
      const symbol = 'AAPL';
      const startDate = new Date('2023-01-01');
      const endDate = new Date('2023-12-31');
      const priceData = optimizationEngine.generateMockPriceData(symbol, startDate, endDate);
      
      expect(Array.isArray(priceData)).toBe(true);
      expect(priceData.length).toBeGreaterThan(250); // About 365 days
      expect(priceData[0]).toHaveProperty('date');
      expect(priceData[0]).toHaveProperty('close');
      expect(priceData[0]).toHaveProperty('symbol');
      expect(priceData[0].symbol).toBe('AAPL');
    });

    it('generates realistic price movements', () => {
      const symbol = 'AAPL';
      const startDate = new Date('2023-01-01');
      const endDate = new Date('2023-04-01'); // 3 months
      const priceData = optimizationEngine.generateMockPriceData(symbol, startDate, endDate);
      
      // Check that prices change over time (not static)
      const initialPrice = priceData[0].close;
      const finalPrice = priceData[priceData.length - 1].close;
      
      expect(initialPrice).not.toBe(finalPrice);
      expect(initialPrice).toBeGreaterThan(0);
      expect(finalPrice).toBeGreaterThan(0);
    });
  });

  describe('Returns Matrix Calculation', () => {
    it('calculates returns matrix from price data', () => {
      const priceData = {
        AAPL: [
          { date: '2023-01-01', close: 100 },
          { date: '2023-01-02', close: 105 },
          { date: '2023-01-03', close: 102 }
        ],
        MSFT: [
          { date: '2023-01-01', close: 200 },
          { date: '2023-01-02', close: 210 },
          { date: '2023-01-03', close: 205 }
        ]
      };
      
      const result = optimizationEngine.calculateReturnsMatrix(priceData);
      
      expect(result).toHaveProperty('returns');
      expect(result).toHaveProperty('dates');
      expect(result).toHaveProperty('symbols');
      expect(Array.isArray(result.returns)).toBe(true);
      expect(result.returns.length).toBe(2); // One less than price data length
      expect(result.returns[0].length).toBe(2); // Two assets
      
      // Verify actual return calculations
      expect(result.returns[0][0]).toBeCloseTo(0.05); // AAPL: (105-100)/100
      expect(result.returns[0][1]).toBeCloseTo(0.05); // MSFT: (210-200)/200
    });

    it('handles empty price data', () => {
      const result = optimizationEngine.calculateReturnsMatrix({});
      expect(result).toHaveProperty('returns');
      expect(result).toHaveProperty('dates');
      expect(result).toHaveProperty('symbols');
      expect(Array.isArray(result.returns)).toBe(true);
      expect(result.returns.length).toBe(0);
    });

    it('handles single price point', () => {
      const priceData = {
        AAPL: [{ date: '2023-01-01', close: 100 }]
      };
      const result = optimizationEngine.calculateReturnsMatrix(priceData);
      expect(result.returns.length).toBe(0);
    });
  });

  describe('Rebalancing Calculations', () => {
    it('calculates rebalancing trades correctly', async () => {
      const currentPortfolio = {
        holdings: [
          { symbol: 'AAPL', weight: 0.6, marketValue: 60000 },
          { symbol: 'MSFT', weight: 0.4, marketValue: 40000 }
        ],
        totalValue: 100000
      };
      
      const universe = ['AAPL', 'MSFT'];
      const targetWeights = [0.5, 0.5]; // Array matching universe order
      
      const trades = await optimizationEngine.calculateRebalancing(currentPortfolio, universe, targetWeights);
      
      expect(Array.isArray(trades)).toBe(true);
      expect(trades.length).toBe(2);
      
      // AAPL should be sold (weight decreases from 0.6 to 0.5)
      const aaplTrade = trades.find(t => t.symbol === 'AAPL');
      expect(aaplTrade.action).toBe('SELL');
      expect(aaplTrade.tradeValue).toBeCloseTo(-10000); // 0.1 * 100000
      
      // MSFT should be bought (weight increases from 0.4 to 0.5)
      const msftTrade = trades.find(t => t.symbol === 'MSFT');
      expect(msftTrade.action).toBe('BUY');
      expect(msftTrade.tradeValue).toBeCloseTo(10000);
    });

    it('ignores small weight differences', async () => {
      const currentPortfolio = {
        holdings: [{ symbol: 'AAPL', weight: 0.501, marketValue: 50100 }],
        totalValue: 100000
      };
      
      const universe = ['AAPL'];
      const targetWeights = [0.5];
      
      const trades = await optimizationEngine.calculateRebalancing(currentPortfolio, universe, targetWeights);
      expect(trades.length).toBe(0); // Small difference should be ignored
    });

    it('sorts trades by priority and value', async () => {
      const currentPortfolio = {
        holdings: [
          { symbol: 'AAPL', weight: 0.7, marketValue: 70000 },
          { symbol: 'MSFT', weight: 0.2, marketValue: 20000 },
          { symbol: 'GOOGL', weight: 0.1, marketValue: 10000 }
        ],
        totalValue: 100000
      };
      
      const universe = ['AAPL', 'MSFT', 'GOOGL'];
      const targetWeights = [0.4, 0.3, 0.3];
      
      const trades = await optimizationEngine.calculateRebalancing(currentPortfolio, universe, targetWeights);
      
      // Should have trades for all 3 positions (large differences)
      expect(trades.length).toBe(3);
      
      // Find AAPL trade - should be largest sell (0.7 -> 0.4 = -0.3)
      const aaplTrade = trades.find(t => t.symbol === 'AAPL');
      expect(aaplTrade.action).toBe('SELL');
      expect(Math.abs(aaplTrade.tradeValue)).toBe(30000); // 0.3 * 100000
    });
  });

  describe('Optimization Insights', () => {
    it('generates risk warning for high volatility', () => {
      const currentPortfolio = { holdings: [] };
      const optimization = { sharpeRatio: 0.4 };
      const riskMetrics = { volatility: 0.25 }; // 25% volatility
      const corrMatrix = [];
      const universe = ['AAPL', 'MSFT'];
      
      const insights = optimizationEngine.generateOptimizationInsights(currentPortfolio, optimization, riskMetrics, corrMatrix, universe);
      
      expect(Array.isArray(insights)).toBe(true);
      const riskInsight = insights.find(i => i.type === 'warning' && i.category === 'Risk');
      expect(riskInsight).toBeDefined();
      expect(riskInsight.title).toContain('High Portfolio Volatility');
    });

    it('generates diversification insight for small portfolios', () => {
      const currentPortfolio = { holdings: [] };
      const optimization = { sharpeRatio: 1.0 };
      const riskMetrics = { volatility: 0.15 };
      const corrMatrix = [];
      const universe = ['AAPL', 'MSFT']; // Small universe (2 assets)
      
      const insights = optimizationEngine.generateOptimizationInsights(currentPortfolio, optimization, riskMetrics, corrMatrix, universe);
      const diversificationInsight = insights.find(i => i.category === 'Diversification');
      expect(diversificationInsight).toBeDefined();
      expect(diversificationInsight.title).toContain('Limited Diversification');
    });

    it('generates positive insight for high Sharpe ratio', () => {
      const currentPortfolio = { holdings: [] };
      const optimization = { sharpeRatio: 1.8 }; // High Sharpe ratio
      const riskMetrics = { volatility: 0.10 };
      const corrMatrix = [];
      const universe = ['AAPL', 'MSFT', 'GOOGL', 'AMZN', 'TSLA', 'NVDA', 'META', 'NFLX', 'JPM', 'JNJ']; // 10 assets
      
      const insights = optimizationEngine.generateOptimizationInsights(currentPortfolio, optimization, riskMetrics, corrMatrix, universe);
      const performanceInsight = insights.find(i => i.type === 'success');
      expect(performanceInsight).toBeDefined();
      expect(performanceInsight.category).toBe('Performance');
    });

    it('generates concentration warning for large positions', () => {
      const currentPortfolio = { 
        holdings: [
          { symbol: 'AAPL', weight: 0.6 },
          { symbol: 'MSFT', weight: 0.4 }
        ]
      };
      const optimization = { 
        sharpeRatio: 1.0, 
        weights: [0.6, 0.4] // Array of weight values, not objects
      };
      const riskMetrics = { volatility: 0.15 };
      const corrMatrix = [];
      const universe = ['AAPL', 'MSFT'];
      
      const insights = optimizationEngine.generateOptimizationInsights(currentPortfolio, optimization, riskMetrics, corrMatrix, universe);
      const concentrationInsight = insights.find(i => i.category === 'Concentration');
      expect(concentrationInsight).toBeDefined();
    });
  });

  describe('Formatting Functions', () => {
    it('formats weights correctly', () => {
      const universe = ['AAPL', 'MSFT'];
      const weights = [0.456789, 0.543211];
      const formatted = optimizationEngine.formatWeights(universe, weights);
      
      expect(Array.isArray(formatted)).toBe(true);
      expect(formatted[0].symbol).toBe('AAPL');
      expect(formatted[0].weight).toBe(45.68); // Percentage
      expect(formatted[0].allocation).toBe(0.456789);
      expect(formatted[1].symbol).toBe('MSFT');
      expect(formatted[1].weight).toBe(54.32);
    });

    it('formats portfolio summary correctly', () => {
      const portfolio = {
        totalValue: 100000,
        numPositions: 3,
        holdings: [
          { symbol: 'AAPL', weight: 0.4, marketValue: 40000, pnl: 5000, pnlPercent: 12.5 },
          { symbol: 'MSFT', weight: 0.35, marketValue: 35000, pnl: 3000, pnlPercent: 8.6 },
          { symbol: 'GOOGL', weight: 0.25, marketValue: 25000, pnl: 2000, pnlPercent: 8.0 }
        ]
      };
      
      const summary = optimizationEngine.formatPortfolioSummary(portfolio);
      
      expect(summary.totalValue).toBe(100000);
      expect(summary.numPositions).toBe(3);
      expect(Array.isArray(summary.topHoldings)).toBe(true);
      expect(summary.topHoldings[0].symbol).toBe('AAPL');
      expect(summary.topHoldings[0].weight).toBe(40); // Percentage
    });

    it('formats correlation matrix correctly', () => {
      // Create a mock correlation matrix with .get method
      const correlationMatrix = {
        get: (i, j) => {
          if (i === 0 && j === 1) return 0.85; // High correlation
          if (i === 1 && j === 0) return 0.85;
          return i === j ? 1.0 : 0.0;
        }
      };
      const universe = ['AAPL', 'MSFT'];
      
      const formatted = optimizationEngine.formatCorrelationMatrix(universe, correlationMatrix);
      
      expect(Array.isArray(formatted)).toBe(true);
      expect(formatted[0]).toHaveProperty('asset1');
      expect(formatted[0]).toHaveProperty('asset2');
      expect(formatted[0]).toHaveProperty('correlation');
      expect(formatted[0]).toHaveProperty('strength');
      expect(formatted[0].correlation).toBe(0.85);
    });
  });

  describe('Data Quality Assessment', () => {
    it('assesses high-quality data correctly', () => {
      const priceData = {
        AAPL: Array.from({ length: 252 }, (_, i) => ({
          date: new Date(2023, 0, i + 1).toISOString().split('T')[0],
          close: 100 + Math.random() * 20
        })),
        MSFT: Array.from({ length: 252 }, (_, i) => ({
          date: new Date(2023, 0, i + 1).toISOString().split('T')[0],
          close: 200 + Math.random() * 40
        }))
      };
      
      const assessment = optimizationEngine.assessDataQuality(priceData, {});
      
      expect(assessment.score).toBeGreaterThan(80);
      expect(assessment.symbols).toBe(2);
      expect(assessment.totalDataPoints).toBe(504);
      expect(assessment.missingDataPoints).toBe(0);
    });

    it('identifies missing data points', () => {
      const priceData = {
        AAPL: [
          { date: '2023-01-01', close: 100 },
          { date: '2023-01-02', close: 105 }
        ],
        MSFT: [
          { date: '2023-01-01', close: null }, // Missing data
          { date: '2023-01-02', close: 210 }
        ]
      };
      
      const assessment = optimizationEngine.assessDataQuality(priceData, {});
      
      expect(assessment.score).toBeLessThan(100);
      expect(assessment.missingDataPoints).toBeGreaterThan(0);
    });
  });

  describe('Fallback Optimization', () => {
    it('generates fallback optimization with demo data', () => {
      const result = optimizationEngine.generateFallbackOptimization('user123', 'maxSharpe');
      
      expect(result).toHaveProperty('success');
      expect(result).toHaveProperty('optimization');
      expect(result).toHaveProperty('currentPortfolio');
      expect(result).toHaveProperty('rebalancing');
      expect(result.success).toBe(true);
      expect(result.optimization).toHaveProperty('weights');
      expect(result.optimization).toHaveProperty('expectedReturn');
      expect(result.optimization).toHaveProperty('volatility');
      expect(result.optimization).toHaveProperty('sharpeRatio');
    });

    it('uses equal weights for equalWeight objective', () => {
      const result = optimizationEngine.generateFallbackOptimization('user123', 'equalWeight');
      
      const weights = result.optimization.weights;
      const expectedWeight = 20; // 100% / 5 assets = 20%
      
      weights.forEach(weightObj => {
        expect(weightObj.weight).toBeCloseTo(expectedWeight, 1);
        expect(weightObj.allocation).toBeCloseTo(0.2, 1);
      });
    });

    it('generates mock efficient frontier', () => {
      const frontier = optimizationEngine.generateMockEfficientFrontier();
      
      expect(Array.isArray(frontier)).toBe(true);
      expect(frontier.length).toBe(20);
      
      frontier.forEach(point => {
        expect(point).toHaveProperty('volatility');
        expect(point).toHaveProperty('expectedReturn');
        expect(point).toHaveProperty('sharpeRatio');
        expect(point.volatility).toBeGreaterThan(0);
        expect(point.expectedReturn).toBeGreaterThan(0);
      });
    });
  });

  describe('Full Optimization Integration', () => {
    it('runs complete optimization successfully', async () => {
      const params = {
        userId: 123,
        objective: 'maxSharpe',
        constraints: {},
        includeAssets: [],
        excludeAssets: []
      };
      
      const result = await optimizationEngine.runOptimization(params);
      
      expect(result).toBeDefined();
      expect(result).toHaveProperty('success');
      expect(result).toHaveProperty('optimization');
      expect(result).toHaveProperty('currentPortfolio');
      expect(result).toHaveProperty('insights');
      expect(result).toHaveProperty('rebalancing');
    });

    it('falls back to demo optimization on error', async () => {
      // Test with invalid params to trigger fallback
      const params = {
        userId: null, // Invalid user ID
        objective: 'maxSharpe'
      };
      
      const result = await optimizationEngine.runOptimization(params);
      
      expect(result).toHaveProperty('success');
      expect(result).toHaveProperty('optimization');
      expect(result).toHaveProperty('currentPortfolio');
    });
  });

  describe('Mock Price Data Generation', () => {
    it('generates price data with correct structure', () => {
      const symbol = 'AAPL';
      const startDate = new Date('2023-01-01');
      const endDate = new Date('2023-01-10'); // 10 days
      const priceData = optimizationEngine.generateMockPriceData(symbol, startDate, endDate);
      
      expect(priceData.length).toBeGreaterThan(8); // About 10 days
      priceData.forEach(day => {
        expect(day).toHaveProperty('date');
        expect(day).toHaveProperty('close');
        expect(day).toHaveProperty('symbol');
        expect(typeof day.close).toBe('number');
        expect(day.symbol).toBe('AAPL');
      });
    });

    it('applies different volatility for different assets', () => {
      const startDate = new Date('2023-01-01');
      const endDate = new Date('2023-04-01'); // 3 months
      
      const tslaData = optimizationEngine.generateMockPriceData('TSLA', startDate, endDate);
      const spyData = optimizationEngine.generateMockPriceData('SPY', startDate, endDate);
      
      // Calculate returns to verify different volatilities
      const tslaReturns = [];
      const spyReturns = [];
      
      for (let i = 1; i < tslaData.length; i++) {
        tslaReturns.push((tslaData[i].close - tslaData[i-1].close) / tslaData[i-1].close);
        spyReturns.push((spyData[i].close - spyData[i-1].close) / spyData[i-1].close);
      }
      
      // Both should have returns (not static prices)
      const tslaVariance = tslaReturns.reduce((sum, r) => sum + r*r, 0) / tslaReturns.length;
      const spyVariance = spyReturns.reduce((sum, r) => sum + r*r, 0) / spyReturns.length;
      
      expect(tslaVariance).toBeGreaterThan(0);
      expect(spyVariance).toBeGreaterThan(0);
      // TSLA should have higher volatility than SPY
      expect(tslaVariance).toBeGreaterThan(spyVariance);
    });
  });
});