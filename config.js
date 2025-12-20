/**
 * Configuration Management - Central source for all constants, defaults, and weights
 *
 * JavaScript version of config.py
 * This module centralizes all configurable values including:
 * - Scoring weights with academic justification (Fama-French Factor Model)
 * - Default metric values when data is unavailable
 * - Threshold values for alerts and classifications
 */

// =============================================================================
// COMPOSITE SCORE WEIGHTING FRAMEWORK
// =============================================================================
/**
 * Final composite score calculation weights
 *
 * Current allocation (quality-focused):
 *   * Quality: 30% → Profitability and financial stability (priority metric)
 *   * Momentum: 20% → Short-term price momentum
 *   * Value: 15% → PE/PB ratios relative to market
 *   * Growth: 15% → Earnings growth momentum
 *   * Positioning: 10% → Technical support/resistance levels
 *   * Risk: 10% → Volatility and downside risk
 *
 * Note: Sentiment factor excluded pending data infrastructure readiness
 */
const COMPOSITE_SCORE_WEIGHTS = {
  quality: 0.30,        // Profitability, margins, ROE (quality of earnings) - PRIMARY
  momentum: 0.20,       // Short-term price momentum (proven 3-12 month effect)
  value: 0.15,          // PE/PB ratios relative to market (mean reversion)
  growth: 0.15,         // Revenue and earnings momentum (acceleration)
  positioning: 0.10,    // Technical positioning (support/resistance)
  risk: 0.10,           // Volatility and downside risk management
};

// Validate weights sum to 1.0
const compositeSum = Object.values(COMPOSITE_SCORE_WEIGHTS).reduce((a, b) => a + b, 0);
if (Math.abs(compositeSum - 1.0) >= 0.0001) {
  throw new Error(`Composite score weights must sum to 1.0, got ${compositeSum}`);
}

// =============================================================================
// RISK SCORE WEIGHTING
// =============================================================================
/**
 * Risk score calculation weights
 * 40% Volatility + 27% Technical Positioning + 33% Max Drawdown
 */
const RISK_SCORE_WEIGHTS = {
  volatility: 0.40,                // 12-month annualized volatility
  technical_positioning: 0.27,     // Price distance from support/resistance
  max_drawdown: 0.33,              // 52-week maximum drawdown
};

// Validate weights sum to 1.0
const riskSum = Object.values(RISK_SCORE_WEIGHTS).reduce((a, b) => a + b, 0);
if (Math.abs(riskSum - 1.0) >= 0.0001) {
  throw new Error(`Risk score weights must sum to 1.0, got ${riskSum}`);
}

// =============================================================================
// MOMENTUM SCORE COMPONENT WEIGHTS
// =============================================================================
/**
 * Momentum factor breakdown - how the 25% momentum weight is distributed
 *
 * Each component captures different timeframe momentum:
 * - Short-term (1-3 months): Latest trend
 * - Medium-term (3-6 months): Intermediate trend
 * - Long-term (6-12 months): Sustained momentum
 */
const MOMENTUM_WEIGHTS = {
  short_term: 0.25,              // 1-3 month trend
  medium_term: 0.25,             // 3-6 month trend
  longer_term: 0.20,             // 6-12 month trend
  relative_strength: 0.15,       // Relative to sector/market
  consistency: 0.15,             // Positive months ratio (upside consistency)
};

// =============================================================================
// VALUE SCORE COMPONENT WEIGHTS
// =============================================================================
/**
 * Value factor breakdown - comparing stock multiples to market/sector
 */
const VALUE_WEIGHTS = {
  pe_ratio: 0.30,                // Price-to-Earnings (most used multiple)
  price_to_book: 0.20,           // Price-to-Book (asset valuation)
  price_to_sales: 0.15,          // Price-to-Sales (revenue valuation)
  ev_to_ebitda: 0.20,            // EV/EBITDA (enterprise value)
  fcf_yield: 0.10,               // Free cash flow yield (cash generation)
  peg_ratio: 0.05,               // PEG ratio (growth-adjusted PE)
};

// =============================================================================
// QUALITY SCORE COMPONENT WEIGHTS
// =============================================================================
/**
 * Quality factor - profitability, financial stability, earnings consistency
 */
