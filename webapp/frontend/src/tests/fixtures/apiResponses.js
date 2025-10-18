/**
 * API Response Fixtures
 *
 * These fixtures match the actual database schema and API response structures.
 * Use these to ensure tests validate against realistic data.
 *
 * Each fixture is based on actual data structures returned by the backend API routes.
 */

// ============================================================================
// MARKET DATA ENDPOINTS
// ============================================================================

/**
 * GET /api/market/
 * Returns market overview with sentiment and breadth data
 */
export const marketOverviewResponse = {
  success: true,
  data: {
    // Market Status
    marketStatus: 'Open',

    // Market Indices
    indices: [
      {
        symbol: 'SPY',
        name: 'S&P 500',
        price: 450.25,
        change: 2.50,
        changePercent: 0.56,
        volume: 95_300_000,
        high_52w: 485.50,
        low_52w: 380.25,
      },
      {
        symbol: 'QQQ',
        name: 'Nasdaq-100',
        price: 380.75,
        change: -1.20,
        changePercent: -0.31,
        volume: 142_500_000,
        high_52w: 425.30,
        low_52w: 310.50,
      },
      {
        symbol: 'IWM',
        name: 'Russell 2000',
        price: 205.45,
        change: 1.15,
        changePercent: 0.56,
        volume: 32_100_000,
        high_52w: 215.80,
        low_52w: 165.20,
      },
    ],

    // Sector Performance
    sectors: [
      {
        sector: 'Technology',
        performance: 1.25,
        weight: 29.5,
        ytd_performance: 18.5,
      },
      {
        sector: 'Healthcare',
        performance: 0.85,
        weight: 13.2,
        ytd_performance: 12.3,
      },
      {
        sector: 'Financials',
        performance: -0.45,
        weight: 11.8,
        ytd_performance: 8.2,
      },
      {
        sector: 'Industrials',
        performance: 0.65,
        weight: 8.5,
        ytd_performance: 5.1,
      },
      {
        sector: 'Consumer Discretionary',
        performance: -0.15,
        weight: 8.2,
        ytd_performance: 3.2,
      },
      {
        sector: 'Consumer Staples',
        performance: 0.25,
        weight: 6.1,
        ytd_performance: 2.1,
      },
      {
        sector: 'Energy',
        performance: -1.25,
        weight: 4.2,
        ytd_performance: 15.3,
      },
      {
        sector: 'Utilities',
        performance: 0.05,
        weight: 3.2,
        ytd_performance: -2.1,
      },
      {
        sector: 'Real Estate',
        performance: 0.35,
        weight: 3.1,
        ytd_performance: 0.5,
      },
      {
        sector: 'Materials',
        performance: -0.55,
        weight: 2.5,
        ytd_performance: 4.8,
      },
      {
        sector: 'Communication Services',
        performance: 0.15,
        weight: 9.7,
        ytd_performance: 12.8,
      },
    ],

    // Market Movers (gainers/losers)
    movers: {
      gainers: [
        {
          symbol: 'NVDA',
          price: 142.35,
          change: 5.20,
          changePercent: 3.8,
          volume: 45_300_000,
          pe_ratio: 65.2,
        },
        {
          symbol: 'AAPL',
          price: 229.75,
          change: 3.45,
          changePercent: 1.5,
          volume: 48_200_000,
          pe_ratio: 32.5,
        },
        {
          symbol: 'MSFT',
          price: 431.50,
          change: 2.80,
          changePercent: 0.65,
          volume: 21_500_000,
          pe_ratio: 38.2,
        },
      ],
      losers: [
        {
          symbol: 'IBM',
          price: 198.25,
          change: -4.15,
          changePercent: -2.05,
          volume: 3_200_000,
          pe_ratio: 24.5,
        },
        {
          symbol: 'INTC',
          price: 31.45,
          change: -2.80,
          changePercent: -8.2,
          volume: 65_300_000,
          pe_ratio: 12.1,
        },
      ],
    },

    // Sentiment Indicators
    sentiment: {
      fear_greed: {
        value: 45,
        value_text: 'Neutral',
        date: '2025-10-18',
        change_from_prev: 2,
      },
      aaii: {
        bullish: 45.3,
        neutral: 28.2,
        bearish: 26.5,
        date: '2025-10-18',
      },
      naaim: {
        mean_exposure: 65.2,
        date: '2025-10-18',
      },
    },

    // Market Breadth
    breadth: {
      advancing: 1850,
      declining: 950,
      unchanged: 200,
      total_stocks: 3000,
      advance_decline_ratio: 1.95,
      advance_decline_line: 45250, // Cumulative AD line
      average_change_percent: 0.42,
      up_volume_percent: 58.5,
      down_volume_percent: 41.5,
    },

    // Market Cap Distribution
    market_cap: {
      total: 50_000_000_000_000,
      large_cap: 35_000_000_000_000, // > $10B
      mid_cap: 10_000_000_000_000, // $2B - $10B
      small_cap: 5_000_000_000_000, // < $2B
    },
  },
  timestamp: '2025-10-18T15:30:00Z',
};

