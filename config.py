"""
Configuration Management - Central source for all constants, defaults, and weights

This module centralizes all configurable values including:
- Default metric values when data is unavailable
- Scoring weights with academic/business justification
- Threshold values for alerts and classifications
- Algorithm parameters

All values are documented with their rationale to enable audit trails and
allow stakeholders to understand scoring logic.
"""

# =============================================================================
# GROWTH METRICS DEFAULTS
# =============================================================================
"""
When growth metrics data is unavailable, these defaults are used.
These are NOT targets or benchmarks - they indicate data unavailability.
"""
GROWTH_RATE_DEFAULT = 0.05  # 5% - Conservative default when revenue data missing
PAYOUT_RATIO_DEFAULT = 0.30  # 30% - Historical market average for payout ratio
EARNINGS_STABILITY_DEFAULT = 0.50  # 50% - Neutral score indicating insufficient data


# =============================================================================
# RISK METRICS DEFAULTS AND CALCULATIONS
# =============================================================================
"""
Risk metric calculations and defaults
"""
# Volatility calculations
ANNUALIZATION_FACTOR = 252  # Trading days per year

# Downside volatility - using only negative returns
# These are calculated metrics, not defaults
DOWNSIDE_VOLATILITY_MIN_PERIODS = 20  # Minimum periods needed for valid calculation


# =============================================================================
# VALUATION METRICS DEFAULTS
# =============================================================================
"""
Valuation defaults when specific market data is unavailable
"""
DCF_RISK_FREE_RATE = 0.04  # 4% - Current risk-free rate assumption (Treasury yield)
DCF_EQUITY_RISK_PREMIUM = 0.065  # 6.5% - Market risk premium over risk-free rate
DCF_DEFAULT_GROWTH_TERMINAL = 0.025  # 2.5% - Terminal growth rate (GDP growth assumption)

# When market or sector benchmarks are unavailable
VALUATION_NEUTRAL_SCORE = 50.0  # 50/100 = neutral valuation


# =============================================================================
# POSITIONING & SENTIMENT DEFAULTS
# =============================================================================
"""
Technical and sentiment positioning defaults
"""
POSITIONING_SCORE_DEFAULT = 70.0  # Neutral positioning score (0-100 scale)
SENTIMENT_SCORE_DEFAULT = 50.0  # Neutral sentiment (0-100 scale)


# =============================================================================
# COMPOSITE SCORE WEIGHTING FRAMEWORK
# =============================================================================
"""
Final composite score calculation weights

Current allocation (quality-focused):
- Quality: 30% → Profitability and financial stability (priority metric)
- Momentum: 20% → Short-term price momentum
- Value: 15% → PE/PB ratios relative to market
- Growth: 15% → Earnings growth momentum
- Positioning: 10% → Technical support/resistance levels
- Risk: 10% → Volatility and downside risk

Note: Sentiment factor excluded pending data infrastructure readiness
"""
COMPOSITE_SCORE_WEIGHTS = {
    "quality": 0.30,         # Profitability, margins, ROE (quality of earnings) - PRIMARY
    "momentum": 0.20,        # Short-term price momentum (proven 3-12 month effect)
    "value": 0.15,           # PE/PB ratios relative to market (mean reversion)
    "growth": 0.15,          # Revenue and earnings momentum (acceleration)
    "positioning": 0.10,     # Technical positioning (support/resistance)
    "risk": 0.10,            # Volatility and downside risk management
}

# Validation
assert abs(sum(COMPOSITE_SCORE_WEIGHTS.values()) - 1.0) < 0.0001, \
    f"Weights must sum to 1.0, got {sum(COMPOSITE_SCORE_WEIGHTS.values())}"


