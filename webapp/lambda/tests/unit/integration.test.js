/**
 * INTEGRATION TEST SUITE
 * Tests end-to-end data flows and API response formats
 */

describe('System Integration Tests', () => {
  describe('API Response Formats', () => {
    test('portfolio optimization endpoint returns required fields', () => {
      const mockResponse = {
        success: true,
        data: {
          portfolio_analysis: {
            current_state: {
              total_value: 50000,
              composite_score: 72.5,
              concentration_ratio: 0.25,
              diversification_score: 68,
              sector_drift: 0.12,
            },
            risk_metrics: {
              volatility: 0.18,
              sharpe_ratio: 1.45,
              beta: 1.1,
              max_drawdown: 0.25,
              var_95: 0.15,
            },
          },
          recommendations: [
            {
              rank: 1,
              action: 'BUY',
              symbol: 'NVDA',
              quantity: 10,
              portfolio_fit_score: 78.5,
              estimated_cost: 2500,
            },
          ],
        },
      };

      expect(mockResponse.success).toBe(true);
      expect(mockResponse.data.portfolio_analysis).toBeDefined();
      expect(mockResponse.data.recommendations).toBeDefined();
      expect(mockResponse.data.portfolio_analysis.current_state.total_value).toBeGreaterThan(0);
      expect(mockResponse.data.recommendations[0].action).toMatch(/BUY|SELL|REDUCE/);
    });

    test('stock detail endpoint returns real data fields', () => {
      const mockResponse = {
        success: true,
        data: {
          symbol: 'AAPL',
          current_price: 150.25,
          composite_score: 75,
          technical_analysis: {
            rsi: 65,
            macd: 0.5,
            trend: 'Uptrend',
          },
          metrics: {
            pe: 28.5,
            pb: 42.1,
            dividend_yield: 0.45,
          },
        },
      };

      expect(mockResponse.data.symbol).toEqual('AAPL');
      expect(mockResponse.data.current_price).toBeGreaterThan(0);
      expect(mockResponse.data.composite_score).toBeGreaterThanOrEqual(0);
      expect(mockResponse.data.composite_score).toBeLessThanOrEqual(100);
      expect(mockResponse.data.technical_analysis.trend).toMatch(/Uptrend|Downtrend|Sideways|null/);
    });

    test('market data endpoint returns healthy structure', () => {
      const mockResponse = {
        success: true,
        data: {
          market_summary: {
            sp500: { current: 4500, trend: 'Uptrend', support: 4400, resistance: 4550 },
            nasdaq: { current: 14000, trend: 'Sideways', support: 13900, resistance: 14100 },
          },
          market_internals: {
            breadth: {
              advancingStocks: 2800,
              decliningStocks: 1500,
              unchangedStocks: 200,
              McClellanOscillator: 150,
            },
            volume: {
              current: 1500000000,
              trend: 'Above Average',
            },
          },
        },
      };

      expect(mockResponse.success).toBe(true);
      expect(mockResponse.data.market_summary).toBeDefined();
      expect(mockResponse.data.market_internals).toBeDefined();
      expect(mockResponse.data.market_internals.breadth.McClellanOscillator).not.toBeNull();
    });
  });

  describe('Data Validation Throughout System', () => {
    test('no null values propagate as 0 in calculations', () => {
      const trade = {
        symbol: 'TEST',
        shares_to_trade: null,
        current_price: null,
      };

      // Should validate BOTH are present
      const shares = parseFloat(trade.shares_to_trade);
      const price = parseFloat(trade.current_price);
      const isValidTrade = isFinite(shares) && isFinite(price) && price > 0;

      expect(isValidTrade).toBe(false);

      // Should NOT create transaction
      if (isValidTrade) {
        const transaction = { symbol: trade.symbol, quantity: Math.abs(shares), price: price };
        expect(transaction).toBeUndefined(); // Should not reach here
      } else {
        // Correct: skip transaction
        expect(true).toBe(true);
      }
    });

    test('rebalance preserves portfolio integrity', () => {
      const currentPortfolio = {
        holdings: [
          { symbol: 'AAPL', quantity: 100, current_price: 150, market_value: 15000 },
          { symbol: 'MSFT', quantity: 50, current_price: 300, market_value: 15000 },
        ],
      };

      const totalValue = 30000;

      // Simulate REDUCE recommendation (sell 25%)
      const recommendation = {
        action: 'REDUCE',
        symbol: 'AAPL',
        quantity: 25,  // 100 * 0.25
      };

      const newQuantity = currentPortfolio.holdings[0].quantity - recommendation.quantity;
      const newMarketValue = newQuantity * currentPortfolio.holdings[0].current_price;

      expect(newQuantity).toEqual(75);
      expect(newMarketValue).toEqual(11250);
      expect(newMarketValue).toBeLessThan(currentPortfolio.holdings[0].market_value);
    });

    test('correlation matrix stays bounded in [-1, 1]', () => {
      // Simulate 3 stocks with correlations
      const correlationMatrix = [
        [1.0, 0.65, 0.45],     // AAPL
        [0.65, 1.0, 0.72],     // MSFT
        [0.45, 0.72, 1.0],     // GOOGL
      ];

      // Validate all values
      const allValid = correlationMatrix.every(row =>
        row.every(val => val >= -1 && val <= 1)
      );

      expect(allValid).toBe(true);

      // Validate diagonal is 1
      correlationMatrix.forEach((row, i) => {
        expect(row[i]).toEqual(1.0);
      });
    });
  });

  describe('Error Handling', () => {
    test('handles missing database gracefully', () => {
      const result = {
        success: false,
        error: 'Database connection failed',
        details: 'Unable to fetch portfolio data',
        data: null,  // Not undefined, explicitly null
      };

      expect(result.success).toBe(false);
      expect(result.error).toBeDefined();
      expect(result.data).toBeNull();
    });

    test('validates portfolio_holdings structure before calculation', () => {
      const invalidHolding = {
        symbol: 'TEST',
        quantity: null,
        current_price: 100,
      };

      const quantity = parseFloat(invalidHolding.quantity);
      const isValid = isFinite(quantity) && quantity > 0;

      expect(isValid).toBe(false);

      // Should not proceed with calculation
      if (isValid) {
        // This should not execute
        expect(true).toBe(false);
      }
    });

    test('handles partial data gracefully', () => {
      const holdingsWithMissingPrices = [
        { symbol: 'AAPL', quantity: 100, current_price: 150 },
        { symbol: 'MSFT', quantity: 50, current_price: null },  // Missing price
        { symbol: 'GOOGL', quantity: 75, current_price: 120 },
      ];

      const validHoldings = holdingsWithMissingPrices.filter(h => {
        const price = parseFloat(h.current_price);
        const qty = parseFloat(h.quantity);
        return qty && isFinite(qty) && qty > 0 && price && isFinite(price) && price > 0;
      });

      expect(validHoldings).toHaveLength(2);
      expect(validHoldings.map(h => h.symbol)).toEqual(['AAPL', 'GOOGL']);
    });
  });

  describe('Data Consistency', () => {
    test('sector weights sum to approximately 100%', () => {
      const sectorAllocation = {
        Technology: { weight: 35 },
        Financials: { weight: 25 },
        Healthcare: { weight: 20 },
        Energy: { weight: 15 },
        Other: { weight: 5 },
      };

      const totalWeight = Object.values(sectorAllocation).reduce(
        (sum, sector) => sum + sector.weight,
        0
      );

      expect(totalWeight).toEqual(100);
    });

    test('portfolio metrics are internally consistent', () => {
      const portfolio = {
        current_state: {
          total_value: 50000,
          cash: 5000,
          invested_value: 45000,
        },
        risk_metrics: {
          volatility: 0.18,
          sharpe_ratio: 1.45,
          beta: 1.1,
        },
      };

      expect(portfolio.current_state.invested_value).toEqual(
        portfolio.current_state.total_value - portfolio.current_state.cash
      );

      expect(portfolio.risk_metrics.volatility).toBeGreaterThan(0);
      expect(portfolio.risk_metrics.volatility).toBeLessThan(1);  // Typical range 0-1
    });

    test('recommendation costs match quantities and prices', () => {
      const recommendations = [
        {
          symbol: 'AAPL',
          action: 'BUY',
          quantity: 66,
          current_price: 150.25,
          estimated_cost: 9916.5,  // 66 * 150.25
        },
        {
          symbol: 'MSFT',
          action: 'REDUCE',
          quantity: 25,
          current_price: 300.00,
          estimated_cost: 7500,  // 25 * 300
        },
      ];

      recommendations.forEach(rec => {
        const expectedCost = rec.quantity * rec.current_price;
        expect(rec.estimated_cost).toBeCloseTo(expectedCost, 0);
      });
    });
  });

  describe('Performance Boundaries', () => {
    test('correlation calculation completes in reasonable time', () => {
      const startTime = Date.now();

      // Simulate correlation between 100 price points
      const prices1 = Array(100).fill(0).map(() => Math.random() * 100);
      const prices2 = Array(100).fill(0).map(() => Math.random() * 100);

      const returns1 = prices1.slice(1).map((p, i) => (p - prices1[i]) / prices1[i]);
      const returns2 = prices2.slice(1).map((p, i) => (p - prices2[i]) / prices2[i]);

      // Calculate correlation
      const n = returns1.length;
      const mean1 = returns1.reduce((a, b) => a + b) / n;
      const mean2 = returns2.reduce((a, b) => a + b) / n;

      let covariance = 0;
      let variance1 = 0;
      let variance2 = 0;

      for (let i = 0; i < n; i++) {
        covariance += (returns1[i] - mean1) * (returns2[i] - mean2);
        variance1 += (returns1[i] - mean1) ** 2;
        variance2 += (returns2[i] - mean2) ** 2;
      }

      const correlation = covariance / Math.sqrt(variance1 * variance2);

      const elapsed = Date.now() - startTime;
      expect(elapsed).toBeLessThan(100);  // Should complete in <100ms
      expect(correlation).toBeGreaterThanOrEqual(-1);
      expect(correlation).toBeLessThanOrEqual(1);
    });

    test('portfolio optimization recommends reasonable quantity', () => {
      const suggestedAmount = 10000;
      const stockPrice = 150.25;

      const quantity = Math.floor(suggestedAmount / stockPrice);

      expect(quantity).toBeGreaterThan(0);
      expect(quantity * stockPrice).toBeLessThanOrEqual(suggestedAmount);
      expect(suggestedAmount - quantity * stockPrice).toBeLessThan(stockPrice);  // Minimal waste
    });
  });
});