// ============================================================================
// SENTIMENT HISTORY ENDPOINTS
// ============================================================================

/**
 * GET /api/market/sentiment-history
 * Historical sentiment data for charts
 */
export const sentimentHistoryResponse = {
  success: true,
  data: {
    fear_greed_history: [
      { date: '2025-10-18', value: 45, value_text: 'Neutral' },
      { date: '2025-10-17', value: 43, value_text: 'Neutral' },
      { date: '2025-10-16', value: 48, value_text: 'Neutral' },
      { date: '2025-10-15', value: 52, value_text: 'Greed' },
      { date: '2025-10-14', value: 55, value_text: 'Greed' },
    ],
    aaii_history: [
      { date: '2025-10-18', bullish: 45.3, neutral: 28.2, bearish: 26.5 },
      { date: '2025-10-11', bullish: 42.1, neutral: 30.2, bearish: 27.7 },
      { date: '2025-10-04', bullish: 40.5, neutral: 31.2, bearish: 28.3 },
    ],
    naaim_history: [
      { date: '2025-10-18', mean_exposure: 65.2 },
      { date: '2025-10-17', mean_exposure: 63.5 },
      { date: '2025-10-16', mean_exposure: 62.1 },
    ],
  },
  timestamp: '2025-10-18T15:30:00Z',
};

// ============================================================================
// SCORES ENDPOINT
// ============================================================================

/**
 * GET /api/scores?page=1&limit=50
 * Stock scores with all factor inputs
 */
export const scoresResponse = {
  success: true,
  data: {
    stocks: [
      {
        // Basic Info
        symbol: 'AAPL',
        company_name: 'Apple Inc.',
        sector: 'Technology',

        // Composite Scores (0-100)
        composite_score: 78.5,
        momentum_score: 82.1,
        trend_score: 75.3,
        value_score: 68.9,
        quality_score: 85.2,
        growth_score: 72.4,
        positioning_score: 71.8,
        sentiment_score: 62.1,
        risk_score: 69.5,

        // Price Data
        current_price: 229.75,
        price_change_1d: 1.25,
        price_change_5d: 3.45,
        price_change_30d: 8.12,
        volatility_30d: 22.1,

        // Technical Indicators
        rsi: 62.45,
        macd: 3.22,
        sma_20: 228.93,
        sma_50: 225.67,

        // Metrics
        pe_ratio: 32.5,
        market_cap: 3_200_000_000_000,
        volume_avg_30d: 48_200_000,

        // Momentum Components
        momentum_components: {
          short_term: 7.8, // 3M return %
          medium_term: 12.3, // 6M return %
          longer_term: 18.5, // 12M-1 return %
          relative_strength: 72,
          consistency: 0.88,
        },

        // Positioning Components
        positioning_components: {
          institutional_ownership: 58.5,
          insider_ownership: 0.7,
          short_percent_of_float: 2.1,
          short_ratio: 2.5,
          institution_count: 4850,
          acc_dist_rating: 0.72,
        },

        // Factor Inputs (JSONB columns)
        value_inputs: {
          stock_pe: 32.5,
          forward_pe: 28.2,
          stock_pb: 42.3,
          stock_ps: 18.5,
          stock_ev_ebitda: 24.1,
          pe_percentile_rank: 75,
          pb_percentile_rank: 82,
          ps_percentile_rank: 78,
          fcf_yield: 3.2,
          dividend_yield: 0.42,
        },

        quality_inputs: {
          return_on_equity_pct: 124.5,
          return_on_assets_pct: 42.3,
          gross_margin_pct: 47.8,
          operating_margin_pct: 32.1,
          fcf_to_net_income: 0.92,
          debt_to_equity: 0.42,
          current_ratio: 1.55,
          roe_percentile_rank: 92,
          roa_percentile_rank: 88,
        },

        growth_inputs: {
          revenue_growth_3y_cagr: 8.2,
          eps_growth_3y_cagr: 12.5,
          revenue_growth_yoy: 5.3,
          eps_growth_yoy: 9.8,
          fcf_growth_yoy: 15.3,
        },

        momentum_inputs: {
          momentum_12m_1: 18.5,
          momentum_6m: 12.3,
          momentum_3m: 7.8,
          price_vs_sma_50: 1.72,
          price_vs_sma_200: 4.25,
          volatility_12m: 24.3,
        },

        relative_strength_inputs: {
          rs_rating: 72,
          sector_relative_1m: 5.2,
          sector_relative_3m: 8.1,
          sector_relative_6m: 12.3,
          sector_percentile: 78,
          positive_months_12: 10,
        },

        risk_inputs: {
          volatility_12m_pct: 24.3,
          beta: 1.18,
          max_drawdown_52w_pct: -12.3,
          sharpe_ratio: 1.45,
        },

        last_updated: '2025-10-18T15:30:00Z',
        score_date: '2025-10-18',
      },
    ],
    pagination: {
      page: 1,
      limit: 50,
      total: 4800,
      hasMore: true,
    },
    summary: {
      totalStocks: 4800,
      averageScore: 62.3,
      topScore: 95.2,
      scoreRange: { min: 15.3, max: 95.2 },
    },
    timestamp: '2025-10-18T15:30:00Z',
  },
};