# =============================================================================
# MOMENTUM SCORE COMPONENT WEIGHTS
# =============================================================================
"""
Momentum factor breakdown - how the 25% momentum weight is distributed

Each component captures different timeframe momentum:
- Short-term (1-3 months): Latest trend
- Medium-term (3-6 months): Intermediate trend
- Long-term (6-12 months): Sustained momentum
"""
MOMENTUM_WEIGHTS = {
    "short_term": 0.25,              # 1-3 month trend
    "medium_term": 0.25,             # 3-6 month trend
    "longer_term": 0.20,             # 6-12 month trend
    "relative_strength": 0.15,       # Relative to sector/market
    "consistency": 0.15,             # Positive months ratio (upside consistency)
}

assert abs(sum(MOMENTUM_WEIGHTS.values()) - 1.0) < 0.0001


# =============================================================================
# VALUE SCORE COMPONENT WEIGHTS
# =============================================================================
"""
Value factor breakdown - comparing stock multiples to market/sector
"""
VALUE_WEIGHTS = {
    "pe_ratio": 0.30,                # Price-to-Earnings (most used multiple)
    "price_to_book": 0.20,           # Price-to-Book (asset valuation)
    "price_to_sales": 0.15,          # Price-to-Sales (revenue valuation)
    "ev_to_ebitda": 0.20,            # EV/EBITDA (enterprise value)
    "fcf_yield": 0.10,               # Free cash flow yield (cash generation)
    "peg_ratio": 0.05,               # PEG ratio (growth-adjusted PE)
}

assert abs(sum(VALUE_WEIGHTS.values()) - 1.0) < 0.0001


# =============================================================================
# QUALITY SCORE COMPONENT WEIGHTS
# =============================================================================
"""
Quality factor - profitability, financial stability, earnings consistency
"""
QUALITY_WEIGHTS = {
    "return_on_equity": 0.25,        # ROE - Return on shareholder capital
    "margin_consistency": 0.20,      # Stable profit margins (quality of earnings)
    "debt_to_equity": 0.20,          # Financial leverage (balance sheet strength)
    "earnings_stability": 0.20,      # EPS growth consistency
    "cash_conversion": 0.15,         # Operating CF / Net Income (cash quality)
}

assert abs(sum(QUALITY_WEIGHTS.values()) - 1.0) < 0.0001


# =============================================================================
# GROWTH SCORE COMPONENT WEIGHTS
# =============================================================================
"""
Growth factor - revenue and earnings acceleration
"""
GROWTH_WEIGHTS = {
    "revenue_growth_3y_cagr": 0.30,  # Revenue growth compound annual rate
    "eps_growth_3y_cagr": 0.30,      # Earnings growth acceleration
    "operating_income_growth": 0.20, # Operating leverage (top-line to bottom-line)
    "fcf_growth": 0.10,              # Free cash flow growth
    "quarterly_momentum": 0.10,      # Recent quarter-over-quarter acceleration
}

assert abs(sum(GROWTH_WEIGHTS.values()) - 1.0) < 0.0001


# =============================================================================
# RISK SCORE COMPONENT WEIGHTS
# =============================================================================
"""
Risk factor - volatility, drawdown, systematic risk

Final risk_score formula (in loadstockscores.py):
  risk_score = (
    volatility_12m * 0.40 +           # Annualized volatility (40%)
    technical_positioning * 0.27 +    # Support/resistance distance (27%)
    max_drawdown_52w * 0.33           # Maximum peak-to-trough loss (33%)
  )

Rationale:
- 40% Volatility: Price fluctuation is primary risk (beta equivalent)
- 27% Technical: Positioning relative to support is predictive of reversal risk
- 33% Drawdown: Actual loss suffered (realized downside risk)
"""
RISK_SCORE_WEIGHTS = {
    "volatility": 0.40,              # 12-month annualized volatility
    "technical_positioning": 0.27,   # Price distance from support/resistance
    "max_drawdown": 0.33,            # 52-week maximum drawdown
}

assert abs(sum(RISK_SCORE_WEIGHTS.values()) - 1.0) < 0.0001


