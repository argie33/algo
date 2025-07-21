/**
 * REAL Optimization Engine Unit Tests
 * Tests actual business logic, not mocked bullshit
 */

const OptimizationEngine = require('../../services/optimizationEngine');
const PortfolioMath = require('../../utils/portfolioMath');

// Test with REAL PortfolioMath - no mocks!
describe('OptimizationEngine REAL Tests', () => {
  let optimizationEngine;

  beforeEach(() => {
    optimizationEngine = new OptimizationEngine();
  });

  describe('Real Portfolio Math Integration', () => {
    test('generates realistic mock price data with proper format', () => {
      const startDate = new Date('2023-01-01');
      const endDate = new Date('2023-01-10');
      
      const priceData = optimizationEngine.generateMockPriceData('AAPL', startDate, endDate);
      
      // Test real price data structure
      expect(Array.isArray(priceData)).toBe(true);
      expect(priceData.length).toBeGreaterThan(5);
      
      // Test each price point has real structure
      priceData.forEach(point => {
        expect(point).toHaveProperty('date');
        expect(point).toHaveProperty('close');
        expect(point).toHaveProperty('symbol');
        expect(typeof point.close).toBe('number');
        expect(point.close).toBeGreaterThan(0);
        expect(point.symbol).toBe('AAPL');
      });
      
      // Verify prices change (not static)
      const prices = priceData.map(p => p.close);
      const uniquePrices = [...new Set(prices)];
      expect(uniquePrices.length).toBeGreaterThan(1); // Prices should vary
    });

    test('calculates returns matrix from real price data', () => {
      const startDate = new Date('2023-01-01');
      const endDate = new Date('2023-01-10');
      
      const priceData = {
        'AAPL': optimizationEngine.generateMockPriceData('AAPL', startDate, endDate),
        'MSFT': optimizationEngine.generateMockPriceData('MSFT', startDate, endDate)
      };
      
      const returnsData = optimizationEngine.calculateReturnsMatrix(priceData);
      
      // Test real returns calculation
      expect(returnsData).toHaveProperty('returns');
      expect(returnsData).toHaveProperty('dates');
      expect(returnsData).toHaveProperty('symbols');
      
      expect(Array.isArray(returnsData.returns)).toBe(true);
      expect(returnsData.returns.length).toBeGreaterThan(0);
      expect(returnsData.symbols).toEqual(['AAPL', 'MSFT']);
      
      // Each return period should have returns for both assets
      returnsData.returns.forEach(dayReturns => {
        expect(dayReturns).toHaveLength(2); // AAPL and MSFT
        dayReturns.forEach(ret => {
          expect(typeof ret).toBe('number');
          expect(ret).toBeGreaterThan(-1); // Return > -100%
          expect(ret).toBeLessThan(1); // Return < 100% (reasonable daily change)
        });
      });
    });

    test('REAL covariance matrix calculation with actual data', () => {
      // Generate real price data
      const startDate = new Date('2023-01-01');
      const endDate = new Date('2023-03-01'); // 60 days of data
      
      const priceData = {
        'AAPL': optimizationEngine.generateMockPriceData('AAPL', startDate, endDate),
        'MSFT': optimizationEngine.generateMockPriceData('MSFT', startDate, endDate),
        'GOOGL': optimizationEngine.generateMockPriceData('GOOGL', startDate, endDate)
      };
      
      const returnsData = optimizationEngine.calculateReturnsMatrix(priceData);
      
      // Test REAL PortfolioMath.calculateCovarianceMatrix (no mocking!)
      const covMatrix = PortfolioMath.calculateCovarianceMatrix(returnsData.returns);
      
      // Verify real covariance matrix properties
      expect(covMatrix).toBeDefined();
      expect(covMatrix.rows).toBe(3);
      expect(covMatrix.columns).toBe(3);
      
      // Diagonal elements should be positive (variance)
      expect(covMatrix.get(0, 0)).toBeGreaterThan(0);
      expect(covMatrix.get(1, 1)).toBeGreaterThan(0);
      expect(covMatrix.get(2, 2)).toBeGreaterThan(0);
      
      // Matrix should be symmetric
      expect(covMatrix.get(0, 1)).toBeCloseTo(covMatrix.get(1, 0), 10);
      expect(covMatrix.get(0, 2)).toBeCloseTo(covMatrix.get(2, 0), 10);
      expect(covMatrix.get(1, 2)).toBeCloseTo(covMatrix.get(2, 1), 10);
    });
  });

  describe('Real Rebalancing Calculations', () => {
    test('calculates real rebalancing with actual portfolio data', async () => {
      const currentPortfolio = {
        holdings: [
          { symbol: 'AAPL', weight: 0.4, marketValue: 40000 },
          { symbol: 'MSFT', weight: 0.3, marketValue: 30000 },
          { symbol: 'GOOGL', weight: 0.3, marketValue: 30000 }
        ],
        totalValue: 100000
      };
      
      const universe = ['AAPL', 'MSFT', 'GOOGL'];
      const targetWeights = [0.33, 0.33, 0.34]; // More balanced allocation
      
      const rebalancing = await optimizationEngine.calculateRebalancing(
        currentPortfolio, 
        universe, 
        targetWeights
      );
      
      // Test real rebalancing calculations
      expect(Array.isArray(rebalancing)).toBe(true);
      
      rebalancing.forEach(trade => {
        expect(trade).toHaveProperty('symbol');
        expect(trade).toHaveProperty('currentWeight');
        expect(trade).toHaveProperty('targetWeight');
        expect(trade).toHaveProperty('tradeValue');
        expect(trade).toHaveProperty('action');
        expect(['BUY', 'SELL']).toContain(trade.action);
        
        // Verify math: trade value should make sense
        const expectedTradeValue = (trade.targetWeight / 100) * 100000 - trade.currentValue;
        expect(Math.abs(trade.tradeValue - expectedTradeValue)).toBeLessThan(100); // Within $100 rounding
      });
    });
  });

  describe('Real Portfolio Insights Generation', () => {
    test('generates real insights from actual optimization data', () => {
      const currentPortfolio = {
        holdings: [{ symbol: 'AAPL', weight: 0.8 }], // High concentration
        totalValue: 100000
      };
      
      const optimization = {
        weights: [0.8, 0.2], // Still concentrated
        sharpeRatio: 0.5 // Low Sharpe ratio
      };
      
      const riskMetrics = {
        volatility: 0.25 // High volatility
      };
      
      const corrMatrix = { get: () => 0.1 }; // Low correlation
      const universe = ['AAPL', 'MSFT'];
      
      const insights = optimizationEngine.generateOptimizationInsights(
        currentPortfolio,
        optimization,
        riskMetrics,
        corrMatrix,
        universe
      );
      
      // Test real insight generation logic
      expect(Array.isArray(insights)).toBe(true);
      expect(insights.length).toBeGreaterThan(0);
      
      // Should detect high volatility
      const volatilityWarning = insights.find(i => i.category === 'Risk');
      expect(volatilityWarning).toBeDefined();
      expect(volatilityWarning.type).toBe('warning');
      
      // Should detect low Sharpe ratio
      const performanceWarning = insights.find(i => i.category === 'Performance');
      expect(performanceWarning).toBeDefined();
      
      // Should detect concentration risk
      const concentrationWarning = insights.find(i => i.category === 'Concentration');
      expect(concentrationWarning).toBeDefined();
    });
  });

  describe('Real Demo Portfolio Logic', () => {
    test('demo portfolio has realistic financial data structure', () => {
      const portfolio = optimizationEngine.getDemoPortfolio();
      
      // Test real portfolio structure
      expect(portfolio).toHaveProperty('holdings');
      expect(portfolio).toHaveProperty('totalValue');
      expect(portfolio).toHaveProperty('numPositions');
      
      expect(Array.isArray(portfolio.holdings)).toBe(true);
      expect(portfolio.holdings.length).toBeGreaterThan(0);
      
      let calculatedTotal = 0;
      portfolio.holdings.forEach(holding => {
        expect(holding).toHaveProperty('symbol');
        expect(holding).toHaveProperty('marketValue');
        expect(holding).toHaveProperty('weight');
        expect(holding).toHaveProperty('pnl');
        
        // Verify real financial calculations
        expect(typeof holding.marketValue).toBe('number');
        expect(holding.marketValue).toBeGreaterThan(0);
        calculatedTotal += holding.marketValue;
      });
      
      // Verify total value calculation is correct
      expect(calculatedTotal).toBe(portfolio.totalValue);
      
      // Verify weights sum to 1 (or close to it)
      const totalWeight = portfolio.holdings.reduce((sum, h) => sum + h.weight, 0);
      expect(totalWeight).toBeCloseTo(1.0, 2);
    });
  });

  describe('Real Data Quality Assessment', () => {
    test('assesses actual price data quality correctly', () => {
      const startDate = new Date('2023-01-01');
      const endDate = new Date('2023-01-30');
      
      const priceData = {
        'AAPL': optimizationEngine.generateMockPriceData('AAPL', startDate, endDate),
        'MSFT': optimizationEngine.generateMockPriceData('MSFT', startDate, endDate)
      };
      
      const returnsData = optimizationEngine.calculateReturnsMatrix(priceData);
      const quality = optimizationEngine.assessDataQuality(priceData, returnsData);
      
      // Test real data quality logic
      expect(quality).toHaveProperty('score');
      expect(quality).toHaveProperty('assessment');
      expect(quality).toHaveProperty('totalDataPoints');
      expect(quality).toHaveProperty('symbols');
      
      expect(quality.score).toBeGreaterThan(90); // Should be high quality mock data
      expect(['Excellent', 'Good', 'Fair', 'Poor']).toContain(quality.assessment);
      expect(quality.symbols).toBe(2);
      expect(quality.totalDataPoints).toBeGreaterThan(40); // ~30 days * 2 symbols
    });
  });

  describe('Real Error Handling', () => {
    test('handles missing portfolio data gracefully with real fallback', async () => {
      // This will test the real fallback logic when database fails
      const mockQuery = require('../../utils/database').query;
      
      // Temporarily replace with failing query to test real error handling
      const originalQuery = mockQuery;
      const failingQuery = () => Promise.reject(new Error('Database connection failed'));
      require('../../utils/database').query = failingQuery;
      
      try {
        const portfolio = await optimizationEngine.getCurrentPortfolio(999);
        
        // Should fallback to demo portfolio (real logic)
        expect(portfolio).toBeDefined();
        expect(portfolio.holdings).toBeDefined();
        expect(portfolio.totalValue).toBeGreaterThan(0);
        
        // Verify it's the demo portfolio structure
        expect(portfolio.holdings[0].symbol).toBe('AAPL');
      } finally {
        // Restore original query
        require('../../utils/database').query = originalQuery;
      }
    });
  });
});