const QUALITY_WEIGHTS = {
  return_on_equity: 0.25,        // ROE - Return on shareholder capital
  margin_consistency: 0.20,      // Stable profit margins (quality of earnings)
  debt_to_equity: 0.20,          // Financial leverage (balance sheet strength)
  earnings_stability: 0.20,      // EPS growth consistency
  accrual_quality: 0.15,         // Ratio of operating cash flow to net income
};

// =============================================================================
// GROWTH SCORE COMPONENT WEIGHTS
// =============================================================================
/**
 * Growth factor - revenue and earnings growth acceleration
 */
const GROWTH_WEIGHTS = {
  revenue_growth_3y: 0.25,       // 3-year revenue CAGR (acceleration trend)
  earnings_growth_3y: 0.25,      // 3-year earnings CAGR
  revenue_growth_acceleration: 0.20,  // Comparing recent vs historical growth
  earnings_growth_acceleration: 0.20, // Acceleration in EPS growth
  fcf_growth: 0.10,              // Free cash flow growth (most important)
};

// =============================================================================
// GROWTH METRICS DEFAULTS
// =============================================================================
/**
 * DATA INTEGRITY RULE: Return NULL for missing data, NEVER use defaults
 *
 * These constants exist only for historical reference and should NEVER be used
 * as fallback values when real data is unavailable.
 *
 * Previous behavior: Used these as fallback when metrics missing
 * Current behavior: Return NULL when data unavailable (not these defaults)
 *
 * Keeping these defined to prevent code breakage, but marking as DEPRECATED.
 */
const GROWTH_RATE_DEFAULT = null;              // DEPRECATED: Use NULL instead
const PAYOUT_RATIO_DEFAULT = null;             // DEPRECATED: Use NULL instead
const EARNINGS_STABILITY_DEFAULT = null;       // DEPRECATED: Use NULL instead

// =============================================================================
// RISK METRICS DEFAULTS AND CALCULATIONS
// =============================================================================
/**
 * Risk metric calculations and defaults
 */
const ANNUALIZATION_FACTOR = 252;             // Trading days per year
const DOWNSIDE_VOLATILITY_MIN_PERIODS = 20;   // Minimum periods needed for valid calculation

// =============================================================================
// VALUATION METRICS DEFAULTS
// =============================================================================
/**
 * Valuation defaults when specific market data is unavailable
 */
const DCF_RISK_FREE_RATE = 0.04;              // 4% - Current risk-free rate assumption (Treasury yield)
const DCF_EQUITY_RISK_PREMIUM = 0.065;        // 6.5% - Market risk premium over risk-free rate
const DCF_DEFAULT_GROWTH_TERMINAL = 0.025;    // 2.5% - Terminal growth rate (GDP growth assumption)
const VALUATION_NEUTRAL_SCORE = 50.0;         // 50/100 = neutral valuation

// =============================================================================
// POSITIONING & SENTIMENT DEFAULTS
// =============================================================================
/**
 * DATA INTEGRITY RULE: Return NULL for missing data, NEVER use defaults
 *
 * Previous behavior: Used these as "neutral" fallback values
 * Current behavior: Return NULL when data unavailable
 *
 * DEPRECATED: Do NOT use these as fill-in values for missing metrics
 */
const POSITIONING_SCORE_DEFAULT = null;       // DEPRECATED: Use NULL instead
const SENTIMENT_SCORE_DEFAULT = null;         // DEPRECATED: Use NULL instead

// =============================================================================
// EXPORTS
// =============================================================================
module.exports = {
  // Composite scores
  COMPOSITE_SCORE_WEIGHTS,
  RISK_SCORE_WEIGHTS,

  // Component weights
  MOMENTUM_WEIGHTS,
  VALUE_WEIGHTS,
  QUALITY_WEIGHTS,
  GROWTH_WEIGHTS,

  // Defaults
  GROWTH_RATE_DEFAULT,
  PAYOUT_RATIO_DEFAULT,
  EARNINGS_STABILITY_DEFAULT,
  ANNUALIZATION_FACTOR,
  DOWNSIDE_VOLATILITY_MIN_PERIODS,
  DCF_RISK_FREE_RATE,
  DCF_EQUITY_RISK_PREMIUM,
  DCF_DEFAULT_GROWTH_TERMINAL,
  VALUATION_NEUTRAL_SCORE,
  POSITIONING_SCORE_DEFAULT,
  SENTIMENT_SCORE_DEFAULT,
};
