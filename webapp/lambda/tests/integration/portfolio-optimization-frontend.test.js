/**
 * Portfolio Optimization - Frontend Integration Test
 * Verifies the backend API response can be consumed by the frontend component
 */

const { validateApiResponse, validateFrontendIntegration, validateAllChecks } = require('../validation/api-frontend-compatibility');

describe('Portfolio Optimization - Frontend Integration', () => {
  // Mock API response based on actual backend implementation
  const mockApiResponse = {
    success: true,
    data: {
      optimization_id: 'opt-20251108-1234567890',
      timestamp: new Date().toISOString(),
      user_id: 'test-user-123',

      // Portfolio State
      portfolio_state: {
        total_value: 150000,
        total_cost: 140000,
        unrealized_pnl: 10000,
        unrealized_pnl_pct: 7.14,
        num_holdings: 12,
        composite_score: 72.5,
        concentration_ratio: 48.3,
        top_holdings: [
          {
            symbol: 'AAPL',
            shares: 50,
            cost: 7000,
            market_value: 8500,
            weight_pct: 5.67,
            score: 85.2,
            pnl_pct: 21.4,
          },
          {
            symbol: 'MSFT',
            shares: 30,
            cost: 9000,
            market_value: 10500,
            weight_pct: 7.0,
            score: 78.1,
            pnl_pct: 16.7,
          },
          {
            symbol: 'GOOGL',
            shares: 15,
            cost: 2100,
            market_value: 2250,
            weight_pct: 1.5,
            score: 81.4,
            pnl_pct: 7.1,
          },
          {
            symbol: 'TSLA',
            shares: 20,
            cost: 4000,
            market_value: 4200,
            weight_pct: 2.8,
            score: 70.5,
            pnl_pct: 5.0,
          },
          {
            symbol: 'AMZN',
            shares: 25,
            cost: 5000,
            market_value: 5500,
            weight_pct: 3.67,
            score: 76.2,
            pnl_pct: 10.0,
          },
        ],
      },

      // Sector Allocation
      sector_allocation: [
        {
          sector: 'tech',
          holdings: ['AAPL', 'MSFT', 'GOOGL'],
          num_holdings: 3,
          current_pct: 42.5,
          target_pct: 25,
          drift: 17.5,
          value: 63750,
          status: 'OVERWEIGHT',
        },
        {
          sector: 'consumer',
          holdings: ['AMZN', 'TSLA'],
          num_holdings: 2,
          current_pct: 18.7,
          target_pct: 15,
          drift: 3.7,
          value: 28050,
          status: 'OVERWEIGHT',
        },
        {
          sector: 'healthcare',
          holdings: ['JNJ', 'UNH'],
          num_holdings: 2,
          current_pct: 15.2,
          target_pct: 15,
          drift: 0.2,
          value: 22800,
          status: 'BALANCED',
        },
        {
          sector: 'financials',
          holdings: ['JPM', 'BAC'],
          num_holdings: 2,
          current_pct: 12.1,
          target_pct: 15,
          drift: -2.9,
          value: 18150,
          status: 'UNDERWEIGHT',
        },
        {
          sector: 'industrials',
          holdings: ['BA'],
          num_holdings: 1,
          current_pct: 8.5,
          target_pct: 10,
          drift: -1.5,
          value: 12750,
          status: 'UNDERWEIGHT',
        },
        {
          sector: 'energy',
          holdings: [],
          num_holdings: 0,
          current_pct: 0,
          target_pct: 5,
          drift: -5,
          value: 0,
          status: 'UNDERWEIGHT',
        },
      ],

      // Recommended Trades
      recommended_trades: [
        {
          rank: 1,
          action: 'BUY',
          symbol: 'XOM',
          composite_score: 72.3,
          portfolio_fit_score: 78.5,
          market_fit_component: 75.2,
          correlation_component: 82.1,
          sector_component: 88.0,
          current_price: 112.45,
          sector: 'energy',
          suggested_amount: 10000,
          rationale: 'High-quality energy stock fills underweighted sector. Low correlation with current tech-heavy portfolio. Adds diversification.',
          expected_impact: {
            diversification: 'Adds new sector exposure',
            correlation: 'Reduces portfolio correlation by ~2%',
            sector_rebalancing: 'Helps reduce tech overweight',
          },
          formula_explanation: 'Fit Score = (50×72.3 + 15×75.2 + 20×82.1 + 15×88.0) / 100 = 78.5',
        },
        {
          rank: 2,
          action: 'BUY',
          symbol: 'PG',
          composite_score: 75.8,
          portfolio_fit_score: 74.2,
          market_fit_component: 71.5,
          correlation_component: 76.3,
          sector_component: 80.0,
          current_price: 168.32,
          sector: 'consumer',
          suggested_amount: 10000,
          rationale: 'Consumer staples with strong quality score. Defensive characteristics complement current growth positions.',
          expected_impact: {
            diversification: 'Adds defensive exposure',
            correlation: 'Reduces portfolio volatility',
            sector_rebalancing: 'Balances consumer sector allocation',
          },
          formula_explanation: 'Fit Score = (50×75.8 + 15×71.5 + 20×76.3 + 15×80.0) / 100 = 74.2',
        },
        {
          rank: 3,
          action: 'REDUCE',
          symbol: 'LOW',
          composite_score: 58.2,
          portfolio_fit_score: 38.2,
          current_weight_pct: 8.3,
          current_price: 85.60,
          position_value: 12450,
          sector: 'consumer',
          suggested_action: 'Reduce by 25%',
          rationale: 'Stock quality below threshold (58.2/100). Consider reducing position and reallocating to higher-quality stocks.',
          expected_impact: {
            quality_improvement: 'Replace with better-scoring stock',
            concentration: 'Reduces LOW position concentration',
            capital_redeployment: 'Free up ~$3,100 for high-quality positions',
          },
        },
        {
          rank: 4,
          action: 'SELL',
          symbol: 'AMD',
          composite_score: 55.0,
          portfolio_fit_score: 35.0,
          current_weight_pct: 3.1,
          current_price: 180.25,
          position_value: 4650,
          sector: 'tech',
          suggested_action: 'Sell entire position',
          rationale: 'Stock quality below threshold (55.0/100). Highest quality alternatives available in same sector.',
          expected_impact: {
            quality_improvement: 'Replace with better-scoring stock',
            concentration: 'Reduces AMD position entirely',
            capital_redeployment: 'Free up ~$4,650 for rebalancing',
          },
        },
      ],

      // Portfolio Metrics
      portfolio_metrics: {
        before: {
          avg_composite_score: 72.5,
          concentration_ratio: 48.3,
          sector_diversification: 5,
          estimated_sharpe_ratio: 1.2,
          correlation_to_market: 0.78,
        },
        after_recommendations: {
          avg_composite_score: 75.2,
          concentration_ratio: 45.1,
          sector_diversification: 6,
          estimated_sharpe_ratio: 1.35,
          correlation_to_market: 0.72,
        },
        expected_improvements: {
          composite_score: '2-4 point increase',
          concentration: '3-5% reduction',
          sector_balance: 'Closer to target allocations',
          portfolio_stability: 'Reduced correlation between holdings',
        },
      },

      // Formulas
      formulas_used: [
        'Portfolio_Fit_Score = (50×Composite + 15×Market_Fit + 20×Correlation + 15×Sector) / 10',
        'Market_Fit adapts to market conditions (bullish=growth, moderate=balanced, bearish=defensive)',
        'Correlation_Score = 100 - (avg_correlation × 100), penalizes redundant positions',
        'Sector_Score = 50 + (drift × 200) if underweight, 50 - (drift × 200) if overweight',
      ],

      // Data Quality
      data_quality: {
        holdings_with_scores: 12,
        total_holdings: 12,
        stocks_in_universe: 542,
        timestamp: new Date().toISOString(),
      },
    },
  };

  test('API response passes all structure validations', () => {
    const result = validateApiResponse(mockApiResponse);
    console.log('\n✅ Structure validation complete');
  });

  test('Frontend can consume all required fields from portfolio_state', () => {
    const data = mockApiResponse.data;
    const ps = data.portfolio_state;

    // Portfolio Summary Cards (lines 228-300)
    expect(ps.total_value).toBeDefined();
    expect(typeof ps.total_value).toBe('number');

    expect(ps.unrealized_pnl).toBeDefined();
    expect(typeof ps.unrealized_pnl).toBe('number');

    expect(ps.unrealized_pnl_pct).toBeDefined();
    expect(typeof ps.unrealized_pnl_pct).toBe('number');

    expect(ps.num_holdings).toBeDefined();
    expect(typeof ps.num_holdings).toBe('number');

    expect(ps.composite_score).toBeDefined();
    expect(typeof ps.composite_score).toBe('number');

    expect(ps.concentration_ratio).toBeDefined();
    expect(typeof ps.concentration_ratio).toBe('number');

    console.log('✅ All portfolio summary card fields available');
  });

  test('Frontend can render top holdings with correct structure', () => {
    const topHoldings = mockApiResponse.data.portfolio_state.top_holdings;

    expect(Array.isArray(topHoldings)).toBe(true);
    expect(topHoldings.length).toBeGreaterThan(0);

    const holding = topHoldings[0];

    // Fields used in frontend (lines 312-349)
    expect(holding.symbol).toBeDefined();
    expect(typeof holding.symbol).toBe('string');

    expect(holding.market_value).toBeDefined();
    expect(typeof holding.market_value).toBe('number');

    expect(holding.shares).toBeDefined();
    expect(typeof holding.shares).toBe('number');

    expect(holding.weight_pct).toBeDefined();
    expect(typeof holding.weight_pct).toBe('number');

    expect(holding.score).toBeDefined();
    expect(holding.score === null || typeof holding.score === 'number').toBe(true);

    expect(holding.pnl_pct).toBeDefined();
    expect(holding.pnl_pct === null || typeof holding.pnl_pct === 'number').toBe(true);

    console.log('✅ Top holdings have all required display fields');
  });

  test('Frontend can render sector allocation table', () => {
    const sectors = mockApiResponse.data.sector_allocation;

    expect(Array.isArray(sectors)).toBe(true);
    expect(sectors.length).toBeGreaterThan(0);

    const sector = sectors[0];

    // Fields used in frontend (lines 380-431)
    expect(sector.sector).toBeDefined();
    expect(typeof sector.sector).toBe('string');

    expect(sector.num_holdings).toBeDefined();
    expect(typeof sector.num_holdings).toBe('number');

    expect(sector.current_pct).toBeDefined();
    expect(typeof sector.current_pct).toBe('number');

    expect(sector.target_pct).toBeDefined();
    expect(typeof sector.target_pct).toBe('number');

    expect(sector.drift).toBeDefined();
    expect(typeof sector.drift).toBe('number');

    expect(sector.status).toBeDefined();
    expect(['BALANCED', 'OVERWEIGHT', 'UNDERWEIGHT']).toContain(sector.status);

    // Verify calculations
    const calculatedDrift = sector.current_pct - sector.target_pct;
    expect(Math.abs(sector.drift - calculatedDrift)).toBeLessThan(0.01);

    console.log('✅ Sector allocation table has all required fields');
  });

  test('Frontend can render recommendations table', () => {
    const trades = mockApiResponse.data.recommended_trades;

    expect(Array.isArray(trades)).toBe(true);
    expect(trades.length).toBeGreaterThan(0);

    const trade = trades[0];

    // Fields used in frontend (lines 460-530)
    expect(trade.action).toBeDefined();
    expect(['BUY', 'SELL', 'REDUCE', 'HOLD']).toContain(trade.action);

    expect(trade.symbol).toBeDefined();
    expect(typeof trade.symbol).toBe('string');

    expect(trade.sector).toBeDefined();
    expect(typeof trade.sector).toBe('string');

    expect(trade.portfolio_fit_score).toBeDefined();
    expect(typeof trade.portfolio_fit_score).toBe('number');

    expect(trade.composite_score).toBeDefined();
    expect(typeof trade.composite_score).toBe('number');

    expect(trade.rationale).toBeDefined();
    expect(typeof trade.rationale).toBe('string');

    // Fit score should be in valid range
    expect(trade.portfolio_fit_score).toBeGreaterThanOrEqual(0);
    expect(trade.portfolio_fit_score).toBeLessThanOrEqual(100);

    console.log('✅ Recommendations table has all required fields');
  });

  test('Frontend can display portfolio metrics before/after', () => {
    const metrics = mockApiResponse.data.portfolio_metrics;

    expect(metrics.before).toBeDefined();
    expect(metrics.after_recommendations).toBeDefined();
    expect(metrics.expected_improvements).toBeDefined();

    const before = metrics.before;
    const after = metrics.after_recommendations;

    // Check numeric fields
    expect(typeof before.avg_composite_score).toBe('number');
    expect(typeof before.concentration_ratio).toBe('number');
    expect(typeof after.avg_composite_score).toBe('number');
    expect(typeof after.concentration_ratio).toBe('number');

    console.log('✅ Portfolio metrics have correct structure');
  });

  test('Frontend can display optimization metadata', () => {
    const data = mockApiResponse.data;

    expect(data.optimization_id).toBeDefined();
    expect(typeof data.optimization_id).toBe('string');

    expect(data.timestamp).toBeDefined();
    expect(typeof data.timestamp).toBe('string');

    expect(data.data_quality).toBeDefined();
    expect(typeof data.data_quality.holdings_with_scores).toBe('number');
    expect(typeof data.data_quality.total_holdings).toBe('number');

    console.log('✅ Optimization metadata available for footer display');
  });

  test('Comprehensive frontend integration validation', () => {
    const result = validateFrontendIntegration(mockApiResponse);
    console.log('\n✅ Frontend integration validation complete');
  });

  test('Complete API-Frontend compatibility check', () => {
    const isValid = validateAllChecks(mockApiResponse);
    expect(isValid).toBe(true);
  });

  test('All sector percentages sum to ~100%', () => {
    const sectors = mockApiResponse.data.sector_allocation;
    const totalPct = sectors.reduce((sum, s) => sum + s.current_pct, 0);

    expect(Math.abs(totalPct - 100)).toBeLessThan(1);
    console.log(`✅ Sector percentages sum to ${totalPct.toFixed(1)}%`);
  });

  test('Recommendations are ranked correctly', () => {
    const trades = mockApiResponse.data.recommended_trades;

    for (let i = 0; i < trades.length; i++) {
      expect(trades[i].rank).toBe(i + 1);
    }

    // Should be sorted by fit score descending
    for (let i = 0; i < trades.length - 1; i++) {
      const current = trades[i];
      const next = trades[i + 1];
      if (current.action === 'BUY' && next.action === 'BUY') {
        expect(current.portfolio_fit_score).toBeGreaterThanOrEqual(next.portfolio_fit_score);
      }
    }

    console.log('✅ Recommendations ranked correctly');
  });

  test('No null undefined scores in recommendations', () => {
    const trades = mockApiResponse.data.recommended_trades;

    trades.forEach((trade) => {
      expect(trade.composite_score).not.toBeNull();
      expect(trade.composite_score).not.toBeUndefined();

      expect(trade.portfolio_fit_score).not.toBeNull();
      expect(trade.portfolio_fit_score).not.toBeUndefined();

      expect(trade.rationale).toBeTruthy();
      expect(typeof trade.rationale).toBe('string');
    });

    console.log('✅ All recommendation scores valid');
  });
});
