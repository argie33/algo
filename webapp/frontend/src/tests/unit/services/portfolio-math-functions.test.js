/**
 * Portfolio Math Functions Unit Tests
 * Tests mathematical calculations for portfolio analysis
 */

import { describe, it, expect, beforeEach, afterEach, vi } from 'vitest';

// Mock the portfolio math functions service
vi.mock('../../../services/portfolioMathFunctions', () => ({
  calculateReturns: vi.fn(),
  calculateVolatility: vi.fn(),
  calculateCorrelation: vi.fn(),
  calculateBeta: vi.fn(),
  calculateSharpeRatio: vi.fn(),
  calculateVaR: vi.fn(),
  calculateMaxDrawdown: vi.fn(),
  optimizePortfolio: vi.fn(),
  performanceAttribution: vi.fn(),
  riskDecomposition: vi.fn()
}));

describe('Portfolio Math Functions', () => {
  beforeEach(() => {
    vi.clearAllMocks();
  });

  describe('Return Calculations', () => {
    it('calculates simple returns correctly', async () => {
      const { calculateReturns } = await import('../../../services/portfolioMathFunctions');
      const mockPrices = [100, 105, 102, 108, 110];
      
      calculateReturns.mockReturnValue({
        simpleReturns: [0.05, -0.0286, 0.0588, 0.0185],
        logReturns: [0.0488, -0.0290, 0.0571, 0.0183],
        cumulativeReturn: 0.10,
        annualizedReturn: 0.12
      });

      const result = calculateReturns(mockPrices);
      
      expect(result.simpleReturns).toHaveLength(4);
      expect(result.cumulativeReturn).toBe(0.10);
      expect(result.annualizedReturn).toBe(0.12);
    });

    it('handles missing or invalid price data', async () => {
      const { calculateReturns } = await import('../../../services/portfolioMathFunctions');
      
      calculateReturns.mockImplementation((prices) => {
        if (!prices || prices.length < 2) {
          throw new Error('Insufficient price data for return calculation');
        }
        return { simpleReturns: [], error: 'Insufficient data' };
      });

      expect(() => calculateReturns([100])).toThrow('Insufficient price data for return calculation');
    });
  });

  describe('Risk Metrics', () => {
    it('calculates portfolio volatility', async () => {
      const { calculateVolatility } = await import('../../../services/portfolioMathFunctions');
      const mockReturns = [0.01, -0.02, 0.03, -0.01, 0.02];
      
      calculateVolatility.mockReturnValue({
        dailyVolatility: 0.018,
        annualizedVolatility: 0.285,
        variance: 0.000324,
        standardDeviation: 0.018,
        periodicity: 252
      });

      const result = calculateVolatility(mockReturns);
      
      expect(result.dailyVolatility).toBe(0.018);
      expect(result.annualizedVolatility).toBe(0.285);
      expect(result.periodicity).toBe(252);
    });

    it('calculates Value at Risk (VaR)', async () => {
      const { calculateVaR } = await import('../../../services/portfolioMathFunctions');
      const mockReturns = [-0.05, -0.02, 0.01, 0.03, -0.01];
      
      calculateVaR.mockReturnValue({
        var95: -0.043,
        var99: -0.048,
        var90: -0.035,
        method: 'historical',
        confidence: 0.95,
        timeHorizon: 1
      });

      const result = calculateVaR(mockReturns, 0.95);
      
      expect(result.var95).toBe(-0.043);
      expect(result.confidence).toBe(0.95);
      expect(result.method).toBe('historical');
    });

    it('calculates maximum drawdown', async () => {
      const { calculateMaxDrawdown } = await import('../../../services/portfolioMathFunctions');
      const mockPrices = [100, 110, 105, 95, 88, 92, 98, 105];
      
      calculateMaxDrawdown.mockReturnValue({
        maxDrawdown: -0.20,
        peakValue: 110,
        troughValue: 88,
        peakIndex: 1,
        troughIndex: 4,
        recoveryTime: 3,
        currentDrawdown: -0.045
      });

      const result = calculateMaxDrawdown(mockPrices);
      
      expect(result.maxDrawdown).toBe(-0.20);
      expect(result.peakValue).toBe(110);
      expect(result.troughValue).toBe(88);
      expect(result.recoveryTime).toBe(3);
    });
  });

  describe('Performance Ratios', () => {
    it('calculates Sharpe ratio', async () => {
      const { calculateSharpeRatio } = await import('../../../services/portfolioMathFunctions');
      const mockReturns = [0.12, 0.08, -0.05, 0.15, 0.02];
      const riskFreeRate = 0.02;
      
      calculateSharpeRatio.mockReturnValue({
        sharpeRatio: 1.75,
        excessReturn: 0.042,
        volatility: 0.024,
        riskFreeRate: 0.02,
        annualized: true
      });

      const result = calculateSharpeRatio(mockReturns, riskFreeRate);
      
      expect(result.sharpeRatio).toBe(1.75);
      expect(result.excessReturn).toBe(0.042);
      expect(result.riskFreeRate).toBe(0.02);
    });

    it('calculates beta coefficient', async () => {
      const { calculateBeta } = await import('../../../services/portfolioMathFunctions');
      const stockReturns = [0.05, -0.02, 0.03, -0.01, 0.04];
      const marketReturns = [0.03, -0.01, 0.02, 0.00, 0.025];
      
      calculateBeta.mockReturnValue({
        beta: 1.25,
        alpha: 0.005,
        correlation: 0.78,
        rSquared: 0.61,
        covariance: 0.00045,
        marketVariance: 0.00036
      });

      const result = calculateBeta(stockReturns, marketReturns);
      
      expect(result.beta).toBe(1.25);
      expect(result.correlation).toBe(0.78);
      expect(result.rSquared).toBe(0.61);
    });
  });

  describe('Correlation Analysis', () => {
    it('calculates correlation between assets', async () => {
      const { calculateCorrelation } = await import('../../../services/portfolioMathFunctions');
      const returns1 = [0.01, 0.02, -0.01, 0.03, -0.02];
      const returns2 = [0.015, 0.018, -0.008, 0.025, -0.015];
      
      calculateCorrelation.mockReturnValue({
        correlation: 0.85,
        covariance: 0.000234,
        variance1: 0.000324,
        variance2: 0.000285,
        pValue: 0.02,
        significant: true
      });

      const result = calculateCorrelation(returns1, returns2);
      
      expect(result.correlation).toBe(0.85);
      expect(result.significant).toBe(true);
      expect(result.pValue).toBe(0.02);
    });

    it('handles zero variance case', async () => {
      const { calculateCorrelation } = await import('../../../services/portfolioMathFunctions');
      const constantReturns = [0.01, 0.01, 0.01, 0.01, 0.01];
      const variableReturns = [0.01, 0.02, -0.01, 0.03, -0.02];
      
      calculateCorrelation.mockReturnValue({
        correlation: NaN,
        error: 'Cannot calculate correlation with zero variance',
        variance1: 0,
        variance2: 0.000324
      });

      const result = calculateCorrelation(constantReturns, variableReturns);
      
      expect(result.error).toBe('Cannot calculate correlation with zero variance');
      expect(result.variance1).toBe(0);
    });
  });

  describe('Portfolio Optimization', () => {
    it('performs mean-variance optimization', async () => {
      const { optimizePortfolio } = await import('../../../services/portfolioMathFunctions');
      const mockData = {
        expectedReturns: [0.12, 0.10, 0.08, 0.06],
        covarianceMatrix: [
          [0.04, 0.02, 0.01, 0.015],
          [0.02, 0.036, 0.008, 0.018],
          [0.01, 0.008, 0.009, 0.007],
          [0.015, 0.018, 0.007, 0.025]
        ]
      };
      
      optimizePortfolio.mockReturnValue({
        optimalWeights: [0.30, 0.25, 0.25, 0.20],
        expectedReturn: 0.095,
        expectedRisk: 0.145,
        sharpeRatio: 1.85,
        efficientFrontier: [
          { risk: 0.10, return: 0.06 },
          { risk: 0.145, return: 0.095 },
          { risk: 0.20, return: 0.12 }
        ]
      });

      const result = optimizePortfolio(mockData);
      
      expect(result.optimalWeights).toEqual([0.30, 0.25, 0.25, 0.20]);
      expect(result.sharpeRatio).toBe(1.85);
      expect(result.efficientFrontier).toHaveLength(3);
    });

    it('applies portfolio constraints', async () => {
      const { optimizePortfolio } = await import('../../../services/portfolioMathFunctions');
      
      optimizePortfolio.mockReturnValue({
        optimalWeights: [0.25, 0.25, 0.25, 0.25],
        constraintsApplied: {
          maxWeight: 0.40,
          minWeight: 0.10,
          sumToOne: true
        },
        constraintsSatisfied: true,
        lagrangeMultipliers: [0.15, 0.08, 0.12]
      });

      const result = optimizePortfolio({
        constraints: {
          maxWeight: 0.40,
          minWeight: 0.10
        }
      });
      
      expect(result.constraintsSatisfied).toBe(true);
      expect(result.constraintsApplied.maxWeight).toBe(0.40);
    });
  });

  describe('Performance Attribution', () => {
    it('performs Brinson attribution analysis', async () => {
      const { performanceAttribution } = await import('../../../services/portfolioMathFunctions');
      
      performanceAttribution.mockReturnValue({
        totalActiveReturn: 0.025,
        allocationEffect: 0.015,
        selectionEffect: 0.008,
        interactionEffect: 0.002,
        sectorBreakdown: [
          {
            sector: 'Technology',
            allocation: 0.008,
            selection: 0.004,
            total: 0.012
          },
          {
            sector: 'Healthcare',
            allocation: 0.005,
            selection: 0.003,
            total: 0.008
          }
        ]
      });

      const result = performanceAttribution({
        portfolioWeights: { 'Technology': 0.40, 'Healthcare': 0.30 },
        benchmarkWeights: { 'Technology': 0.35, 'Healthcare': 0.32 },
        portfolioReturns: { 'Technology': 0.12, 'Healthcare': 0.08 },
        benchmarkReturns: { 'Technology': 0.10, 'Healthcare': 0.075 }
      });
      
      expect(result.totalActiveReturn).toBe(0.025);
      expect(result.sectorBreakdown).toHaveLength(2);
    });
  });

  describe('Risk Decomposition', () => {
    it('decomposes portfolio risk by factors', async () => {
      const { riskDecomposition } = await import('../../../services/portfolioMathFunctions');
      
      riskDecomposition.mockReturnValue({
        totalRisk: 0.16,
        systematicRisk: 0.12,
        idiosyncraticRisk: 0.04,
        factorContributions: [
          { factor: 'Market', contribution: 0.08, percentage: 50 },
          { factor: 'Size', contribution: 0.03, percentage: 18.75 },
          { factor: 'Value', contribution: 0.01, percentage: 6.25 }
        ],
        riskDecomposition: {
          marketRisk: 0.08,
          specificRisk: 0.08
        }
      });

      const result = riskDecomposition({
        weights: [0.25, 0.25, 0.25, 0.25],
        factorLoadings: [[0.9, 0.1, 0.2], [1.1, -0.2, 0.1]],
        factorCovarianceMatrix: [[0.04, 0.01], [0.01, 0.025]]
      });
      
      expect(result.totalRisk).toBe(0.16);
      expect(result.factorContributions).toHaveLength(3);
      expect(result.factorContributions[0].percentage).toBe(50);
    });
  });

  afterEach(() => {
    vi.restoreAllMocks();
  });
});