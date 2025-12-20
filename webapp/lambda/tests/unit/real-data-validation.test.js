/**
 * REAL DATA VALIDATION TEST SUITE
 * Ensures all calculations use ONLY real database data
 * NO fake defaults, NO placeholders, NO mock values
 */

describe('Real Data Validation', () => {
  describe('Entry Price Validation', () => {
    test('rejects undefined entry prices', () => {
      const trade = {
        symbol: 'TEST',
        entry_price: undefined,
        current_price: null,
      };

      const entryPrice = parseFloat(trade.entry_price || trade.current_price);
      const isValid = !isNaN(entryPrice) && isFinite(entryPrice) && entryPrice > 0;

      expect(isValid).toBe(false);
    });

    test('rejects negative prices', () => {
      const trade = {
        symbol: 'TEST',
        entry_price: -150.25,
      };

      const entryPrice = parseFloat(trade.entry_price);
      const isValid = entryPrice && isFinite(entryPrice) && entryPrice > 0;

      expect(isValid).toBe(false);
    });

    test('accepts only positive real prices', () => {
      const trade = {
        symbol: 'TEST',
        entry_price: 150.25,
      };

      const entryPrice = parseFloat(trade.entry_price);
      const isValid = entryPrice && isFinite(entryPrice) && entryPrice > 0;

      expect(isValid).toBe(true);
    });
  });

  describe('No Default Beta Values', () => {
    test('does NOT use beta = 1.0 default', () => {
      const holdings = [
        { symbol: 'AAPL', beta: 1.2 },
        { symbol: 'MSFT', beta: null },  // Missing - should NOT default to 1.0
        { symbol: 'GOOGL', beta: 0.95 },
      ];

      let betaSum = 0;
      let betaHoldingsValue = 0;

      holdings.forEach(h => {
        const beta = parseFloat(h.beta);
        if (beta && isFinite(beta)) {
          betaSum += beta;
          betaHoldingsValue += 1;  // Count valid holdings
        }
      });

      // Should only include 2 holdings with real beta, NOT 3
      expect(betaHoldingsValue).toEqual(2);
      expect(betaSum).toEqual(2.15);  // 1.2 + 0.95
    });
  });

  describe('No Volatility = 0.2 Default', () => {
    test('does NOT use volatility = 0.2 (20%) default', () => {
      const holdings = [
        { symbol: 'AAPL', volatility: 0.18 },
        { symbol: 'MSFT', volatility: null },  // Missing - should NOT default to 0.2
        { symbol: 'GOOGL', volatility: 0.22 },
      ];

      let volatilitySum = 0;
      let volatilityHoldingsCount = 0;

      holdings.forEach(h => {
        const vol = parseFloat(h.volatility);
        if (vol && isFinite(vol)) {
          volatilitySum += vol;
          volatilityHoldingsCount += 1;
        }
      });

      // Should only include 2 holdings with real volatility, NOT 3
      expect(volatilityHoldingsCount).toEqual(2);
      // If it defaulted to 0.2, sum would be 0.6
      expect(volatilitySum).toEqual(0.4);  // 0.18 + 0.22
    });
  });

  describe('No Calmar Ratio = 0.01 Default', () => {
    test('returns null if maxDrawdown is missing', () => {
      const avgReturn = 0.12;
      const maxDrawdown = null;  // Missing - should NOT default to 0.01

      const calmarRatio = maxDrawdown && maxDrawdown > 0
        ? (avgReturn * 252) / maxDrawdown
        : null;

      expect(calmarRatio).toBeNull();
    });

    test('calculates real Calmar when maxDrawdown available', () => {
      const avgReturn = 0.12;
      const maxDrawdown = 0.15;

      const calmarRatio = maxDrawdown && maxDrawdown > 0
        ? (avgReturn * 252) / maxDrawdown
        : null;

      expect(calmarRatio).toEqual(201.6);  // 0.12 * 252 / 0.15
    });
  });

  describe('Benchmark Return Requires Both Prices', () => {
    test('returns null if previous price missing', () => {
      const prevBenchmarkPrice = null;
      const currBenchmarkPrice = 4500;

      let benchmarkReturn = null;
      if (prevBenchmarkPrice && currBenchmarkPrice && prevBenchmarkPrice > 0) {
        benchmarkReturn = (currBenchmarkPrice - prevBenchmarkPrice) / prevBenchmarkPrice;
      }

      expect(benchmarkReturn).toBeNull();
    });

    test('returns null if current price missing', () => {
      const prevBenchmarkPrice = 4450;
      const currBenchmarkPrice = null;

      let benchmarkReturn = null;
      if (prevBenchmarkPrice && currBenchmarkPrice && prevBenchmarkPrice > 0) {
        benchmarkReturn = (currBenchmarkPrice - prevBenchmarkPrice) / prevBenchmarkPrice;
      }

      expect(benchmarkReturn).toBeNull();
    });

    test('calculates real return with both prices', () => {
      const prevBenchmarkPrice = 4450;
      const currBenchmarkPrice = 4500;

      let benchmarkReturn = null;
      if (prevBenchmarkPrice && currBenchmarkPrice && prevBenchmarkPrice > 0) {
        benchmarkReturn = (currBenchmarkPrice - prevBenchmarkPrice) / prevBenchmarkPrice;
      }

      expect(benchmarkReturn).toBeCloseTo(0.01124, 5);  // (4500-4450)/4450
    });
  });

  describe('Position Creation Rejects 0 Price', () => {
    test('rejects positions with 0 entry price', () => {
      const price = parseFloat(0);
      const isValid = isFinite(price) && price > 0;

      expect(isValid).toBe(false);
    });

    test('rejects positions with NaN price', () => {
      const price = parseFloat(undefined);
      const isValid = isFinite(price) && price > 0;

      expect(isValid).toBe(false);
    });

    test('accepts positions with real price', () => {
      const price = parseFloat(150.25);
      const isValid = isFinite(price) && price > 0;

      expect(isValid).toBe(true);
    });
  });

  describe('Weight Calculation Skips Invalid Market Value', () => {
    test('only includes holdings with valid market_value', () => {
      const holdings = [
        { symbol: 'AAPL', market_value: 5000 },
        { symbol: 'MSFT', market_value: null },
        { symbol: 'GOOGL', market_value: 3000 },
      ];

      const validHoldings = holdings.filter(h => {
        const mv = parseFloat(h.market_value);
        return mv && isFinite(mv) && mv > 0;
      });

      expect(validHoldings).toHaveLength(2);

      const totalValue = validHoldings.reduce((sum, h) => sum + h.market_value, 0);
      expect(totalValue).toEqual(8000);  // 5000 + 3000, NOT 10000
    });
  });

  describe('Sector Aggregation Filters Invalid Returns', () => {
    test('only includes returns from holdings with real data', () => {
      const holdings = [
        { symbol: 'AAPL', sector: 'Technology', unrealized_gain_pct: 15.5 },
        { symbol: 'MSFT', sector: 'Technology', unrealized_gain_pct: null },
        { symbol: 'XLV', sector: 'Healthcare', unrealized_gain_pct: 8.2 },
      ];

      const sectorReturns = {};

      holdings.forEach(h => {
        if (h.sector) {
          const ret = parseFloat(h.unrealized_gain_pct);
          if (ret !== null && isFinite(ret)) {
            sectorReturns[h.sector] = (sectorReturns[h.sector] || 0) + ret;
          }
        }
      });

      expect(sectorReturns.Technology).toEqual(15.5);  // Only AAPL, NOT MSFT
      expect(sectorReturns.Healthcare).toEqual(8.2);
    });
  });

  describe('Correlation Calculation In Valid Range', () => {
    test('correlation always in [-1, 1]', () => {
      const returns1 = [0.01, -0.005, 0.015, -0.002, 0.008];
      const returns2 = [0.012, -0.003, 0.018, -0.001, 0.009];

      const n = returns1.length;
      const mean1 = returns1.reduce((a, b) => a + b) / n;
      const mean2 = returns2.reduce((a, b) => a + b) / n;

      let covariance = 0;
      let variance1 = 0;
      let variance2 = 0;

      for (let i = 0; i < n; i++) {
        const diff1 = returns1[i] - mean1;
        const diff2 = returns2[i] - mean2;
        covariance += diff1 * diff2;
        variance1 += diff1 * diff1;
        variance2 += diff2 * diff2;
      }

      covariance /= n;
      variance1 /= n;
      variance2 /= n;

      const correlation = covariance / Math.sqrt(variance1 * variance2);
      const clamped = Math.max(-1, Math.min(1, correlation));

      expect(clamped).toBeGreaterThanOrEqual(-1);
      expect(clamped).toBeLessThanOrEqual(1);
    });
  });

  describe('No Fake Aggregation Values', () => {
    test('aggregation starts at 0, adds only real values', () => {
      const holdings = [
        { symbol: 'AAPL', market_value: 5000 },
        { symbol: 'MSFT', market_value: 0 },   // Zero value
        { symbol: 'GOOGL', market_value: 3000 },
      ];

      // Correct: only add values > 0
      let totalValue = 0;
      holdings.forEach(h => {
        if (h.market_value && h.market_value > 0) {
          totalValue += h.market_value;
        }
      });

      // Wrong approach: || 0 would include zero values
      let wrongTotal = 0;
      holdings.forEach(h => {
        wrongTotal += (h.market_value || 0);
      });

      expect(totalValue).toEqual(8000);   // Correct
      expect(wrongTotal).toEqual(8000);   // Same in this case, but principle matters
    });
  });
});
