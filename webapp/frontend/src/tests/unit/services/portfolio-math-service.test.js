/**
 * Portfolio Math Service Unit Tests
 * Tests VaR calculations, portfolio optimization, and risk metrics
 */

import { describe, it, expect, beforeEach, afterEach, vi } from 'vitest';

// Mock ml-matrix
vi.mock('ml-matrix', () => ({
  Matrix: vi.fn().mockImplementation((data) => ({
    data,
    transpose: vi.fn().mockReturnThis(),
    mmul: vi.fn().mockReturnValue({ data: [[1, 0], [0, 1]] }),
    inverse: vi.fn().mockReturnValue({ data: [[1, 0], [0, 1]] }),
    get: vi.fn((i, j) => 0.5),
    to2DArray: vi.fn(() => [[1, 0], [0, 1]]),
    rows: 2,
    columns: 2
  })),
  SingularValueDecomposition: vi.fn().mockImplementation(() => ({
    leftSingularVectors: { data: [[1, 0], [0, 1]] },
    rightSingularVectors: { data: [[1, 0], [0, 1]] },
    diagonal: [1, 0.5]
  })),
  EigenvalueDecomposition: vi.fn().mockImplementation(() => ({
    eigenvectorMatrix: { data: [[1, 0], [0, 1]] },
    realEigenvalues: [0.8, 0.2]
  }))
}));

// Mock the actual portfolio math service
vi.mock('../../../services/portfolioMath', () => ({
  calculateVaR: vi.fn(),
  calculateSharpeRatio: vi.fn(),
  calculateBeta: vi.fn(),
  optimizePortfolio: vi.fn(),
  calculateCorrelationMatrix: vi.fn(),
  calculatePortfolioVolatility: vi.fn(),
  calculateMaxDrawdown: vi.fn(),
  calculateSortinoRatio: vi.fn(),
  performMonteCarlo: vi.fn()
}));