/**
 * GET /api/scores/:symbol
 * Detailed factor analysis for a single stock
 */
export const stockDetailScoresResponse = {
  success: true,
  data: {
    symbol: 'AAPL',
    composite_score: 78.5,
    last_updated: '2025-10-18T15:30:00Z',

    factors: {
      momentum: {
        score: 82.1,
        components: {
          short_term: 7.8,
          medium_term: 12.3,
          longer_term: 18.5,
          consistency: 0.88,
          relative_strength: 72,
        },
        inputs: {
          momentum_12m_1: 18.5,
          momentum_6m: 12.3,
          momentum_3m: 7.8,
          risk_adjusted_momentum: 0.68,
          price_vs_sma_50: 1.72,
          price_vs_sma_200: 4.25,
          volatility_12m: 24.3,
        },
      },

      value: {
        score: 68.9,
        inputs: {
          stock_pe: 32.5,
          forward_pe: 28.2,
          stock_pb: 42.3,
          stock_ps: 18.5,
          pe_percentile_rank: 75,
          pb_percentile_rank: 82,
          fcf_yield: 3.2,
          dividend_yield: 0.42,
          peg_ratio: 2.1,
          dcf_intrinsic_value: 245.30,
        },
      },

      quality: {
        score: 85.2,
        inputs: {
          return_on_equity_pct: 124.5,
          return_on_assets_pct: 42.3,
          gross_margin_pct: 47.8,
          operating_margin_pct: 32.1,
          fcf_to_net_income: 0.92,
          debt_to_equity: 0.42,
          current_ratio: 1.55,
          roe_percentile_rank: 92,
          roa_percentile_rank: 88,
        },
      },

      growth: {
        score: 72.4,
        inputs: {
          revenue_growth_3y_cagr: 8.2,
          eps_growth_3y_cagr: 12.5,
          revenue_growth_yoy: 5.3,
          eps_growth_yoy: 9.8,
          fcf_growth_yoy: 15.3,
          sustainable_growth_rate: 9.2,
          quarterly_growth_momentum: 2.1,
        },
      },

      relative_strength: {
        score: 71.2,
        inputs: {
          rs_rating: 72,
          sector_relative_1m: 5.2,
          sector_relative_3m: 8.1,
          sector_relative_6m: 12.3,
          sector_relative_12m: 18.5,
          sector_percentile: 78,
          positive_months_12: 10,
          timeframe_alignment: 0.85,
        },
      },

      positioning: {
        score: 71.8,
        components: {
          institutional_ownership: 58.5,
          insider_ownership: 0.7,
          short_percent_of_float: 2.1,
          institution_count: 4850,
          acc_dist_rating: 0.72,
        },
      },

      sentiment: {
        score: 62.1,
        components: {
          analyst_rating: 2.1, // 1-5 scale (1=buy, 5=sell)
          recommendation_trend: 'positive',
          news_sentiment: 'neutral',
        },
      },

      risk: {
        score: 69.5,
        inputs: {
          volatility_12m_pct: 24.3,
          volatility_risk_component: 18.5,
          max_drawdown_52w_pct: -12.3,
          beta: 1.18,
          sharpe_ratio: 1.45,
          sortino_ratio: 2.15,
        },
      },
    },

    performance: {
      priceChange1d: 1.25,
      priceChange5d: 3.45,
      priceChange30d: 8.12,
      priceChange52w: 28.5,
      volatility30d: 22.1,
      volatility52w: 24.3,
    },

    technical: {
      rsi: 62.45,
      macd: 3.22,
      sma20: 228.93,
      sma50: 225.67,
      sma200: 220.15,
    },

    company: {
      name: 'Apple Inc.',
      sector: 'Technology',
      industry: 'Consumer Electronics',
      pe_ratio: 32.5,
      market_cap: 3_200_000_000_000,
    },
  },
  timestamp: '2025-10-18T15:30:00Z',
};

// ============================================================================
// MARKET BREADTH ENDPOINT
// ============================================================================

/**
 * GET /api/market/breadth
 * Detailed market breadth data
 */
export const marketBreadthResponse = {
  success: true,
  data: {
    advancing: 1850,
    declining: 950,
    unchanged: 200,
    total_stocks: 3000,
    advance_decline_ratio: 1.95,
    advance_decline_line: 45250,
    up_volume_percent: 58.5,
    down_volume_percent: 41.5,
    new_highs: 245,
    new_lows: 18,
    breadth_momentum: 0.65, // Directional strength
    breadth_thrust: true, // Market in thrust position
    average_change_percent: 0.42,
    up_volume: 2_150_000_000,
    down_volume: 1_540_000_000,
  },
  timestamp: '2025-10-18T15:30:00Z',
};

// ============================================================================
// EXPORT ALL FIXTURES
// ============================================================================

export default {
  marketOverviewResponse,
  sentimentHistoryResponse,
  scoresResponse,
  stockDetailScoresResponse,
  marketBreadthResponse,
};
