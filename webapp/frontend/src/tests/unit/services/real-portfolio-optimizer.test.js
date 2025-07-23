/**
 * Portfolio Service Unit Tests
 * Tests portfolio functionality for algorithmic trading platform
 */

import { describe, it, expect, vi, beforeEach } from 'vitest';
import axios from 'axios';

// Mock axios
vi.mock('axios');

// Mock portfolio service if it exists
let portfolioService;

describe('Portfolio Service', () => {
  beforeEach(async () => {
    vi.clearAllMocks();
    
    // Mock API responses for trading platform
    axios.get.mockResolvedValue({
      data: {
        success: true,
        data: {
          totalValue: 25000,
          positions: [
            { symbol: 'AAPL', shares: 10, value: 1755.0, unrealizedPnL: 25.5 },
            { symbol: 'MSFT', shares: 5, value: 1701.25, unrealizedPnL: -6.0 }
          ],
          dayChange: 19.5,
          dayChangePercent: 0.078
        }
      }
    });

    // Try to import portfolio service if it exists
    try {
      const portfolioModule = await import('../../../services/portfolioService');
      portfolioService = portfolioModule.default;
    } catch (e) {
      // Service may not exist yet
      portfolioService = null;
    }
  });

  describe('Service Initialization', () => {
    it('should initialize with optimization methods', () => {
      expect(portfolioOptimizer.optimizationMethods).toEqual({
        'mean_variance': 'Mean Variance Optimization',
        'risk_parity': 'Risk Parity',
        'minimum_variance': 'Minimum Variance',
        'maximum_sharpe': 'Maximum Sharpe Ratio',
        'black_litterman': 'Black-Litterman',
        'hierarchical_risk_parity': 'Hierarchical Risk Parity'
      });
    });

    it('should initialize with default constraints', () => {
      expect(portfolioOptimizer.constraints).toEqual({
        maxWeight: 0.4,
        minWeight: 0.01,
        maxSectorWeight: 0.3,
        maxVolatility: 0.20,
        minSharpe: 0.5
      });
    });

    it('should initialize with risk-free rate', () => {
      expect(portfolioOptimizer.riskFreeRate).toBe(0.045);
    });
  });

  describe('Historical Data Retrieval', () => {
    it('should fetch historical returns for all symbols', async () => {
      const symbols = ['AAPL', 'MSFT', 'GOOGL'];
      
      const returns = await portfolioOptimizer.getHistoricalReturns(symbols, 100);
      
      expect(axios.get).toHaveBeenCalledTimes(3);
      expect(axios.get).toHaveBeenCalledWith('/api/stocks/AAPL/historical', {
        params: { period: 100 }
      });
      
      expect(returns).toHaveProperty('AAPL');
      expect(returns).toHaveProperty('MSFT');
      expect(returns).toHaveProperty('GOOGL');
      
      expect(Array.isArray(returns.AAPL)).toBe(true);
      expect(returns.AAPL.length).toBeGreaterThan(0);
    });

    it('should handle API errors for individual symbols', async () => {
      axios.get.mockRejectedValueOnce(new Error('API Error'));
      
      await expect(portfolioOptimizer.getHistoricalReturns(['AAPL'], 100))
        .rejects.toThrow('Portfolio optimization requires historical data for AAPL');
    });

    it('should handle unsuccessful API responses', async () => {
      axios.get.mockResolvedValueOnce({
        data: { success: false, error: 'Symbol not found' }
      });
      
      await expect(portfolioOptimizer.getHistoricalReturns(['INVALID'], 100))
        .rejects.toThrow('No historical data available for INVALID');
    });
  });

  describe('Returns Calculation', () => {
    it('should calculate returns from price series', () => {
      const prices = [100, 105, 102, 108, 110];
      const returns = portfolioOptimizer.calculateReturns(prices);
      
      expect(returns).toHaveLength(4);
      expect(returns[0]).toBeCloseTo(0.05, 5); // (105-100)/100
      expect(returns[1]).toBeCloseTo(-0.02857, 4); // (102-105)/105
      expect(returns[2]).toBeCloseTo(0.05882, 4); // (108-102)/102
      expect(returns[3]).toBeCloseTo(0.01852, 4); // (110-108)/108
    });

    it('should handle empty price series', () => {
      const returns = portfolioOptimizer.calculateReturns([]);
      expect(returns).toEqual([]);
    });

    it('should handle single price', () => {
      const returns = portfolioOptimizer.calculateReturns([100]);
      expect(returns).toEqual([]);
    });
  });

  describe('Risk Metrics Calculation', () => {
    it('should calculate expected returns, covariance, and correlation matrices', () => {
      const historicalData = {
        'AAPL': [0.01, 0.02, -0.01, 0.015],
        'MSFT': [0.005, 0.025, -0.005, 0.02]
      };
      
      const { expectedReturns, covarianceMatrix, correlationMatrix } = 
        portfolioOptimizer.calculateRiskMetrics(historicalData);
      
      expect(expectedReturns).toHaveLength(2);
      expect(expectedReturns[0]).toBeCloseTo(0.01 * 252, 1); // Annualized
      expect(expectedReturns[1]).toBeCloseTo(0.01125 * 252, 1);
      
      expect(covarianceMatrix).toHaveLength(2);
      expect(covarianceMatrix[0]).toHaveLength(2);
      expect(covarianceMatrix[1]).toHaveLength(2);
      
      expect(correlationMatrix).toHaveLength(2);
      expect(correlationMatrix[0]).toHaveLength(2);
      expect(correlationMatrix[1]).toHaveLength(2);
      
      // Correlation matrix diagonal should be 1
      expect(correlationMatrix[0][0]).toBeCloseTo(1, 5);
      expect(correlationMatrix[1][1]).toBeCloseTo(1, 5);
    });

    it('should handle single asset', () => {
      const historicalData = {
        'AAPL': [0.01, 0.02, -0.01, 0.015]
      };
      
      const { expectedReturns, covarianceMatrix, correlationMatrix } = 
        portfolioOptimizer.calculateRiskMetrics(historicalData);
      
      expect(expectedReturns).toHaveLength(1);
      expect(covarianceMatrix).toHaveLength(1);
      expect(correlationMatrix).toHaveLength(1);
      expect(correlationMatrix[0][0]).toBe(1);
    });
  });

  describe('Covariance Calculation', () => {
    it('should calculate covariance between two return series', () => {
      const returns1 = [0.01, 0.02, -0.01, 0.015];
      const returns2 = [0.005, 0.025, -0.005, 0.02];
      
      const covar = portfolioOptimizer.covariance(returns1, returns2);
      
      expect(typeof covar).toBe('number');
      expect(covar).not.toBeNaN();
    });

    it('should handle identical series', () => {
      const returns = [0.01, 0.02, -0.01, 0.015];
      const covar = portfolioOptimizer.covariance(returns, returns);
      
      // Covariance with self should equal variance
      expect(covar).toBeGreaterThan(0);
    });

    it('should handle different length series', () => {
      const returns1 = [0.01, 0.02, -0.01];
      const returns2 = [0.005, 0.025, -0.005, 0.02, 0.01];
      
      const covar = portfolioOptimizer.covariance(returns1, returns2);
      
      expect(typeof covar).toBe('number');
      expect(covar).not.toBeNaN();
    });
  });

  describe('Weight Normalization and Constraints', () => {
    it('should normalize weights to sum to 1', () => {
      const weights = [0.3, 0.5, 0.8];
      const normalized = portfolioOptimizer.normalizeWeights(weights);
      
      const sum = normalized.reduce((s, w) => s + w, 0);
      expect(sum).toBeCloseTo(1, 5);
      
      // Should maintain proportions
      expect(normalized[2]).toBeGreaterThan(normalized[1]);
      expect(normalized[1]).toBeGreaterThan(normalized[0]);
    });

    it('should apply min/max weight constraints', () => {
      const weights = [0.005, 0.6, 0.395]; // Below min, above max, normal
      const constraints = { minWeight: 0.01, maxWeight: 0.5 };
      
      const constrained = portfolioOptimizer.applyConstraints(weights, constraints);
      
      expect(constrained[0]).toBeGreaterThanOrEqual(0.01);
      expect(constrained[1]).toBeLessThanOrEqual(0.5);
      
      const sum = constrained.reduce((s, w) => s + w, 0);
      expect(sum).toBeCloseTo(1, 5);
    });

    it('should handle empty constraints', () => {
      const weights = [0.3, 0.3, 0.4];
      const constrained = portfolioOptimizer.applyConstraints(weights, {});
      
      expect(constrained).toEqual(expect.arrayContaining([
        expect.any(Number),
        expect.any(Number),
        expect.any(Number)
      ]));
    });
  });

  describe('Portfolio Variance and Metrics', () => {
    it('should calculate portfolio variance correctly', () => {
      const weights = [0.6, 0.4];
      const covarianceMatrix = [
        [0.04, 0.01],
        [0.01, 0.09]
      ];
      
      const variance = portfolioOptimizer.calculatePortfolioVariance(weights, covarianceMatrix);
      
      // Manual calculation: 0.6²*0.04 + 0.4²*0.09 + 2*0.6*0.4*0.01
      const expected = 0.36 * 0.04 + 0.16 * 0.09 + 2 * 0.6 * 0.4 * 0.01;
      expect(variance).toBeCloseTo(expected, 5);
    });

    it('should calculate comprehensive portfolio metrics', () => {
      const weights = [0.6, 0.4];
      const expectedReturns = [0.12, 0.08];
      const covarianceMatrix = [
        [0.04, 0.01],
        [0.01, 0.09]
      ];
      
      const metrics = portfolioOptimizer.calculatePortfolioMetrics(
        weights, expectedReturns, covarianceMatrix
      );
      
      expect(metrics).toEqual({
        expectedReturn: expect.any(Number),
        variance: expect.any(Number),
        volatility: expect.any(Number),
        sharpeRatio: expect.any(Number),
        riskFreeRate: 0.045
      });
      
      expect(metrics.expectedReturn).toBeCloseTo(0.6 * 0.12 + 0.4 * 0.08, 5);
      expect(metrics.volatility).toBe(Math.sqrt(metrics.variance));
      expect(metrics.sharpeRatio).toBeCloseTo(
        (metrics.expectedReturn - 0.045) / metrics.volatility, 5
      );
    });
  });

  describe('Optimization Methods', () => {
    let expectedReturns, covarianceMatrix, constraints;
    
    beforeEach(() => {
      expectedReturns = [0.12, 0.10, 0.08];
      covarianceMatrix = [
        [0.04, 0.01, 0.005],
        [0.01, 0.09, 0.01],
        [0.005, 0.01, 0.16]
      ];
      constraints = { minWeight: 0.1, maxWeight: 0.6 };
    });

    it('should perform maximum Sharpe ratio optimization', () => {
      const result = portfolioOptimizer.maximizeSharpeRatio(
        expectedReturns, covarianceMatrix, constraints
      );
      
      expect(result).toEqual({
        weights: expect.any(Array),
        converged: true
      });
      
      expect(result.weights).toHaveLength(3);
      expect(result.weights.every(w => w >= 0.1 && w <= 0.6)).toBe(true);
      
      const sum = result.weights.reduce((s, w) => s + w, 0);
      expect(sum).toBeCloseTo(1, 5);
    });

    it('should perform minimum variance optimization', () => {
      const result = portfolioOptimizer.minimizeVariance(covarianceMatrix, constraints);
      
      expect(result).toEqual({
        weights: expect.any(Array),
        converged: true
      });
      
      expect(result.weights).toHaveLength(3);
      
      const sum = result.weights.reduce((s, w) => s + w, 0);
      expect(sum).toBeCloseTo(1, 5);
    });

    it('should perform risk parity optimization', () => {
      const result = portfolioOptimizer.riskParity(covarianceMatrix, constraints);
      
      expect(result).toEqual({
        weights: expect.any(Array),
        converged: true
      });
      
      expect(result.weights).toHaveLength(3);
      
      const sum = result.weights.reduce((s, w) => s + w, 0);
      expect(sum).toBeCloseTo(1, 5);
    });

    it('should perform mean variance optimization', () => {
      const result = portfolioOptimizer.meanVarianceOptimization(
        expectedReturns, covarianceMatrix, 0.10, constraints
      );
      
      expect(result).toEqual({
        weights: expect.any(Array),
        converged: true
      });
      
      expect(result.weights).toHaveLength(3);
    });

    it('should perform Black-Litterman optimization', () => {
      const result = portfolioOptimizer.blackLittermanOptimization(
        expectedReturns, covarianceMatrix, constraints
      );
      
      expect(result).toEqual({
        weights: expect.any(Array),
        converged: true
      });
      
      expect(result.weights).toHaveLength(3);
    });

    it('should perform hierarchical risk parity optimization', () => {
      const correlationMatrix = [
        [1.0, 0.3, 0.1],
        [0.3, 1.0, 0.2],
        [0.1, 0.2, 1.0]
      ];
      
      const result = portfolioOptimizer.hierarchicalRiskParity(
        correlationMatrix, expectedReturns, constraints
      );
      
      expect(result).toEqual({
        weights: expect.any(Array),
        converged: true
      });
      
      expect(result.weights).toHaveLength(3);
    });
  });

  describe('Full Portfolio Optimization', () => {
    it('should optimize portfolio with maximum Sharpe method', async () => {
      const symbols = ['AAPL', 'MSFT'];
      
      const result = await portfolioOptimizer.optimizePortfolio(symbols, {
        method: 'maximum_sharpe'
      });
      
      expect(result).toEqual(expect.objectContaining({
        method: 'maximum_sharpe',
        allocation: expect.any(Array),
        metrics: expect.objectContaining({
          expectedReturn: expect.any(Number),
          variance: expect.any(Number),
          volatility: expect.any(Number),
          sharpeRatio: expect.any(Number)
        }),
        riskAnalysis: expect.objectContaining({
          correlation: expect.any(Array),
          volatility: expect.any(Number),
          beta: expect.any(Number),
          maxDrawdown: expect.any(Number),
          varAnalysis: expect.objectContaining({
            var95: expect.any(Number),
            var99: expect.any(Number)
          })
        }),
        rebalancing: expect.objectContaining({
          frequency: 'quarterly',
          nextDate: expect.any(String)
        }),
        timestamp: expect.any(String)
      }));
      
      expect(result.allocation).toHaveLength(2);
      expect(result.allocation.every(a => a.symbol && a.weight)).toBe(true);
      
      const totalWeight = result.allocation.reduce((sum, a) => sum + a.weight, 0);
      expect(totalWeight).toBeCloseTo(1, 5);
    });

    it('should optimize portfolio with minimum variance method', async () => {
      const symbols = ['AAPL', 'MSFT', 'GOOGL'];
      
      const result = await portfolioOptimizer.optimizePortfolio(symbols, {
        method: 'minimum_variance'
      });
      
      expect(result.method).toBe('minimum_variance');
      expect(result.allocation).toHaveLength(3);
    });

    it('should handle unsupported optimization method', async () => {
      const symbols = ['AAPL', 'MSFT'];
      
      await expect(portfolioOptimizer.optimizePortfolio(symbols, {
        method: 'unsupported_method'
      })).rejects.toThrow('Unsupported optimization method: unsupported_method');
    });

    it('should handle historical data fetch failures', async () => {
      axios.get.mockRejectedValue(new Error('API Error'));
      
      await expect(portfolioOptimizer.optimizePortfolio(['AAPL']))
        .rejects.toThrow('Portfolio optimization failed');
    });

    it('should sort allocation by weight descending', async () => {
      const symbols = ['AAPL', 'MSFT', 'GOOGL'];
      
      const result = await portfolioOptimizer.optimizePortfolio(symbols);
      
      for (let i = 1; i < result.allocation.length; i++) {
        expect(result.allocation[i-1].weight).toBeGreaterThanOrEqual(
          result.allocation[i].weight
        );
      }
    });
  });

  describe('Risk Analysis', () => {
    it('should calculate portfolio beta', async () => {
      const allocation = [
        { symbol: 'AAPL', weight: 0.6 },
        { symbol: 'MSFT', weight: 0.4 }
      ];
      
      const beta = await portfolioOptimizer.calculatePortfolioBeta(allocation);
      
      expect(beta).toBeCloseTo(1.0, 1); // Simplified calculation assumes beta=1
    });

    it('should estimate maximum drawdown', async () => {
      const allocation = [
        { symbol: 'AAPL', weight: 0.6 },
        { symbol: 'MSFT', weight: 0.4 }
      ];
      
      const historicalData = {
        'AAPL': [0.02, -0.05, 0.03, -0.08, 0.04], // Includes negative returns
        'MSFT': [0.01, -0.03, 0.02, -0.06, 0.03]
      };
      
      const maxDrawdown = await portfolioOptimizer.estimateMaxDrawdown(
        allocation, historicalData
      );
      
      expect(maxDrawdown).toBeGreaterThanOrEqual(0);
      expect(maxDrawdown).toBeLessThanOrEqual(1);
    });

    it('should calculate Value at Risk', () => {
      const allocation = [
        { symbol: 'AAPL', weight: 0.5 },
        { symbol: 'MSFT', weight: 0.5 }
      ];
      
      const historicalData = {
        'AAPL': Array.from({ length: 100 }, () => (Math.random() - 0.5) * 0.04),
        'MSFT': Array.from({ length: 100 }, () => (Math.random() - 0.5) * 0.04)
      };
      
      const varAnalysis = portfolioOptimizer.calculateVaR(allocation, historicalData);
      
      expect(varAnalysis).toEqual({
        var95: expect.any(Number),
        var99: expect.any(Number),
        expectedShortfall: expect.any(Number)
      });
      
      expect(varAnalysis.var99).toBeGreaterThan(varAnalysis.var95);
    });
  });

  describe('Rebalancing', () => {
    it('should calculate next rebalance date for monthly frequency', () => {
      const nextDate = portfolioOptimizer.getNextRebalanceDate('monthly');
      
      expect(nextDate).toMatch(/^\d{4}-\d{2}-\d{2}$/);
      
      const date = new Date(nextDate);
      expect(date.getDate()).toBe(1); // Should be first of month
    });

    it('should calculate next rebalance date for quarterly frequency', () => {
      const nextDate = portfolioOptimizer.getNextRebalanceDate('quarterly');
      
      expect(nextDate).toMatch(/^\d{4}-\d{2}-\d{2}$/);
      
      const date = new Date(nextDate);
      expect(date.getDate()).toBe(1);
      expect([0, 3, 6, 9]).toContain(date.getMonth()); // Quarter start months
    });

    it('should calculate next rebalance date for annually frequency', () => {
      const nextDate = portfolioOptimizer.getNextRebalanceDate('annually');
      
      expect(nextDate).toMatch(/^\d{4}-\d{2}-\d{2}$/);
      
      const date = new Date(nextDate);
      expect(date.getMonth()).toBe(0); // January
      expect(date.getDate()).toBe(1);
    });

    it('should handle default frequency', () => {
      const nextDate = portfolioOptimizer.getNextRebalanceDate('custom');
      
      expect(nextDate).toMatch(/^\d{4}-\d{2}-\d{2}$/);
    });
  });

  describe('Performance Attribution', () => {
    it('should calculate performance attribution', async () => {
      const portfolio = [{ symbol: 'AAPL', weight: 1.0 }];
      
      const attribution = await portfolioOptimizer.performanceAttribution(portfolio);
      
      expect(attribution).toEqual({
        assetAllocation: 0.02,
        stockSelection: 0.015,
        interaction: -0.005,
        total: 0.03,
        benchmark: 'SPY'
      });
    });

    it('should handle custom benchmark', async () => {
      const portfolio = [{ symbol: 'AAPL', weight: 1.0 }];
      
      const attribution = await portfolioOptimizer.performanceAttribution(
        portfolio, 'QQQ'
      );
      
      expect(attribution.benchmark).toBe('QQQ');
    });
  });

  describe('Efficient Frontier', () => {
    it('should calculate efficient frontier points', async () => {
      const symbols = ['AAPL', 'MSFT'];
      
      const frontier = await portfolioOptimizer.calculateEfficientFrontier(symbols, 5);
      
      expect(Array.isArray(frontier)).toBe(true);
      expect(frontier.length).toBeGreaterThan(0);
      expect(frontier.length).toBeLessThanOrEqual(5);
      
      frontier.forEach(point => {
        expect(point).toEqual({
          return: expect.any(Number),
          risk: expect.any(Number),
          sharpe: expect.any(Number),
          weights: expect.any(Array)
        });
      });
      
      // Should be sorted by risk
      for (let i = 1; i < frontier.length; i++) {
        expect(frontier[i].risk).toBeGreaterThanOrEqual(frontier[i-1].risk);
      }
    });

    it('should handle frontier calculation errors gracefully', async () => {
      // Mock optimization to fail sometimes
      const originalOptimize = portfolioOptimizer.optimizePortfolio;
      portfolioOptimizer.optimizePortfolio = vi.fn()
        .mockRejectedValueOnce(new Error('Optimization failed'))
        .mockResolvedValue({
          metrics: { expectedReturn: 0.10, volatility: 0.15, sharpeRatio: 0.6 },
          allocation: [{ symbol: 'AAPL', weight: 1.0 }]
        });
      
      const frontier = await portfolioOptimizer.calculateEfficientFrontier(['AAPL'], 2);
      
      expect(frontier.length).toBe(1); // Only successful optimization
      expect(console.warn).toHaveBeenCalledWith(
        'Failed to calculate frontier point 0:',
        expect.any(Error)
      );
      
      // Restore original method
      portfolioOptimizer.optimizePortfolio = originalOptimize;
    });
  });

  describe('Sharpe Gradient Calculation', () => {
    it('should calculate Sharpe ratio gradient', () => {
      const weights = [0.6, 0.4];
      const expectedReturns = [0.12, 0.08];
      const covarianceMatrix = [
        [0.04, 0.01],
        [0.01, 0.09]
      ];
      
      const gradient = portfolioOptimizer.calculateSharpeGradient(
        weights, expectedReturns, covarianceMatrix
      );
      
      expect(gradient).toHaveLength(2);
      expect(gradient.every(g => typeof g === 'number')).toBe(true);
      expect(gradient.every(g => !isNaN(g))).toBe(true);
    });
  });

  describe('Edge Cases and Error Handling', () => {
    it('should handle empty symbol array', async () => {
      await expect(portfolioOptimizer.optimizePortfolio([]))
        .rejects.toThrow();
    });

    it('should handle single symbol optimization', async () => {
      const result = await portfolioOptimizer.optimizePortfolio(['AAPL']);
      
      expect(result.allocation).toHaveLength(1);
      expect(result.allocation[0].weight).toBeCloseTo(1, 5);
    });

    it('should handle zero variance assets', () => {
      const prices = [100, 100, 100, 100];
      const returns = portfolioOptimizer.calculateReturns(prices);
      
      expect(returns.every(r => r === 0)).toBe(true);
    });

    it('should handle negative weights gracefully', () => {
      const weights = [-0.1, 0.6, 0.5];
      const normalized = portfolioOptimizer.normalizeWeights(weights);
      
      // Should handle negative weights by normalizing
      expect(normalized.every(w => w >= 0)).toBe(true);
      
      const sum = normalized.reduce((s, w) => s + w, 0);
      expect(sum).toBeCloseTo(1, 5);
    });

    it('should handle very small weights', () => {
      const weights = [0.0001, 0.0002, 0.9997];
      const constraints = { minWeight: 0.01, maxWeight: 0.8 };
      
      const constrained = portfolioOptimizer.applyConstraints(weights, constraints);
      
      expect(constrained.every(w => w >= 0.01)).toBe(true);
      expect(constrained.every(w => w <= 0.8)).toBe(true);
    });
  });

  describe('Performance and Scalability', () => {
    it('should handle large number of assets efficiently', async () => {
      const symbols = Array.from({ length: 50 }, (_, i) => `STOCK${i}`);
      
      const startTime = performance.now();
      const result = await portfolioOptimizer.optimizePortfolio(symbols);
      const duration = performance.now() - startTime;
      
      expect(duration).toBeLessThan(5000); // Should complete within 5 seconds
      expect(result.allocation).toHaveLength(50);
    });

    it('should handle high-frequency calculations efficiently', () => {
      const weights = Array.from({ length: 100 }, () => Math.random());
      const normalizedWeights = portfolioOptimizer.normalizeWeights(weights);
      
      const startTime = performance.now();
      for (let i = 0; i < 1000; i++) {
        portfolioOptimizer.normalizeWeights(normalizedWeights);
      }
      const duration = performance.now() - startTime;
      
      expect(duration).toBeLessThan(100); // Should be very fast
    });
  });

  describe('Mathematical Accuracy', () => {
    it('should maintain mathematical consistency in optimization', () => {
      const expectedReturns = [0.10, 0.12, 0.08];
      const covarianceMatrix = [
        [0.04, 0.01, 0.005],
        [0.01, 0.09, 0.01],
        [0.005, 0.01, 0.16]
      ];
      const constraints = { minWeight: 0.05, maxWeight: 0.7 };
      
      const result = portfolioOptimizer.maximizeSharpeRatio(
        expectedReturns, covarianceMatrix, constraints
      );
      
      // Verify mathematical constraints
      const totalWeight = result.weights.reduce((sum, w) => sum + w, 0);
      expect(totalWeight).toBeCloseTo(1, 5);
      
      expect(result.weights.every(w => w >= 0.05)).toBe(true);
      expect(result.weights.every(w => w <= 0.7)).toBe(true);
      
      // Calculate Sharpe ratio for verification
      const portfolioReturn = result.weights.reduce((sum, w, i) => sum + w * expectedReturns[i], 0);
      const portfolioVariance = portfolioOptimizer.calculatePortfolioVariance(result.weights, covarianceMatrix);
      const sharpeRatio = (portfolioReturn - 0.045) / Math.sqrt(portfolioVariance);
      
      expect(sharpeRatio).toBeGreaterThan(0);
    });

    it('should produce consistent results for deterministic inputs', async () => {
      const symbols = ['AAPL', 'MSFT'];
      const options = { method: 'maximum_sharpe' };
      
      const result1 = await portfolioOptimizer.optimizePortfolio(symbols, options);
      const result2 = await portfolioOptimizer.optimizePortfolio(symbols, options);
      
      expect(result1.allocation).toHaveLength(result2.allocation.length);
      
      // Results should be similar (allowing for minor numerical differences)
      for (let i = 0; i < result1.allocation.length; i++) {
        expect(result1.allocation[i].weight).toBeCloseTo(result2.allocation[i].weight, 3);
      }
    });
  });
});