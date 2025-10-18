/**
 * Database Schema Definitions
 *
 * This file documents the complete database schema that loaders populate.
 * All test fixtures and API responses should conform to these definitions.
 *
 * Source of Truth: Python loaders in /home/stocks/algo/load*.py
 */

// ============================================================================
// PRICE & TECHNICAL DATA
// ============================================================================

/**
 * price_daily table
 * Source: loadpricedaily.py
 * Contains daily OHLCV data from yfinance
 */
const priceDaily = {
  symbol: 'AAPL',
  date: '2025-10-18',
  open: 228.50,
  high: 230.25,
  low: 228.00,
  close: 229.75,
  adj_close: 229.75,
  volume: 52_300_000,
  dividends: 0.00,
  splits: 0,
};

/**
 * technical_data_daily table
 * Source: loadtechnicalsdaily.py
 * Contains technical indicators computed daily
 */
const technicalDaily = {
  symbol: 'AAPL',
  date: '2025-10-18',
  rsi: 62.45,
  macd: 3.22,
  macd_hist: 0.18,
  sma_20: 228.93,
  sma_50: 225.67,
  atr: 2.15,
  mom: 5.82,
  roc: 2.54, // Rate of Change
  roc_10d: 1.85,
  roc_20d: 3.12,
  roc_60d: 8.45,
  mansfield_rs: 72, // Relative Strength Rating
};

/**
 * buy_sell_signal_daily table
 * Source: loadbuyselldaily.py
 * Trading signals generated from technical patterns
 */
const buySignalDaily = {
  symbol: 'AAPL',
  date: '2025-10-18',
  signal_type: 'BUY', // or 'SELL', 'NEUTRAL'
  strength: 0.75, // 0-1 confidence score
};

// ============================================================================
// FUNDAMENTAL DATA
// ============================================================================

/**
 * earnings_history table
 * Source: loadearningshistory.py
 * Historical earnings data (actual vs estimates)
 */
const earningsHistory = {
  symbol: 'AAPL',
  quarter: '2025-09-30',
  eps_actual: 2.18,
  eps_estimate: 2.15,
  eps_difference: 0.03,
  surprise_percent: 1.39, // (actual - estimate) / estimate * 100
  fiscal_year: 2025,
  fiscal_quarter: 4,
  fetched_at: new Date().toISOString(),
};

/**
 * earnings_estimate table
 * Source: loadearningsestimate.py
 * Forward-looking earnings estimates
 */
const earningsEstimate = {
  symbol: 'AAPL',
  period: '2025-12-31',
  avg_estimate: 2.45,
  low_estimate: 2.30,
  high_estimate: 2.60,
  year_ago_eps: 2.05,
  number_of_analysts: 28,
  growth: 19.5,
  fetched_at: new Date().toISOString(),
};

// ============================================================================
// QUALITY METRICS
// ============================================================================

/**
 * quality_metrics table
 * Source: loadqualitymetrics.py
 * Fundamental quality scores
 */
const qualityMetrics = {
  symbol: 'AAPL',
  date: '2025-10-18',
  return_on_equity_pct: 124.5,
  return_on_assets_pct: 42.3,
  gross_margin_pct: 47.8,
  operating_margin_pct: 32.1,
  profit_margin_pct: 28.5,
  fcf_to_net_income: 0.92,
  operating_cf_to_net_income: 1.15,
  debt_to_equity: 0.42,
  current_ratio: 1.55,
  quick_ratio: 1.35,
  earnings_surprise_avg: 1.2, // Average % surprise over last 4 quarters
  eps_growth_stability: 0.85, // Measure of consistency in growth
  payout_ratio: 0.14,
};

/**
 * growth_metrics table
 * Source: loadgrowthmetrics.py
 * Growth rates and trends
 */
const growthMetrics = {
  symbol: 'AAPL',
  date: '2025-10-18',
  revenue_growth_3y_cagr: 8.2,
  eps_growth_3y_cagr: 12.5,
  operating_income_growth_yoy: 9.8,
  roe_trend: 3.5, // YoY change in ROE
  sustainable_growth_rate: 9.2, // ROE * retention rate
  fcf_growth_yoy: 15.3,
  net_income_growth_yoy: 11.2,
  gross_margin_trend: -0.3, // YoY change in margin
  operating_margin_trend: 1.2,
  net_margin_trend: 0.8,
  quarterly_growth_momentum: 2.1, // Most recent quarter vs prior quarter
  asset_growth_yoy: 3.4,
};

/**
 * momentum_metrics table
 * Source: loadmomentummetrics.py
 * Dual momentum and price correlation metrics
 */
