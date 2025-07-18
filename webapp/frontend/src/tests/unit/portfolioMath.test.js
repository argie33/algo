/**
 * Unit Tests for Portfolio Math Functions
 * Tests individual calculations like VaR, Sharpe ratio, etc.
 */

import { describe, test, expect, beforeEach } from 'vitest';
import {
  calculateVaR,
  calculateSharpeRatio,
  calculateBeta,
  calculateCorrelationMatrix,
  calculatePortfolioReturn,
  calculateVolatility
} from '../../services/portfolioMathFunctions.js';

describe('Portfolio Math Service - Unit Tests', () => {
  let mockPortfolioData;
  let mockMarketData;

  beforeEach(() => {
    // Setup test data for each test
    mockPortfolioData = {
      positions: [
        { symbol: 'AAPL', shares: 100, price: 150.00, weight: 0.5 },
        { symbol: 'GOOGL', shares: 50, price: 2000.00, weight: 0.5 }
      ],
      totalValue: 115000,
      returns: [0.02, -0.01, 0.03, -0.02, 0.01] // 5 days of returns
    };

    mockMarketData = {
      spyReturns: [0.015, -0.008, 0.025, -0.015, 0.008] // S&P 500 returns
    };
  });

  describe('VaR (Value at Risk) Calculations', () => {
    test('calculates 1-day VaR correctly with parametric method', () => {
      const result = calculateVaR(mockPortfolioData.returns, 0.05); // 95% confidence
      
      expect(result).toHaveProperty('var');
      expect(result).toHaveProperty('confidenceLevel');
      expect(result).toHaveProperty('method');
      expect(result.var).toBeGreaterThan(0);
      expect(result.confidenceLevel).toBe(0.05);
      expect(result.method).toBe('parametric');
    });

    test('calculates historical VaR correctly', () => {
      const result = calculateVaR(mockPortfolioData.returns, 0.05, 'historical');
      
      expect(result.method).toBe('historical');
      expect(result.var).toBeGreaterThan(0);
      expect(typeof result.var).toBe('number');
    });

    test('handles edge cases - empty returns array', () => {
      expect(() => calculateVaR([], 0.05)).toThrow('Returns array cannot be empty');
    });

    test('handles edge cases - invalid confidence level', () => {
      expect(() => calculateVaR(mockPortfolioData.returns, -0.1)).toThrow('Confidence level must be between 0 and 1');
      expect(() => calculateVaR(mockPortfolioData.returns, 1.1)).toThrow('Confidence level must be between 0 and 1');
    });
  });

  describe('Sharpe Ratio Calculations', () => {
    test('calculates Sharpe ratio correctly', () => {
      const riskFreeRate = 0.02; // 2% annual risk-free rate
      const result = calculateSharpeRatio(mockPortfolioData.returns, riskFreeRate);
      
      expect(result).toHaveProperty('sharpeRatio');
      expect(result).toHaveProperty('annualizedReturn');
      expect(result).toHaveProperty('annualizedVolatility');
      expect(typeof result.sharpeRatio).toBe('number');
      expect(result.annualizedReturn).toBeGreaterThan(0);
      expect(result.annualizedVolatility).toBeGreaterThan(0);
    });

    test('handles zero volatility case', () => {
      const zeroVolatilityReturns = [0.01, 0.01, 0.01, 0.01, 0.01];
      const result = calculateSharpeRatio(zeroVolatilityReturns, 0.02);
      
      expect(result.sharpeRatio).toBe(Infinity);
      expect(result.annualizedVolatility).toBe(0);
    });

    test('handles negative excess returns', () => {
      const negativeReturns = [-0.01, -0.02, -0.01, -0.03, -0.01];
      const result = calculateSharpeRatio(negativeReturns, 0.02);
      
      expect(result.sharpeRatio).toBeLessThan(0);
    });
  });

  describe('Beta Calculations', () => {
    test('calculates beta correctly against market benchmark', () => {
      const result = calculateBeta(mockPortfolioData.returns, mockMarketData.spyReturns);
      
      expect(result).toHaveProperty('beta');
      expect(result).toHaveProperty('correlation');
      expect(result).toHaveProperty('rSquared');
      expect(typeof result.beta).toBe('number');
      expect(result.correlation).toBeGreaterThanOrEqual(-1);
      expect(result.correlation).toBeLessThanOrEqual(1);
      expect(result.rSquared).toBeGreaterThanOrEqual(0);
      expect(result.rSquared).toBeLessThanOrEqual(1);
    });

    test('handles perfectly correlated returns (beta = 1)', () => {
      const identicalReturns = [...mockMarketData.spyReturns];
      const result = calculateBeta(identicalReturns, mockMarketData.spyReturns);
      
      expect(result.beta).toBeCloseTo(1, 2);
      expect(result.correlation).toBeCloseTo(1, 2);
    });

    test('handles uncorrelated returns (beta ≈ 0)', () => {
      const uncorrelatedReturns = [0.05, -0.03, 0.02, -0.01, 0.04];
      const result = calculateBeta(uncorrelatedReturns, mockMarketData.spyReturns);
      
      expect(typeof result.beta).toBe('number');
      expect(result.correlation).toBeGreaterThanOrEqual(-1);
      expect(result.correlation).toBeLessThanOrEqual(1);
    });
  });

  describe('Correlation Matrix Calculations', () => {
    test('calculates correlation matrix for multiple assets', () => {
      const assetReturns = {
        AAPL: [0.02, -0.01, 0.03, -0.02, 0.01],
        GOOGL: [0.01, -0.02, 0.04, -0.01, 0.02],
        MSFT: [0.015, -0.015, 0.025, -0.015, 0.015]
      };
      
      const result = calculateCorrelationMatrix(assetReturns);
      
      expect(result).toHaveProperty('matrix');
      expect(result).toHaveProperty('symbols');
      expect(result.symbols).toEqual(['AAPL', 'GOOGL', 'MSFT']);
      expect(result.matrix.length).toBe(3);
      expect(result.matrix[0].length).toBe(3);
      
      // Diagonal elements should be 1 (correlation with self)
      expect(result.matrix[0][0]).toBeCloseTo(1, 2);
      expect(result.matrix[1][1]).toBeCloseTo(1, 2);
      expect(result.matrix[2][2]).toBeCloseTo(1, 2);
      
      // Matrix should be symmetric
      expect(result.matrix[0][1]).toBeCloseTo(result.matrix[1][0], 2);
      expect(result.matrix[0][2]).toBeCloseTo(result.matrix[2][0], 2);
      expect(result.matrix[1][2]).toBeCloseTo(result.matrix[2][1], 2);
    });

    test('handles single asset case', () => {
      const singleAssetReturns = {
        AAPL: [0.02, -0.01, 0.03, -0.02, 0.01]
      };
      
      const result = calculateCorrelationMatrix(singleAssetReturns);
      
      expect(result.matrix.length).toBe(1);
      expect(result.matrix[0][0]).toBe(1);
    });
  });

  describe('Portfolio Return Calculations', () => {
    test('calculates weighted portfolio return correctly', () => {
      const result = calculatePortfolioReturn(mockPortfolioData.positions);
      
      expect(result).toHaveProperty('totalReturn');
      expect(result).toHaveProperty('weightedReturn');
      expect(result).toHaveProperty('contributions');
      expect(typeof result.totalReturn).toBe('number');
      expect(Array.isArray(result.contributions)).toBe(true);
      expect(result.contributions.length).toBe(mockPortfolioData.positions.length);
    });

    test('handles empty portfolio', () => {
      expect(() => calculatePortfolioReturn([])).toThrow('Portfolio cannot be empty');
    });

    test('validates position weights sum to 1', () => {
      const invalidWeights = [
        { symbol: 'AAPL', shares: 100, price: 150.00, weight: 0.7 },
        { symbol: 'GOOGL', shares: 50, price: 2000.00, weight: 0.7 } // Weights sum to 1.4
      ];
      
      expect(() => calculatePortfolioReturn(invalidWeights)).toThrow('Position weights must sum to 1');
    });
  });

  describe('Volatility Calculations', () => {
    test('calculates annualized volatility correctly', () => {
      const result = calculateVolatility(mockPortfolioData.returns);
      
      expect(result).toHaveProperty('dailyVolatility');
      expect(result).toHaveProperty('annualizedVolatility');
      expect(result).toHaveProperty('variance');
      expect(result.dailyVolatility).toBeGreaterThan(0);
      expect(result.annualizedVolatility).toBeGreaterThan(result.dailyVolatility);
      expect(result.variance).toBeGreaterThan(0);
    });

    test('handles constant returns (zero volatility)', () => {
      const constantReturns = [0.01, 0.01, 0.01, 0.01, 0.01];
      const result = calculateVolatility(constantReturns);
      
      expect(result.dailyVolatility).toBe(0);
      expect(result.annualizedVolatility).toBe(0);
      expect(result.variance).toBe(0);
    });
  });

  describe('Edge Cases and Error Handling', () => {
    test('handles NaN values in returns', () => {
      const returnsWithNaN = [0.01, NaN, 0.02, -0.01, 0.03];
      
      expect(() => calculateVaR(returnsWithNaN, 0.05)).toThrow('Returns contain invalid values');
    });

    test('handles infinite values in returns', () => {
      const returnsWithInfinity = [0.01, Infinity, 0.02, -0.01, 0.03];
      
      expect(() => calculateSharpeRatio(returnsWithInfinity, 0.02)).toThrow('Returns contain invalid values');
    });

    test('handles mismatched array lengths', () => {
      const shortMarketReturns = [0.01, 0.02]; // Only 2 elements
      
      expect(() => calculateBeta(mockPortfolioData.returns, shortMarketReturns)).toThrow('Array lengths must match');
    });
  });
});

// Performance benchmarks
describe('Portfolio Math Performance Tests', () => {
  test('VaR calculation performance with large dataset', () => {
    const largeReturns = Array.from({ length: 1000 }, () => Math.random() * 0.04 - 0.02);
    
    const startTime = performance.now();
    const result = calculateVaR(largeReturns, 0.05);
    const endTime = performance.now();
    
    expect(endTime - startTime).toBeLessThan(100); // Should complete in under 100ms
    expect(result.var).toBeGreaterThan(0);
  });

  test('Correlation matrix performance with many assets', () => {
    const manyAssets = {};
    for (let i = 0; i < 50; i++) {
      manyAssets[`ASSET_${i}`] = Array.from({ length: 252 }, () => Math.random() * 0.04 - 0.02);
    }
    
    const startTime = performance.now();
    const result = calculateCorrelationMatrix(manyAssets);
    const endTime = performance.now();
    
    expect(endTime - startTime).toBeLessThan(1000); // Should complete in under 1 second
    expect(result.matrix.length).toBe(50);
  });
});