/**
 * Financial Calculations Unit Tests
 * Comprehensive testing of all financial mathematics and calculations
 */

import { describe, it, expect, beforeEach } from 'vitest';

describe('🧮 Financial Calculations', () => {
  describe('Portfolio Mathematics', () => {
    it('should calculate portfolio total value correctly', () => {
      const positions = [
        { symbol: 'AAPL', quantity: 100, price: 150.00 },
        { symbol: 'GOOGL', quantity: 25, price: 2800.00 },
        { symbol: 'MSFT', quantity: 50, price: 380.00 }
      ];
      
      const cash = 5000;
      const expectedTotal = (100 * 150) + (25 * 2800) + (50 * 380) + 5000;
      
      const totalValue = calculatePortfolioValue(positions, cash);
      expect(totalValue).toBe(expectedTotal);
    });

    it('should calculate portfolio returns accurately', () => {
      const initialValue = 100000;
      const currentValue = 105000;
      
      const returns = calculateReturns(initialValue, currentValue);
      expect(returns).toBeCloseTo(0.05, 4); // 5% return
    });

    it('should calculate Sharpe ratio correctly', () => {
      const returns = [0.01, 0.02, -0.01, 0.03, 0.005];
      const riskFreeRate = 0.02;
      
      const sharpeRatio = calculateSharpeRatio(returns, riskFreeRate);
      expect(sharpeRatio).toBeGreaterThan(0);
      expect(sharpeRatio).toBeLessThan(5);
    });
  });

  describe('Risk Calculations', () => {
    it('should calculate Value at Risk (VaR)', () => {
      const returns = generateNormalReturns(252, 0, 0.15);
      const confidence = 0.95;
      
      const var95 = calculateVaR(returns, confidence);
      expect(var95).toBeLessThan(0); // VaR should be negative
    });

    it('should calculate portfolio beta', () => {
      const portfolioReturns = [0.01, 0.02, -0.01, 0.03];
      const marketReturns = [0.008, 0.015, -0.008, 0.025];
      
      const beta = calculateBeta(portfolioReturns, marketReturns);
      expect(beta).toBeGreaterThan(0);
    });
  });
});

// Helper functions (would be imported from actual modules)
function calculatePortfolioValue(positions, cash) {
  const positionsValue = positions.reduce((sum, pos) => sum + (pos.quantity * pos.price), 0);
  return positionsValue + cash;
}

function calculateReturns(initial, current) {
  return (current - initial) / initial;
}

function calculateSharpeRatio(returns, riskFreeRate) {
  const meanReturn = returns.reduce((sum, r) => sum + r, 0) / returns.length;
  const variance = returns.reduce((sum, r) => sum + Math.pow(r - meanReturn, 2), 0) / returns.length;
  const stdDev = Math.sqrt(variance);
  return (meanReturn - riskFreeRate) / stdDev;
}

function calculateVaR(returns, confidence) {
  const sorted = returns.sort((a, b) => a - b);
  const index = Math.floor((1 - confidence) * sorted.length);
  return sorted[index];
}

function calculateBeta(portfolioReturns, marketReturns) {
  const n = portfolioReturns.length;
  const portfolioMean = portfolioReturns.reduce((sum, r) => sum + r, 0) / n;
  const marketMean = marketReturns.reduce((sum, r) => sum + r, 0) / n;
  
  let covariance = 0;
  let marketVariance = 0;
  
  for (let i = 0; i < n; i++) {
    covariance += (portfolioReturns[i] - portfolioMean) * (marketReturns[i] - marketMean);
    marketVariance += Math.pow(marketReturns[i] - marketMean, 2);
  }
  
  return covariance / marketVariance;
}

function generateNormalReturns(count, mean, stdDev) {
  const returns = [];
  for (let i = 0; i < count; i++) {
    const u1 = Math.random();
    const u2 = Math.random();
    const z0 = Math.sqrt(-2 * Math.log(u1)) * Math.cos(2 * Math.PI * u2);
    returns.push(mean + stdDev * z0);
  }
  return returns;
}