const momentumMetrics = {
  symbol: 'AAPL',
  date: '2025-10-18',
  momentum_12m_1: 18.5, // 12-month return excluding last month (%)
  momentum_6m: 12.3, // 6-month return (%)
  momentum_3m: 7.8, // 3-month return (%)
  risk_adjusted_momentum: 0.68, // Momentum / volatility
  price_vs_sma_50: 1.72, // (price - SMA50) / SMA50 * 100
  price_vs_sma_200: 4.25, // (price - SMA200) / SMA200 * 100
  price_vs_52w_high: -2.15, // (price - 52w high) / 52w high * 100
  high_52w: 234.50, // 52-week high price
  sma_50: 225.67,
  sma_200: 220.15,
  volatility_12m: 24.3, // Annualized volatility (%)
};

/**
 * risk_metrics table
 * Source: loadriskmetrics.py
 * Risk measurements
 */
const riskMetrics = {
  symbol: 'AAPL',
  date: '2025-10-18',
  volatility_12m_pct: 24.3,
  volatility_risk_component: 18.5, // Systemic risk portion of volatility
  max_drawdown_52w_pct: -12.3, // Worst peak-to-trough decline in 52 weeks
  beta: 1.18, // Market sensitivity (1.0 = market risk)
};

/**
 * positioning_metrics table
 * Source: loadpositioning.py
 * Institutional positioning data
 */
const positioningMetrics = {
  symbol: 'AAPL',
  date: '2025-10-18',
  institutional_ownership: 58.5, // % of shares held by institutions
  insider_ownership: 0.7, // % of shares held by insiders
  short_percent_of_float: 2.1, // % of float that is short
  short_ratio: 2.5, // Days to cover at recent volume
  institution_count: 4850, // Number of institutional holders
};

// ============================================================================
// SCORING & COMPOSITE METRICS
// ============================================================================

/**
 * stock_scores table
 * Source: loadstockscores.py (primary scoring hub)
 * Composite scores and all factor breakdowns
 *
 * NOTE: This is the MOST COMPLEX table - it aggregates data from 12+ source tables
 */
const stockScores = {
  // Primary IDs
  symbol: 'AAPL',
  score_date: '2025-10-18',
  last_updated: new Date().toISOString(),

  // ===== COMPOSITE SCORES (weight-based aggregates) =====
  composite_score: 78.5, // 0-100 overall rating
  momentum_score: 82.1, // 21% weight
  trend_score: 75.3, // 15% weight
  value_score: 68.9, // 15% weight
  quality_score: 85.2, // 15% weight
  growth_score: 72.4, // 19% weight
  positioning_score: 71.8, // 10% weight
  sentiment_score: 62.1, // 5% weight
  risk_score: 69.5, // Derived from risk_metrics

  // ===== MOMENTUM COMPONENTS (detailed breakdown) =====
  momentum_short_term: 7.8, // 3-month return (%)
  momentum_medium_term: 12.3, // 6-month return (%)
  momentum_long_term: 18.5, // 12-month return excluding last month (%)
  momentum_consistency: 0.88, // Correlation of returns across timeframes
  momentum_relative_strength: 72, // Mansfield RS vs sector

  // ===== TECHNICAL INDICATORS (from technical_data_daily) =====
  rsi: 62.45,
  macd: 3.22,
  sma_20: 228.93,
  sma_50: 225.67,
  atr: 2.15,

  // ===== PRICE & RETURNS (from price_daily + calculations) =====
  current_price: 229.75,
  price_change_1d: 1.25,
  price_change_5d: 3.45,
  price_change_30d: 8.12,

  // ===== VOLUME & VOLATILITY =====
  volume_avg_30d: 48_200_000,
  volatility_30d: 22.1, // 30-day annualized volatility

  // ===== MARKET CONTEXT =====
  market_cap: 3_200_000_000_000, // in dollars
  pe_ratio: 32.5,

  // ===== ROC INDICATORS (Rate of Change momentum) =====
  roc_10d: 1.85,
  roc_20d: 3.12,
  roc_60d: 8.45,
  roc_120d: 15.2,
  roc_252d: 18.5,

  // ===== POSITIONING & ACCUMULATION =====
  acc_dist_rating: 0.72, // Accumulation/Distribution indicator normalized 0-1

  // ===== FACTOR INPUTS (JSONB columns in actual database) =====
  value_inputs: {
    // From loadvaluemetrics.py
    stock_pe: 32.5,
    forward_pe: 28.2,
    stock_pb: 42.3,
    stock_ps: 18.5,
    stock_ev_ebitda: 24.1,
    dividend_yield: 0.42,
    fcf_yield: 3.2,
    peg_ratio: 2.1,
    dcf_intrinsic_value: 245.30,
    dcf_discount_pct: 6.7,
    // Relative to market
    market_pe: 22.5,
    sector_pe: 28.0,
    pe_relative: 1.45, // stock_pe / market_pe
    // Percentile ranks (0-100, crucial for value scoring)
    pe_percentile_rank: 75, // Higher = more expensive
    pb_percentile_rank: 82,
    ps_percentile_rank: 78,
    peg_percentile_rank: 68,
    fcf_yield_percentile_rank: 35,
    dividend_yield_percentile_rank: 42,
  },

  quality_inputs: {
    // From quality_metrics table
    return_on_equity_pct: 124.5,
    return_on_assets_pct: 42.3,
    gross_margin_pct: 47.8,
    operating_margin_pct: 32.1,
    profit_margin_pct: 28.5,
    fcf_to_net_income: 0.92,
    debt_to_equity: 0.42,
    current_ratio: 1.55,
    quick_ratio: 1.35,
    earnings_surprise_avg: 1.2,
    eps_growth_stability: 0.85,
    payout_ratio: 0.14,
    // Percentile ranks
    roe_percentile_rank: 92,
    roa_percentile_rank: 88,
    margin_percentile_rank: 85,
    fcf_percentile_rank: 78,
  },

  growth_inputs: {
    // From growth_metrics table
    revenue_growth_3y_cagr: 8.2,
    eps_growth_3y_cagr: 12.5,
    operating_income_growth_yoy: 9.8,
    fcf_growth_yoy: 15.3,
    net_income_growth_yoy: 11.2,
    roe_trend: 3.5,
    gross_margin_trend: -0.3,
    operating_margin_trend: 1.2,
    net_margin_trend: 0.8,
    quarterly_growth_momentum: 2.1,
    asset_growth_yoy: 3.4,
  },

  momentum_inputs: {
    // From momentum_metrics table
    momentum_12m_1: 18.5,
    momentum_6m: 12.3,
    momentum_3m: 7.8,
    risk_adjusted_momentum: 0.68,
    price_vs_sma_50: 1.72,
    price_vs_sma_200: 4.25,
    price_vs_52w_high: -2.15,
    volatility_12m: 24.3,
  },

  relative_strength_inputs: {
    // From relative_strength_metrics table (if populated)
    rs_rating: 72, // 0-99 Mansfield RS
    sector_relative_1m: 5.2,
    sector_relative_3m: 8.1,
    sector_relative_6m: 12.3,
    sector_relative_12m: 18.5,
    sector_percentile: 78, // Percentile vs sector
    rs_momentum_4w: 3.2,
    rs_momentum_13w: 7.8,
    positive_months_12: 10, // of last 12 months
    timeframe_alignment: 0.85, // Consistency across timeframes
    relative_strength_score: 75,
  },

  risk_inputs: {
    // From risk_metrics table
    volatility_12m_pct: 24.3,
    volatility_risk_component: 18.5,
    max_drawdown_52w_pct: -12.3,
    beta: 1.18,
    // Derived calculations
    sharpe_ratio: 1.45, // Risk-adjusted return
    sortino_ratio: 2.15, // Risk-adjusted return (downside only)
  },
};