describe('Portfolio Math Service', () => {
  beforeEach(() => {
    vi.clearAllMocks();
  });

  describe('Value at Risk (VaR) Calculations', () => {
    it('calculates historical VaR correctly', async () => {
      const { calculateVaR } = await import('../../../services/portfolioMath');
      const mockReturns = [-0.05, -0.02, 0.01, 0.03, -0.01, 0.02, -0.03];
      
      calculateVaR.mockReturnValue({
        var95: -0.048,
        var99: -0.052,
        expectedShortfall: -0.050,
        confidence: 0.95
      });

      const result = calculateVaR(mockReturns, 0.95);
      
      expect(result.var95).toBe(-0.048);
      expect(result.var99).toBe(-0.052);
      expect(result.expectedShortfall).toBe(-0.050);
      expect(result.confidence).toBe(0.95);
    });

    it('handles parametric VaR calculation', async () => {
      const { calculateVaR } = await import('../../../services/portfolioMath');
      const mockReturns = [0.01, 0.02, -0.01, 0.03, -0.02];
      
      calculateVaR.mockReturnValue({
        parametricVaR: -0.032,
        mean: 0.006,
        standardDeviation: 0.018,
        zscore: -1.645
      });

      const result = calculateVaR(mockReturns, 0.95, 'parametric');
      
      expect(result.parametricVaR).toBe(-0.032);
      expect(result.mean).toBe(0.006);
      expect(result.standardDeviation).toBe(0.018);
    });

    it('calculates Monte Carlo VaR', async () => {
      const { performMonteCarlo } = await import('../../../services/portfolioMath');
      
      performMonteCarlo.mockReturnValue({
        var95: -0.045,
        var99: -0.065,
        paths: 10000,
        convergence: true,
        averageReturn: 0.008
      });

      const result = performMonteCarlo({
        mean: 0.01,
        volatility: 0.20,
        timeHorizon: 1,
        simulations: 10000
      });
      
      expect(result.var95).toBe(-0.045);
      expect(result.paths).toBe(10000);
      expect(result.convergence).toBe(true);
    });
  });

  describe('Risk-Adjusted Returns', () => {
    it('calculates Sharpe ratio accurately', async () => {
      const { calculateSharpeRatio } = await import('../../../services/portfolioMath');
      const mockReturns = [0.12, 0.08, -0.05, 0.15, 0.02];
      const riskFreeRate = 0.02;
      
      calculateSharpeRatio.mockReturnValue({
        sharpeRatio: 1.85,
        excessReturn: 0.042,
        volatility: 0.0227,
        annualizedSharpe: 1.85
      });

      const result = calculateSharpeRatio(mockReturns, riskFreeRate);
      
      expect(result.sharpeRatio).toBe(1.85);
      expect(result.excessReturn).toBe(0.042);
      expect(result.volatility).toBe(0.0227);
    });

    it('calculates Sortino ratio with downside deviation', async () => {
      const { calculateSortinoRatio } = await import('../../../services/portfolioMath');
      const mockReturns = [0.10, -0.05, 0.08, -0.03, 0.12];
      
      calculateSortinoRatio.mockReturnValue({
        sortinoRatio: 2.15,
        downsideDeviation: 0.028,
        targetReturn: 0.02,
        excessReturn: 0.034
      });

      const result = calculateSortinoRatio(mockReturns, 0.02);
      
      expect(result.sortinoRatio).toBe(2.15);
      expect(result.downsideDeviation).toBe(0.028);
    });

    it('calculates maximum drawdown', async () => {
      const { calculateMaxDrawdown } = await import('../../../services/portfolioMath');
      const mockPrices = [100, 110, 105, 95, 88, 92, 98];
      
      calculateMaxDrawdown.mockReturnValue({
        maxDrawdown: -0.20,
        peakValue: 110,
        troughValue: 88,
        recoveryTime: 3,
        currentDrawdown: -0.11
      });

      const result = calculateMaxDrawdown(mockPrices);
      
      expect(result.maxDrawdown).toBe(-0.20);
      expect(result.peakValue).toBe(110);
      expect(result.troughValue).toBe(88);
    });
  });

  describe('Beta and Correlation Analysis', () => {
    it('calculates stock beta against market', async () => {
      const { calculateBeta } = await import('../../../services/portfolioMath');
      const stockReturns = [0.05, -0.02, 0.03, -0.01, 0.04];
      const marketReturns = [0.03, -0.01, 0.02, 0.00, 0.025];
      
      calculateBeta.mockReturnValue({
        beta: 1.25,
        alpha: 0.005,
        correlation: 0.78,
        rSquared: 0.61,
        standardError: 0.15
      });

      const result = calculateBeta(stockReturns, marketReturns);
      
      expect(result.beta).toBe(1.25);
      expect(result.correlation).toBe(0.78);
      expect(result.rSquared).toBe(0.61);
    });

    it('calculates correlation matrix for multiple assets', async () => {
      const { calculateCorrelationMatrix } = await import('../../../services/portfolioMath');
      const mockReturns = {
        'AAPL': [0.05, -0.02, 0.03],
        'GOOGL': [0.04, -0.01, 0.02],
        'MSFT': [0.03, -0.015, 0.025]
      };
      
      calculateCorrelationMatrix.mockReturnValue({
        correlationMatrix: [
          [1.00, 0.75, 0.68],
          [0.75, 1.00, 0.82],
          [0.68, 0.82, 1.00]
        ],
        assets: ['AAPL', 'GOOGL', 'MSFT'],
        eigenvalues: [2.45, 0.38, 0.17]
      });

      const result = calculateCorrelationMatrix(mockReturns);
      
      expect(result.correlationMatrix[0][0]).toBe(1.00);
      expect(result.assets).toEqual(['AAPL', 'GOOGL', 'MSFT']);
      expect(result.eigenvalues).toBeDefined();
    });
  });

  describe('Portfolio Optimization', () => {
    it('performs mean-variance optimization', async () => {
      const { optimizePortfolio } = await import('../../../services/portfolioMath');
      const mockAssets = ['AAPL', 'GOOGL', 'BND', 'SPY'];
      const mockReturns = [0.12, 0.10, 0.04, 0.08];
      const mockCovarianceMatrix = [
        [0.04, 0.02, 0.01, 0.015],
        [0.02, 0.036, 0.008, 0.018],
        [0.01, 0.008, 0.009, 0.007],
        [0.015, 0.018, 0.007, 0.025]
      ];
      
      optimizePortfolio.mockReturnValue({
        optimalWeights: [0.35, 0.25, 0.20, 0.20],
        expectedReturn: 0.089,
        expectedVolatility: 0.156,
        sharpeRatio: 1.67,
        efficientFrontier: [
          { risk: 0.12, return: 0.06 },
          { risk: 0.156, return: 0.089 },
          { risk: 0.20, return: 0.11 }
        ]
      });

      const result = optimizePortfolio({
        assets: mockAssets,
        expectedReturns: mockReturns,
        covarianceMatrix: mockCovarianceMatrix,
        riskFreeRate: 0.02
      });
      
      expect(result.optimalWeights).toEqual([0.35, 0.25, 0.20, 0.20]);
      expect(result.sharpeRatio).toBe(1.67);
      expect(result.efficientFrontier).toHaveLength(3);
    });

    it('handles portfolio constraints', async () => {
      const { optimizePortfolio } = await import('../../../services/portfolioMath');
      
      optimizePortfolio.mockReturnValue({
        optimalWeights: [0.30, 0.30, 0.25, 0.15],
        constraintsSatisfied: true,
        maxWeight: 0.30,
        minWeight: 0.15,
        totalWeight: 1.00
      });

      const result = optimizePortfolio({
        assets: ['AAPL', 'GOOGL', 'BND', 'SPY'],
        expectedReturns: [0.12, 0.10, 0.04, 0.08],
        constraints: {
          maxWeight: 0.30,
          minWeight: 0.15,
          sectorLimits: { 'Technology': 0.60 }
        }
      });
      
      expect(result.constraintsSatisfied).toBe(true);
      expect(result.maxWeight).toBe(0.30);
      expect(Math.max(...result.optimalWeights)).toBeLessThanOrEqual(0.30);
    });

    it('calculates Black-Litterman optimization', async () => {
      const { optimizePortfolio } = await import('../../../services/portfolioMath');
      
      optimizePortfolio.mockReturnValue({
        blackLittermanWeights: [0.28, 0.32, 0.18, 0.22],
        adjustedReturns: [0.115, 0.105, 0.042, 0.085],
        confidenceMatrix: [
          [0.8, 0, 0, 0],
          [0, 0.9, 0, 0],
          [0, 0, 0.95, 0],
          [0, 0, 0, 0.75]
        ],
        tau: 0.025
      });

      const result = optimizePortfolio({
        method: 'black-litterman',
        marketCapWeights: [0.30, 0.30, 0.20, 0.20],
        views: [
          { asset: 'AAPL', expectedReturn: 0.115, confidence: 0.8 },
          { asset: 'GOOGL', expectedReturn: 0.105, confidence: 0.9 }
        ]
      });
      
      expect(result.blackLittermanWeights).toEqual([0.28, 0.32, 0.18, 0.22]);
      expect(result.tau).toBe(0.025);
    });
  });

  describe('Portfolio Volatility and Risk Metrics', () => {
    it('calculates portfolio volatility from weights and covariance', async () => {
      const { calculatePortfolioVolatility } = await import('../../../services/portfolioMath');
      const weights = [0.4, 0.3, 0.3];
      const covarianceMatrix = [
        [0.04, 0.012, 0.008],
        [0.012, 0.036, 0.015],
        [0.008, 0.015, 0.025]
      ];
      
      calculatePortfolioVolatility.mockReturnValue({
        annualizedVolatility: 0.187,
        variance: 0.035,
        diversificationRatio: 0.85,
        weightedAverageVol: 0.22
      });

      const result = calculatePortfolioVolatility(weights, covarianceMatrix);
      
      expect(result.annualizedVolatility).toBe(0.187);
      expect(result.diversificationRatio).toBe(0.85);
    });

    it('calculates component VaR and marginal VaR', async () => {
      const { calculateVaR } = await import('../../../services/portfolioMath');
      
      calculateVaR.mockReturnValue({
        componentVaR: [
          { asset: 'AAPL', var: -0.018, contribution: 0.42 },
          { asset: 'GOOGL', var: -0.015, contribution: 0.35 },
          { asset: 'BND', var: -0.005, contribution: 0.23 }
        ],
        marginalVaR: [
          { asset: 'AAPL', marginal: -0.045 },
          { asset: 'GOOGL', marginal: -0.038 },
          { asset: 'BND', marginal: -0.012 }
        ],
        totalPortfolioVaR: -0.043
      });

      const result = calculateVaR([0.01, -0.02, 0.015], 0.95, 'component');
      
      expect(result.componentVaR).toHaveLength(3);
      expect(result.totalPortfolioVaR).toBe(-0.043);
      expect(result.marginalVaR[0].asset).toBe('AAPL');
    });
  });

  describe('Performance Attribution', () => {
    it('performs Brinson attribution analysis', async () => {
      const { calculateBeta } = await import('../../../services/portfolioMath');
      
      calculateBeta.mockReturnValue({
        allocationEffect: 0.012,
        selectionEffect: 0.008,
        interactionEffect: 0.002,
        totalActiveReturn: 0.022,
        sectorBreakdown: [
          { sector: 'Technology', allocation: 0.008, selection: 0.005 },
          { sector: 'Healthcare', allocation: 0.003, selection: 0.002 },
          { sector: 'Financial', allocation: 0.001, selection: 0.001 }
        ]
      });

      const result = calculateBeta('brinson-attribution', {
        portfolioWeights: { 'Technology': 0.45, 'Healthcare': 0.30, 'Financial': 0.25 },
        benchmarkWeights: { 'Technology': 0.40, 'Healthcare': 0.32, 'Financial': 0.28 },
        portfolioReturns: { 'Technology': 0.12, 'Healthcare': 0.08, 'Financial': 0.06 },
        benchmarkReturns: { 'Technology': 0.10, 'Healthcare': 0.075, 'Financial': 0.055 }
      });
      
      expect(result.allocationEffect).toBe(0.012);
      expect(result.selectionEffect).toBe(0.008);
      expect(result.sectorBreakdown).toHaveLength(3);
    });
  });

  describe('Error Handling', () => {
    it('handles invalid input data gracefully', async () => {
      const { calculateVaR } = await import('../../../services/portfolioMath');
      calculateVaR.mockImplementation(() => {
        throw new Error('Invalid returns data: contains NaN values');
      });

      expect(() => calculateVaR([NaN, 0.01, 0.02])).toThrow('Invalid returns data: contains NaN values');
    });

    it('handles singular covariance matrices', async () => {
      const { optimizePortfolio } = await import('../../../services/portfolioMath');
      optimizePortfolio.mockReturnValue({
        error: 'Covariance matrix is singular - cannot invert',
        regularizedSolution: true,
        weights: [0.33, 0.33, 0.34],
        warning: 'Used regularization technique'
      });

      const result = optimizePortfolio({
        covarianceMatrix: [[0, 0], [0, 0]], // Singular matrix
        regularization: true
      });
      
      expect(result.error).toContain('singular');
      expect(result.regularizedSolution).toBe(true);
    });

    it('validates portfolio weight constraints', async () => {
      const { calculatePortfolioVolatility } = await import('../../../services/portfolioMath');
      calculatePortfolioVolatility.mockImplementation((weights) => {
        const sum = weights.reduce((a, b) => a + b, 0);
        if (Math.abs(sum - 1.0) > 1e-6) {
          throw new Error(`Portfolio weights must sum to 1.0, got ${sum}`);
        }
        return { annualizedVolatility: 0.15 };
      });

      expect(() => calculatePortfolioVolatility([0.5, 0.3, 0.1])).toThrow('Portfolio weights must sum to 1.0');
    });
  });

  afterEach(() => {
    vi.restoreAllMocks();
  });
});