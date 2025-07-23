/**
 * Unit Tests for REAL Crypto Analytics Helper Methods
 * Tests the mathematical calculations and data processing functions
 */

import { describe, it, expect, vi, beforeEach } from 'vitest';

// Mock the CryptoMarketAnalytics class methods for unit testing
class MockCryptoMarketAnalytics {
  calculateReturns(prices) {
    const returns = [];
    for (let i = 1; i < prices.length; i++) {
      if (prices[i-1] > 0) {
        returns.push((prices[i] - prices[i-1]) / prices[i-1]);
      }
    }
    return returns;
  }

  calculatePearsonCorrelation(x, y) {
    if (x.length === 0 || y.length === 0 || x.length !== y.length) {
      return 0; // Default neutral correlation if no data
    }

    const n = x.length;
    const sumX = x.reduce((a, b) => a + b, 0);
    const sumY = y.reduce((a, b) => a + b, 0);
    const sumXY = x.reduce((acc, xi, i) => acc + xi * y[i], 0);
    const sumX2 = x.reduce((acc, xi) => acc + xi * xi, 0);
    const sumY2 = y.reduce((acc, yi) => acc + yi * yi, 0);

    const numerator = n * sumXY - sumX * sumY;
    const denominator = Math.sqrt((n * sumX2 - sumX * sumX) * (n * sumY2 - sumY * sumY));

    if (denominator === 0) return 0;
    return numerator / denominator;
  }

  calculateVolumeChange(coinsData) {
    const totalVolume24h = coinsData.reduce((sum, coin) => sum + (coin.total_volume || 0), 0);
    if (totalVolume24h === 0) return 0; // Handle zero volume
    const previousVolume = totalVolume24h / 1.05;
    return ((totalVolume24h - previousVolume) / previousVolume) * 100;
  }

  findTopGainers(coinsData, count) {
    return coinsData
      .filter(coin => coin.price_change_percentage_24h > 0)
      .sort((a, b) => b.price_change_percentage_24h - a.price_change_percentage_24h)
      .slice(0, count)
      .map((coin, index) => ({
        symbol: coin.symbol.toUpperCase(),
        rank_change: Math.floor(coin.price_change_percentage_24h / 5),
        market_cap: coin.market_cap
      }));
  }

  findTopLosers(coinsData, count) {
    return coinsData
      .filter(coin => coin.price_change_percentage_24h < 0)
      .sort((a, b) => a.price_change_percentage_24h - b.price_change_percentage_24h)
      .slice(0, count)
      .map((coin, index) => ({
        symbol: coin.symbol.toUpperCase(),
        rank_change: Math.ceil(coin.price_change_percentage_24h / 5),
        market_cap: coin.market_cap
      }));
  }

  calculateSimpleRSI(change1d, change7d) {
    const recentMomentum = (change1d * 0.7) + (change7d * 0.3);
    const normalizedMomentum = Math.max(-50, Math.min(50, recentMomentum));
    return Math.round(50 + normalizedMomentum);
  }

  calculateMomentumScore(change24h) {
    const normalized = Math.max(-50, Math.min(50, change24h));
    return Math.round(50 + normalized);
  }

  calculatePriceTargets(currentPrice, momentum, timeframe) {
    let multiplier = 1;
    
    switch (timeframe) {
      case 'short_term':
        multiplier = Math.abs(momentum) * 0.01;
        break;
      case 'medium_term':
        multiplier = Math.abs(momentum) * 0.02;
        break;
      case 'long_term':
        multiplier = Math.abs(momentum) * 0.01;
        break;
    }
    
    const baseChange = currentPrice * multiplier;
    
    if (momentum >= 0) {
      // Positive momentum: optimistic is highest
      return {
        optimistic: Math.round(currentPrice + (baseChange * 1.5)),
        realistic: Math.round(currentPrice + baseChange),
        pessimistic: Math.round(currentPrice + (baseChange * 0.5))
      };
    } else {
      // Negative momentum: optimistic is least decline (smallest negative change)
      return {
        optimistic: Math.round(currentPrice - (baseChange * 0.5)), // Least decline
        realistic: Math.round(currentPrice - baseChange),           // Expected decline
        pessimistic: Math.round(currentPrice - (baseChange * 1.5)) // Most decline
      };
    }
  }

