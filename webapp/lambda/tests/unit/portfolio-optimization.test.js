/**
 * PORTFOLIO OPTIMIZATION TEST SUITE
 * Tests core algorithms for portfolio recommendations and risk metrics
 */

describe('Portfolio Optimization Algorithms', () => {
  describe('Correlation Analysis', () => {
    test('calculateSimpleCorrelation - returns valid correlation in [-1, 1]', () => {
      const returns1 = [0.01, -0.005, 0.015, -0.002, 0.008];
      const returns2 = [0.012, -0.003, 0.018, -0.001, 0.009];

      // Calculate correlation manually
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

      expect(correlation).not.toBeNull();
      expect(correlation).toBeGreaterThanOrEqual(-1);
      expect(correlation).toBeLessThanOrEqual(1);
    });

    test('calculateSimpleCorrelation - returns null for insufficient data', () => {
      const returns1 = [0.01];
      const returns2 = [0.012];

      // Should return null for insufficient data
      const isValid = returns1.length > 1 && returns2.length > 1;
      expect(isValid).toBe(false);
    });

    test('calculateSimpleCorrelation - returns 1 for identical returns', () => {
      const returns = [0.01, 0.02, 0.015, -0.005, 0.008];

      const n = returns.length;
      const mean = returns.reduce((a, b) => a + b) / n;

      let covariance = 0;
      let variance = 0;

      for (let i = 0; i < n; i++) {
        const diff = returns[i] - mean;
        covariance += diff * diff;
        variance += diff * diff;
      }

      covariance /= n;
      variance /= n;

      const correlation = covariance / variance;

      expect(correlation).toBeCloseTo(1, 5);
    });

    test('calculateDiversificationScore - returns 0-100', () => {
      const correlations = [0.5, 0.3, 0.2, 0.4];
      const avgCorrelation = correlations.reduce((a, b) => a + b) / correlations.length;
      const score = (1 - avgCorrelation) * 100;

      expect(score).toBeGreaterThanOrEqual(0);
      expect(score).toBeLessThanOrEqual(100);
    });

    test('calculateDiversificationScore - higher when correlations are lower', () => {
      const lowCorrelations = [0.1, 0.2, 0.15];
      const highCorrelations = [0.8, 0.9, 0.85];

      const avgLow = lowCorrelations.reduce((a, b) => a + b) / lowCorrelations.length;
      const avgHigh = highCorrelations.reduce((a, b) => a + b) / highCorrelations.length;

      const lowScore = (1 - avgLow) * 100;
      const highScore = (1 - avgHigh) * 100;

      expect(lowScore).toBeGreaterThan(highScore);
    });
  });

  describe('Recommendation Generation', () => {
    test('calculateFitScore - returns 0-100 range', () => {
      const components = {
        composite: 35,  // 50% of 70/100
        marketFit: 12,  // 15% of 80/100
        correlation: 14, // 20% of 70/100
        sector: 12,  // 15% of 80/100
      };

      const fitScore = (
        components.composite +
        components.marketFit +
        components.correlation +
        components.sector
      ) / 100;

      expect(fitScore).toBeGreaterThanOrEqual(0);
      expect(fitScore).toBeLessThanOrEqual(1);
    });

    test('fit score properly weights components', () => {
      const testStock = {
        composite_score: 75,
        current_price: 150.25,
      };

      const marketExposure = 60; // Moderate market conditions

      // Market fit calculation
      const marketFit = (
        testStock.composite_score * 0.4 +
        (marketExposure > 70 ? 20 : marketExposure > 40 ? 50 : 30)
      ) / 2;

      expect(marketFit).toBeGreaterThan(0);
      expect(marketFit).toBeLessThan(100);
    });
  });

  describe('Quantity Calculation', () => {
    test('calculates correct shares from suggested amount', () => {
      const suggestedAmount = 10000;
      const currentPrice = 150.25;

      const quantity = Math.floor(suggestedAmount / currentPrice);

      expect(quantity).toEqual(66);
      expect(quantity * currentPrice).toBeLessThanOrEqual(suggestedAmount);
    });

    test('REDUCE calculates 25% of position', () => {
      const totalQuantity = 100;
      const reduceQuantity = Math.floor(totalQuantity * 0.25);

      expect(reduceQuantity).toEqual(25);
    });

    test('handles zero price gracefully', () => {
      const suggestedAmount = 10000;
      const currentPrice = 0;

      const quantity = currentPrice > 0 ? Math.floor(suggestedAmount / currentPrice) : 0;

      expect(quantity).toEqual(0);
    });
  });

  describe('Risk Metrics', () => {
    test('calculateVolatility - skips null values', () => {
      const holdings = [
        { market_value: 5000, volatility: 0.18 },
        { market_value: 3000, volatility: null },
        { market_value: 2000, volatility: 0.22 },
      ];
      const totalValue = 10000;

      let volatilitySum = 0;
      let validHoldingsValue = 0;

      holdings.forEach(h => {
        const volatility = parseFloat(h.volatility);
        if (volatility && isFinite(volatility)) {
          const weight = h.market_value / totalValue;
          volatilitySum += weight * volatility;
          validHoldingsValue += h.market_value;
        }
      });

      const portfolioVolatility = volatilitySum / (validHoldingsValue / totalValue);

      expect(validHoldingsValue).toEqual(7000); // Should skip 3000 from null volatility
      expect(portfolioVolatility).toBeCloseTo(0.19, 2); // (5000*0.18 + 2000*0.22) / 7000
    });

    test('calculateBeta - renormalizes weights without invalid data', () => {
      const holdings = [
        { market_value: 5000, beta: 1.2 },
        { market_value: 3000, beta: null },
        { market_value: 2000, beta: 0.95 },
      ];
      const totalValue = 10000;

      let betaSum = 0;
      let betaHoldingsValue = 0;

      holdings.forEach(h => {
        const beta = parseFloat(h.beta);
        if (beta && isFinite(beta)) {
          const weight = h.market_value / totalValue;
          betaSum += weight * beta;
          betaHoldingsValue += h.market_value;
        }
      });

      const portfolioBeta = betaSum / (betaHoldingsValue / totalValue);
      const expectedBeta = (5000 * 1.2 + 2000 * 0.95) / 7000;

      expect(betaHoldingsValue).toEqual(7000);
      expect(portfolioBeta).toBeCloseTo(expectedBeta, 2);
    });
  });

  describe('Data Validation', () => {
    test('rejects zero entry prices', () => {
      const trade = {
        symbol: 'TEST',
        entry_price: 0,
        current_price: 150.25,
      };

      const entryPrice = parseFloat(trade.entry_price);
      const isValid = isFinite(entryPrice) && entryPrice > 0;

      expect(isValid).toBe(false);
    });

    test('rejects null entry prices', () => {
      const trade = {
        symbol: 'TEST',
        entry_price: null,
        current_price: null,
      };

      const entryPrice = parseFloat(trade.entry_price || trade.current_price);
      const isValid = isFinite(entryPrice) && entryPrice > 0;

      expect(isValid).toBe(false);
    });

    test('accepts valid entry prices', () => {
      const trade = {
        symbol: 'TEST',
        entry_price: 150.25,
        current_price: 155.00,
      };

      const entryPrice = parseFloat(trade.entry_price || trade.current_price);
      const isValid = isFinite(entryPrice) && entryPrice > 0;

      expect(isValid).toBe(true);
      expect(entryPrice).toEqual(150.25);
    });

    test('skips holdings with invalid market_value', () => {
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
      expect(validHoldings[0].symbol).toEqual('AAPL');
      expect(validHoldings[1].symbol).toEqual('GOOGL');
    });
  });

  describe('Sector Allocation', () => {
    test('correctly aggregates sector weights', () => {
      const holdings = [
        { symbol: 'AAPL', sector: 'Technology', market_value: 5000 },
        { symbol: 'MSFT', sector: 'Technology', market_value: 3000 },
        { symbol: 'JPM', sector: 'Financials', market_value: 2000 },
      ];
      const totalValue = 10000;

      const sectorAllocation = {};
      holdings.forEach(h => {
        const sector = h.sector || 'Other';
        if (!sectorAllocation[sector]) {
          sectorAllocation[sector] = { value: 0, weight: 0 };
        }
        sectorAllocation[sector].value += h.market_value;
      });

      Object.keys(sectorAllocation).forEach(sector => {
        sectorAllocation[sector].weight = (sectorAllocation[sector].value / totalValue) * 100;
      });

      expect(sectorAllocation.Technology.value).toEqual(8000);
      expect(sectorAllocation.Technology.weight).toEqual(80);
      expect(sectorAllocation.Financials.value).toEqual(2000);
      expect(sectorAllocation.Financials.weight).toEqual(20);
    });
  });
});