# =============================================================================
# SCORE THRESHOLDS & CLASSIFICATIONS
# =============================================================================
"""
Score thresholds for classification and alerts
Scores are normalized 0-100
"""
SCORE_THRESHOLDS = {
    # Quality classifications
    "excellent": 80,                 # 80+ = Strong buy signal
    "good": 70,                      # 70-79 = Buy signal
    "neutral": 50,                   # 50-69 = Hold
    "poor": 30,                      # 30-49 = Caution
    "weak": 0,                       # 0-29 = Avoid

    # Risk classifications (lower is better for risk)
    "very_high_risk": 70,            # Risk score 70+ = High volatility/drawdown risk
    "high_risk": 50,                 # Risk score 50-69
    "moderate_risk": 30,             # Risk score 30-49
    "low_risk": 0,                   # Risk score 0-29 = Stable
}


# =============================================================================
# ALERT THRESHOLDS
# =============================================================================
"""
Thresholds that trigger alerts for data quality issues
"""
MIN_QUARTERS_FOR_GROWTH = 5         # Minimum historical quarters for growth calculation
MIN_PERIODS_FOR_VOLATILITY = 20     # Minimum periods for volatility calculation
MIN_DATA_POINTS_FOR_MOMENTUM = 8    # Minimum data points for momentum indicators


# =============================================================================
# DATABASE & DATA HANDLING
# =============================================================================
"""
Database connection and data processing parameters
"""
DB_POOL_MIN_SIZE = 2                # Minimum connections in pool
DB_POOL_MAX_SIZE = 10               # Maximum connections in pool
DB_TIMEOUT = 30                     # Query timeout in seconds
MAX_WORKERS = 4                     # Max concurrent loader threads


# =============================================================================
# LOGGING & OUTPUT
# =============================================================================
"""
Logging and output configuration
"""
LOG_LEVEL = "INFO"
LOG_FORMAT = "%(asctime)s - %(levelname)s - [%(funcName)s] %(message)s"


# =============================================================================
# VALIDATION UTILITY FUNCTIONS
# =============================================================================
def get_weight(factor_name: str, weights_dict: dict) -> float:
    """
    Get weight for a factor, validating it exists and is normalized.

    Args:
        factor_name: Name of the factor (e.g., 'momentum')
        weights_dict: Dictionary of weights (e.g., COMPOSITE_SCORE_WEIGHTS)

    Returns:
        Float weight value

    Raises:
        KeyError: If factor not found in weights dictionary
        ValueError: If weights don't sum to 1.0
    """
    if factor_name not in weights_dict:
        raise KeyError(f"Factor '{factor_name}' not found in weights. "
                      f"Available: {list(weights_dict.keys())}")

    total = sum(weights_dict.values())
    if abs(total - 1.0) > 0.0001:
        raise ValueError(f"Weights don't sum to 1.0: {total}")

    return weights_dict[factor_name]


def get_score_classification(score: float, metric_type: str = "composite") -> str:
    """
    Classify a score into human-readable category.

    Args:
        score: Score value (0-100)
        metric_type: Type of metric ('composite' or 'risk')

    Returns:
        String classification
    """
    if metric_type == "risk":
        # For risk, higher = worse
        thresholds = [
            (70, "Very High Risk"),
            (50, "High Risk"),
            (30, "Moderate Risk"),
            (0, "Low Risk"),
        ]
    else:
        # For composite, higher = better
        thresholds = [
            (80, "Excellent"),
            (70, "Good"),
            (50, "Neutral"),
            (30, "Poor"),
            (0, "Weak"),
        ]

    for threshold, label in thresholds:
        if score >= threshold:
            return label
    return thresholds[-1][1]


if __name__ == "__main__":
    # Validation script
    print("✅ Configuration validation passed")
    print(f"   Composite weights: {COMPOSITE_SCORE_WEIGHTS}")
    print(f"   Risk weights: {RISK_SCORE_WEIGHTS}")
    print(f"   All weight sets validated and sum to 1.0")