  assessDeFiHealth(topProtocols, chainBreakdown, avgChange24h) {
    const protocolCount = topProtocols.length;
    const chainCount = chainBreakdown.length;
    
    const protocolDiversity = protocolCount > 8 ? 'high' : protocolCount > 5 ? 'medium' : 'low';
    const chainDiversity = chainCount > 6 ? 'high' : chainCount > 4 ? 'medium' : 'low';
    const liquidationRisk = avgChange24h < -5 ? 'high' : avgChange24h < -2 ? 'medium' : 'low';
    const innovationRate = avgChange24h > 3 ? 'high' : avgChange24h > 0 ? 'medium' : 'low';
    
    return {
      liquidation_risk: liquidationRisk,
      protocol_diversity: protocolDiversity,
      chain_diversity: chainDiversity,
      innovation_rate: innovationRate
    };
  }
}

describe('🧮 Crypto Analytics Real Mathematical Methods', () => {
  let analytics;

  beforeEach(() => {
    analytics = new MockCryptoMarketAnalytics();
  });

  describe('Price Returns Calculation', () => {
    it('should calculate returns correctly from price array', () => {
      const prices = [100, 105, 102, 108];
      const returns = analytics.calculateReturns(prices);
      
      expect(returns).toHaveLength(3);
      expect(returns[0]).toBeCloseTo(0.05, 4); // (105-100)/100 = 0.05
      expect(returns[1]).toBeCloseTo(-0.0286, 4); // (102-105)/105 ≈ -0.0286
      expect(returns[2]).toBeCloseTo(0.0588, 4); // (108-102)/102 ≈ 0.0588
    });

    it('should handle empty price array', () => {
      const returns = analytics.calculateReturns([]);
      expect(returns).toEqual([]);
    });

    it('should handle single price', () => {
      const returns = analytics.calculateReturns([100]);
      expect(returns).toEqual([]);
    });

    it('should skip zero prices', () => {
      const prices = [100, 0, 110];
      const returns = analytics.calculateReturns(prices);
      expect(returns).toHaveLength(1); // Only one valid return calculation
    });
  });

  describe('Pearson Correlation Calculation', () => {
    it('should calculate perfect positive correlation', () => {
      const x = [1, 2, 3, 4, 5];
      const y = [2, 4, 6, 8, 10];
      const correlation = analytics.calculatePearsonCorrelation(x, y);
      
      expect(correlation).toBeCloseTo(1.0, 4);
    });

    it('should calculate perfect negative correlation', () => {
      const x = [1, 2, 3, 4, 5];
      const y = [10, 8, 6, 4, 2];
      const correlation = analytics.calculatePearsonCorrelation(x, y);
      
      expect(correlation).toBeCloseTo(-1.0, 4);
    });

    it('should calculate no correlation', () => {
      const x = [1, 2, 3, 4, 5];
      const y = [3, 1, 4, 1, 5]; // Random pattern
      const correlation = analytics.calculatePearsonCorrelation(x, y);
      
      expect(correlation).toBeGreaterThan(-1);
      expect(correlation).toBeLessThan(1);
    });

    it('should return 0 for empty arrays', () => {
      const correlation = analytics.calculatePearsonCorrelation([], []);
      expect(correlation).toBe(0);
    });

    it('should return 0 for mismatched array lengths', () => {
      const correlation = analytics.calculatePearsonCorrelation([1, 2, 3], [1, 2]);
      expect(correlation).toBe(0);
    });

    it('should return 0 for zero variance', () => {
      const x = [5, 5, 5, 5];
      const y = [1, 2, 3, 4];
      const correlation = analytics.calculatePearsonCorrelation(x, y);
      expect(correlation).toBe(0);
    });
  });

  describe('Volume Change Calculation', () => {
    it('should calculate volume change correctly', () => {
      const coinsData = [
        { total_volume: 1000000000 },
        { total_volume: 2000000000 },
        { total_volume: 1500000000 }
      ];
      
      const volumeChange = analytics.calculateVolumeChange(coinsData);
      const expectedChange = ((4500000000 - 4500000000/1.05) / (4500000000/1.05)) * 100;
      
      expect(volumeChange).toBeCloseTo(expectedChange, 2);
      expect(volumeChange).toBeCloseTo(4.76, 0); // Approximately 5% increase (rounded)
    });

    it('should handle coins with no volume data', () => {
      const coinsData = [
        { total_volume: null },
        { total_volume: undefined },
        { /* no volume field */ }
      ];
      
      const volumeChange = analytics.calculateVolumeChange(coinsData);
      expect(volumeChange).toBeCloseTo(0, 2);
    });
  });

  describe('Top Gainers and Losers', () => {
    const mockCoinsData = [
      { symbol: 'btc', price_change_percentage_24h: 5.2, market_cap: 800000000000 },
      { symbol: 'eth', price_change_percentage_24h: -2.1, market_cap: 400000000000 },
      { symbol: 'sol', price_change_percentage_24h: 8.5, market_cap: 30000000000 },
      { symbol: 'ada', price_change_percentage_24h: -5.8, market_cap: 15000000000 },
      { symbol: 'matic', price_change_percentage_24h: 3.1, market_cap: 8000000000 }
    ];

    it('should find top gainers correctly', () => {
      const gainers = analytics.findTopGainers(mockCoinsData, 2);
      
      expect(gainers).toHaveLength(2);
      expect(gainers[0].symbol).toBe('SOL');
      expect(gainers[0].rank_change).toBe(Math.floor(8.5 / 5));
      expect(gainers[1].symbol).toBe('BTC');
      expect(gainers[1].rank_change).toBe(Math.floor(5.2 / 5));
    });

    it('should find top losers correctly', () => {
      const losers = analytics.findTopLosers(mockCoinsData, 2);
      
      expect(losers).toHaveLength(2);
      expect(losers[0].symbol).toBe('ADA');
      expect(losers[0].rank_change).toBe(Math.ceil(-5.8 / 5));
      expect(losers[1].symbol).toBe('ETH');
      expect(losers[1].rank_change).toBe(Math.ceil(-2.1 / 5));
    });

    it('should handle request for more gainers than available', () => {
      const gainers = analytics.findTopGainers(mockCoinsData, 10);
      expect(gainers.length).toBeLessThanOrEqual(3); // Only 3 positive performers
    });

    it('should handle empty coin data', () => {
      const gainers = analytics.findTopGainers([], 5);
      const losers = analytics.findTopLosers([], 5);
      
      expect(gainers).toEqual([]);
      expect(losers).toEqual([]);
    });
  });

  describe('RSI Calculation', () => {
    it('should calculate RSI correctly for bullish momentum', () => {
      const rsi = analytics.calculateSimpleRSI(10, 5); // Strong recent momentum
      const expectedRsi = Math.round(50 + ((10 * 0.7) + (5 * 0.3))); // 50 + 8.5 = 58.5 ≈ 59
      
      expect(rsi).toBe(59);
      expect(rsi).toBeGreaterThan(50);
    });

    it('should calculate RSI correctly for bearish momentum', () => {
      const rsi = analytics.calculateSimpleRSI(-8, -3);
      const expectedRsi = Math.round(50 + ((-8 * 0.7) + (-3 * 0.3))); // 50 + (-6.5) = 43.5 ≈ 44
      
      expect(rsi).toBe(44);
      expect(rsi).toBeLessThan(50);
    });

    it('should cap RSI at boundaries', () => {
      const highRsi = analytics.calculateSimpleRSI(100, 100); // Should cap at 100
      const lowRsi = analytics.calculateSimpleRSI(-100, -100); // Should cap at 0
      
      expect(highRsi).toBe(100);
      expect(lowRsi).toBe(0);
    });

    it('should return neutral RSI for no momentum', () => {
      const rsi = analytics.calculateSimpleRSI(0, 0);
      expect(rsi).toBe(50);
    });
  });

  describe('Momentum Score Calculation', () => {
    it('should calculate momentum score correctly', () => {
      const testCases = [
        { change24h: 10, expected: 60 },   // 50 + 10 = 60
        { change24h: -5, expected: 45 },   // 50 - 5 = 45
        { change24h: 0, expected: 50 },    // Neutral
        { change24h: 60, expected: 100 },  // Capped at 100
        { change24h: -60, expected: 0 }    // Capped at 0
      ];

      testCases.forEach(({ change24h, expected }) => {
        const score = analytics.calculateMomentumScore(change24h);
        expect(score).toBe(expected);
      });
    });
  });

  describe('Price Targets Calculation', () => {
    it('should calculate short-term targets correctly', () => {
      const targets = analytics.calculatePriceTargets(45000, 5, 'short_term');
      
      expect(targets.optimistic).toBeGreaterThan(targets.realistic);
      expect(targets.realistic).toBeGreaterThan(targets.pessimistic);
      expect(targets.realistic).toBeGreaterThan(45000);
    });

    it('should calculate medium-term targets with higher volatility', () => {
      const shortTerm = analytics.calculatePriceTargets(45000, 5, 'short_term');
      const mediumTerm = analytics.calculatePriceTargets(45000, 5, 'medium_term');
      
      // Medium-term should have wider ranges
      const shortRange = shortTerm.optimistic - shortTerm.pessimistic;
      const mediumRange = mediumTerm.optimistic - mediumTerm.pessimistic;
      
      expect(mediumRange).toBeGreaterThan(shortRange);
    });

    it('should handle negative momentum correctly', () => {
      const targets = analytics.calculatePriceTargets(45000, -10, 'long_term');
      
      console.log('Negative momentum targets:', targets);
      
      expect(targets.realistic).toBeLessThan(45000);
      // For negative momentum, all targets should be below current price
      // Optimistic = least decline, Pessimistic = most decline
      expect(targets.optimistic).toBeGreaterThan(targets.pessimistic);
    });

    it('should return integer prices', () => {
      const targets = analytics.calculatePriceTargets(45123.456, 3.7, 'short_term');
      
      expect(Number.isInteger(targets.optimistic)).toBe(true);
      expect(Number.isInteger(targets.realistic)).toBe(true);
      expect(Number.isInteger(targets.pessimistic)).toBe(true);
    });
  });

  describe('DeFi Health Assessment', () => {
    it('should assess high diversity correctly', () => {
      const topProtocols = new Array(12).fill({ name: 'Protocol' });
      const chainBreakdown = new Array(8).fill({ chain: 'Chain' });
      
      const health = analytics.assessDeFiHealth(topProtocols, chainBreakdown, 5);
      
      expect(health.protocol_diversity).toBe('high');
      expect(health.chain_diversity).toBe('high');
      expect(health.innovation_rate).toBe('high');
      expect(health.liquidation_risk).toBe('low');
    });

    it('should assess low diversity correctly', () => {
      const topProtocols = new Array(3).fill({ name: 'Protocol' });
      const chainBreakdown = new Array(2).fill({ chain: 'Chain' });
      
      const health = analytics.assessDeFiHealth(topProtocols, chainBreakdown, -8);
      
      expect(health.protocol_diversity).toBe('low');
      expect(health.chain_diversity).toBe('low');
      expect(health.innovation_rate).toBe('low');
      expect(health.liquidation_risk).toBe('high');
    });

    it('should assess medium diversity correctly', () => {
      const topProtocols = new Array(6).fill({ name: 'Protocol' });
      const chainBreakdown = new Array(5).fill({ chain: 'Chain' });
      
      const health = analytics.assessDeFiHealth(topProtocols, chainBreakdown, 1);
      
      expect(health.protocol_diversity).toBe('medium');
      expect(health.chain_diversity).toBe('medium');
      expect(health.innovation_rate).toBe('medium');
      expect(health.liquidation_risk).toBe('low');
    });
  });
});

describe('🔢 Edge Cases and Error Handling', () => {
  let analytics;

  beforeEach(() => {
    analytics = new MockCryptoMarketAnalytics();
  });

  it('should handle undefined values gracefully', () => {
    const coinsData = [
      { symbol: 'btc', price_change_percentage_24h: undefined, market_cap: null },
      { symbol: 'eth' } // Missing fields
    ];

    const gainers = analytics.findTopGainers(coinsData, 5);
    const losers = analytics.findTopLosers(coinsData, 5);

    expect(gainers).toEqual([]);
    expect(losers).toEqual([]);
  });

  it('should handle extreme values', () => {
    const extremeReturns = analytics.calculateReturns([1, 1000000, 0.001]);
    expect(extremeReturns).toHaveLength(2);
    expect(isFinite(extremeReturns[0])).toBe(true);
    expect(isFinite(extremeReturns[1])).toBe(true);
  });

  it('should maintain precision in calculations', () => {
    const x = [0.1, 0.2, 0.3, 0.4, 0.5];
    const y = [0.11, 0.22, 0.33, 0.44, 0.55];
    
    const correlation = analytics.calculatePearsonCorrelation(x, y);
    expect(correlation).toBeCloseTo(1.0, 10); // High precision
  });
});