// ============================================================================
// REFERENCE DATA
// ============================================================================

/**
 * company_profile table
 * Source: loaddailycompanydata.py
 * Basic company information
 */
const companyProfile = {
  symbol: 'AAPL',
  short_name: 'Apple Inc.',
  sector: 'Technology',
  industry: 'Consumer Electronics',
  country: 'US',
  website: 'https://www.apple.com',
  description: 'Apple Inc. designs, manufactures, and markets smartphones...',
};

/**
 * sector_benchmarks table
 * Source: loadsectorbenchmarks.py
 * Sector-wide aggregate metrics
 */
const sectorBenchmarks = {
  sector: 'Technology',
  pe_ratio: 28.0,
  price_to_book: 8.5,
  price_to_sales: 6.2,
  ev_to_ebitda: 22.5,
  fcf_yield: 4.1,
  dividend_yield: 0.8,
};

// ============================================================================
// SENTIMENT & MARKET DATA
// ============================================================================

/**
 * fear_greed_index table
 * Source: loadfeargreed.py
 * CNN Fear & Greed Index
 */
const fearGreedIndex = {
  date: '2025-10-18',
  value: 45, // 0-100 scale
  value_text: 'Neutral', // Extreme Fear, Fear, Neutral, Greed, Extreme Greed
};

/**
 * aaii_sentiment table
 * Source: loadaaiidata.py
 * AAII investor sentiment survey
 */
const aaiiSentiment = {
  date: '2025-10-18',
  bullish: 45.3, // % bullish
  neutral: 28.2, // % neutral
  bearish: 26.5, // % bearish
};

/**
 * naaim_exposure table
 * Source: loadnaaim.py
 * NAAIM exposure index
 */
const naaimExposure = {
  date: '2025-10-18',
  mean_exposure: 65.2, // % in equities
};

// ============================================================================
// EXPORT ALL SCHEMAS
// ============================================================================

module.exports = {
  // Price & Technical
  priceDaily,
  technicalDaily,
  buySignalDaily,

  // Fundamentals
  earningsHistory,
  earningsEstimate,

  // Metrics
  qualityMetrics,
  growthMetrics,
  momentumMetrics,
  riskMetrics,
  positioningMetrics,

  // Scoring (main hub)
  stockScores,

  // Reference
  companyProfile,
  sectorBenchmarks,

  // Sentiment & Market
  fearGreedIndex,
  aaiiSentiment,
  naaimExposure,
};
