-- Enhanced Database Schema for Institutional-Grade Scoring System
-- Based on Financial Platform Blueprint

-- ================================
-- CORE REFERENCE TABLES
-- ================================

-- Enhanced stock symbols with sector/industry classification
CREATE TABLE IF NOT EXISTS stock_symbols_enhanced (
    symbol VARCHAR(10) PRIMARY KEY,
    company_name VARCHAR(255) NOT NULL,
    sector VARCHAR(100),
    industry VARCHAR(150),
    sub_industry VARCHAR(200),
    market_cap_tier VARCHAR(20), -- large_cap, mid_cap, small_cap, micro_cap
    exchange VARCHAR(10),
    currency VARCHAR(3) DEFAULT 'USD',
    country VARCHAR(50) DEFAULT 'US',
    is_active BOOLEAN DEFAULT TRUE,
    listing_date DATE,
    created_at TIMESTAMP WITH TIME ZONE DEFAULT CURRENT_TIMESTAMP,
    updated_at TIMESTAMP WITH TIME ZONE DEFAULT CURRENT_TIMESTAMP
);

-- Market regime tracking for dynamic score weighting
CREATE TABLE IF NOT EXISTS market_regime (
    date DATE PRIMARY KEY,
    regime VARCHAR(20) NOT NULL, -- bull, bear, normal, transition
    confidence_score DECIMAL(5,2), -- 0-100 confidence in regime classification
    vix_level DECIMAL(6,2),
    yield_curve_slope DECIMAL(8,4),
    credit_spreads DECIMAL(8,4),
    created_at TIMESTAMP WITH TIME ZONE DEFAULT CURRENT_TIMESTAMP
);

-- ================================
-- QUALITY SCORE TABLES
-- ================================

-- Earnings Quality Metrics
CREATE TABLE IF NOT EXISTS earnings_quality_metrics (
    symbol VARCHAR(10),
    date DATE,
    period_type VARCHAR(10), -- quarterly, annual
    
    -- Accruals Quality
    accruals_ratio DECIMAL(8,4), -- (CFO - Net Income) / Total Assets
    cash_conversion_ratio DECIMAL(8,4), -- Operating Cash Flow / Net Income
    
    -- Earnings Smoothness
    earnings_volatility DECIMAL(8,4), -- Std dev of earnings/revenue over 5 years
    revenue_recognition_quality DECIMAL(8,4),
    
    -- Quality Scores (0-100)
    accruals_score DECIMAL(5,2),
    cash_conversion_score DECIMAL(5,2),
    earnings_smoothness_score DECIMAL(5,2),
    composite_earnings_quality_score DECIMAL(5,2),
    
    created_at TIMESTAMP WITH TIME ZONE DEFAULT CURRENT_TIMESTAMP,
    PRIMARY KEY (symbol, date)
);

-- Balance Sheet Strength Metrics
CREATE TABLE IF NOT EXISTS balance_sheet_strength (
    symbol VARCHAR(10),
    date DATE,
    
    -- Piotroski F-Score Components
    roa_positive BOOLEAN, -- Return on Assets > 0
    cfo_positive BOOLEAN, -- Operating Cash Flow > 0
    roa_improvement BOOLEAN, -- ROA improved vs prior year
    accruals_quality BOOLEAN, -- CFO > Net Income
    leverage_decrease BOOLEAN, -- Long-term debt ratio decreased
    current_ratio_improvement BOOLEAN, -- Current ratio improved
    shares_outstanding_decrease BOOLEAN, -- Share count decreased
    gross_margin_improvement BOOLEAN, -- Gross margin improved
    asset_turnover_improvement BOOLEAN, -- Asset turnover improved
    
    piotroski_f_score INTEGER, -- Sum of above (0-9)
    
    -- Altman Z-Score Components
    working_capital_to_assets DECIMAL(8,4),
    retained_earnings_to_assets DECIMAL(8,4),
    ebit_to_assets DECIMAL(8,4),
    market_value_equity_to_liabilities DECIMAL(8,4),
    sales_to_assets DECIMAL(8,4),
    altman_z_score DECIMAL(8,4),
    
    -- Additional Balance Sheet Metrics
    debt_to_equity DECIMAL(8,4),
    current_ratio DECIMAL(8,4),
    quick_ratio DECIMAL(8,4),
    interest_coverage DECIMAL(8,4),
    
    -- Composite Scores (0-100)
    piotroski_score DECIMAL(5,2),
    altman_score DECIMAL(5,2),
    debt_quality_score DECIMAL(5,2),
    liquidity_score DECIMAL(5,2),
    composite_balance_sheet_score DECIMAL(5,2),
    
    created_at TIMESTAMP WITH TIME ZONE DEFAULT CURRENT_TIMESTAMP,
    PRIMARY KEY (symbol, date)
);

-- Profitability Metrics
CREATE TABLE IF NOT EXISTS profitability_metrics (
    symbol VARCHAR(10),
    date DATE,
    
    -- Core Profitability Ratios
    return_on_equity DECIMAL(8,4),
    return_on_assets DECIMAL(8,4),
    return_on_invested_capital DECIMAL(8,4),
    
    -- DuPont Analysis Components
    net_profit_margin DECIMAL(8,4),
    asset_turnover DECIMAL(8,4),
    equity_multiplier DECIMAL(8,4),
    
    -- Margin Analysis
    gross_margin DECIMAL(8,4),
    operating_margin DECIMAL(8,4),
    ebitda_margin DECIMAL(8,4),
    
    -- Trend Analysis (vs. prior year)
    roe_trend DECIMAL(8,4),
    roa_trend DECIMAL(8,4),
    roic_trend DECIMAL(8,4),
    margin_trend DECIMAL(8,4),
    
    -- Scores (0-100)
    roe_score DECIMAL(5,2),
    roa_score DECIMAL(5,2),
    roic_score DECIMAL(5,2),
    margin_score DECIMAL(5,2),
    trend_score DECIMAL(5,2),
    composite_profitability_score DECIMAL(5,2),
    
    created_at TIMESTAMP WITH TIME ZONE DEFAULT CURRENT_TIMESTAMP,
    PRIMARY KEY (symbol, date)
);

-- Management Effectiveness Metrics
CREATE TABLE IF NOT EXISTS management_effectiveness (
    symbol VARCHAR(10),
    date DATE,
    
    -- Capital Allocation
    roic_vs_wacc DECIMAL(8,4), -- ROIC - WACC spread
    capex_to_revenue DECIMAL(8,4),
    rd_to_revenue DECIMAL(8,4),
    
    -- Shareholder Returns
    dividend_yield DECIMAL(8,4),
    buyback_yield DECIMAL(8,4),
    total_shareholder_yield DECIMAL(8,4),
    
    -- Efficiency Metrics
    asset_turnover_trend DECIMAL(8,4),
    working_capital_efficiency DECIMAL(8,4),
    free_cash_flow_yield DECIMAL(8,4),
    
    -- Scores (0-100)
    capital_allocation_score DECIMAL(5,2),
    shareholder_return_score DECIMAL(5,2),
    efficiency_score DECIMAL(5,2),
    composite_management_score DECIMAL(5,2),
    
    created_at TIMESTAMP WITH TIME ZONE DEFAULT CURRENT_TIMESTAMP,
    PRIMARY KEY (symbol, date)
);

-- ================================
-- VALUE SCORE TABLES
-- ================================

-- Traditional Valuation Multiples
CREATE TABLE IF NOT EXISTS valuation_multiples (
    symbol VARCHAR(10),
    date DATE,
    
    -- P/E Analysis
    pe_ratio DECIMAL(8,4),
    pe_percentile_5yr DECIMAL(5,2), -- Percentile vs 5-year history
    pe_vs_sector DECIMAL(8,4), -- Z-score vs sector
    peg_ratio DECIMAL(8,4),
    
    -- Price-to-Book Analysis
    pb_ratio DECIMAL(8,4),
    pb_percentile_5yr DECIMAL(5,2),
    pb_vs_sector DECIMAL(8,4),
    price_to_tangible_book DECIMAL(8,4),
    
    -- Enterprise Value Multiples
    ev_ebitda DECIMAL(8,4),
    ev_sales DECIMAL(8,4),
    ev_free_cash_flow DECIMAL(8,4),
    
    -- Scores (0-100, higher = more attractive valuation)
    pe_score DECIMAL(5,2),
    pb_score DECIMAL(5,2),
    ev_multiple_score DECIMAL(5,2),
    composite_multiple_score DECIMAL(5,2),
    
    created_at TIMESTAMP WITH TIME ZONE DEFAULT CURRENT_TIMESTAMP,
    PRIMARY KEY (symbol, date)
);

-- Intrinsic Value Analysis
CREATE TABLE IF NOT EXISTS intrinsic_value_analysis (
    symbol VARCHAR(10),
    date DATE,
    
    -- DCF Model Results
    dcf_intrinsic_value DECIMAL(12,4),
    dcf_margin_of_safety DECIMAL(8,4), -- (Intrinsic Value - Price) / Price
    dcf_confidence_score DECIMAL(5,2), -- Model confidence based on input quality
    
    -- Model Inputs
    terminal_growth_rate DECIMAL(6,4),
    discount_rate DECIMAL(6,4),
    forecast_period INTEGER,
    
    -- Sensitivity Analysis
    dcf_bear_case DECIMAL(12,4),
    dcf_base_case DECIMAL(12,4),
    dcf_bull_case DECIMAL(12,4),
    
    -- Residual Income Model
    residual_income_value DECIMAL(12,4),
    economic_profit DECIMAL(12,4),
    
    -- Dividend Discount Model (if applicable)
    ddm_value DECIMAL(12,4),
    dividend_growth_rate DECIMAL(6,4),
    
    -- Composite Intrinsic Value Score (0-100)
    intrinsic_value_score DECIMAL(5,2),
    
    created_at TIMESTAMP WITH TIME ZONE DEFAULT CURRENT_TIMESTAMP,
    PRIMARY KEY (symbol, date)
);

-- ================================
-- GROWTH SCORE TABLES
-- ================================

-- Revenue Growth Analysis
CREATE TABLE IF NOT EXISTS revenue_growth_analysis (
    symbol VARCHAR(10),
    date DATE,
    
    -- Growth Rates
    revenue_growth_1yr DECIMAL(8,4),
    revenue_growth_3yr_cagr DECIMAL(8,4),
    revenue_growth_5yr_cagr DECIMAL(8,4),
    
    -- Growth Quality
    organic_growth_rate DECIMAL(8,4), -- Excluding acquisitions
    same_store_sales_growth DECIMAL(8,4), -- For applicable industries
    market_share_trend DECIMAL(8,4),
    
    -- Sustainability Metrics
    sustainable_growth_rate DECIMAL(8,4), -- ROE * (1 - Payout Ratio)
    revenue_predictability DECIMAL(8,4), -- Coefficient of variation
    cyclical_adjustment DECIMAL(8,4),
    
    -- Scores (0-100)
    growth_rate_score DECIMAL(5,2),
    growth_quality_score DECIMAL(5,2),
    growth_sustainability_score DECIMAL(5,2),
    composite_revenue_growth_score DECIMAL(5,2),
    
    created_at TIMESTAMP WITH TIME ZONE DEFAULT CURRENT_TIMESTAMP,
    PRIMARY KEY (symbol, date)
);

-- Earnings Growth Analysis
CREATE TABLE IF NOT EXISTS earnings_growth_analysis (
    symbol VARCHAR(10),
    date DATE,
    
    -- EPS Growth Rates
    eps_growth_1yr DECIMAL(8,4),
    eps_growth_3yr_cagr DECIMAL(8,4),
    eps_growth_5yr_cagr DECIMAL(8,4),
    
    -- Growth Decomposition
    revenue_contribution DECIMAL(8,4), -- % of EPS growth from revenue
    margin_contribution DECIMAL(8,4), -- % from margin expansion
    share_count_contribution DECIMAL(8,4), -- % from buybacks
    
    -- Forward-Looking Growth
    eps_revision_momentum DECIMAL(8,4), -- Analyst estimate changes
    forward_growth_estimate DECIMAL(8,4),
    long_term_growth_rate DECIMAL(8,4),
    
    -- Growth Consistency
    earnings_predictability DECIMAL(8,4),
    growth_acceleration DECIMAL(8,4), -- Second derivative of growth
    
    -- Scores (0-100)
    eps_growth_score DECIMAL(5,2),
    growth_quality_score DECIMAL(5,2),
    forward_growth_score DECIMAL(5,2),
    composite_earnings_growth_score DECIMAL(5,2),
    
    created_at TIMESTAMP WITH TIME ZONE DEFAULT CURRENT_TIMESTAMP,
    PRIMARY KEY (symbol, date)
);

-- ================================
-- MOMENTUM SCORE TABLES
-- ================================

-- Price Momentum Analysis
CREATE TABLE IF NOT EXISTS price_momentum_analysis (
    symbol VARCHAR(10),
    date DATE,
    
    -- Jegadeesh-Titman Momentum
    momentum_12_1 DECIMAL(8,4), -- 12-month return excluding last month
    momentum_6_1 DECIMAL(8,4), -- 6-month return excluding last month
    momentum_3_1 DECIMAL(8,4), -- 3-month return excluding last month
    
    -- Risk-Adjusted Momentum
    risk_adjusted_momentum DECIMAL(8,4), -- Momentum / volatility
    beta_adjusted_momentum DECIMAL(8,4), -- Market-neutral momentum
    
    -- Short-term Dynamics
    reversal_1_month DECIMAL(8,4), -- Last month's return (mean reversion)
    momentum_acceleration DECIMAL(8,4), -- Change in momentum trend
    
    -- Volume Analysis
    volume_weighted_momentum DECIMAL(8,4),
    unusual_volume_score DECIMAL(5,2),
    
    -- Scores (0-100)
    price_momentum_score DECIMAL(5,2),
    volume_momentum_score DECIMAL(5,2),
    composite_price_momentum_score DECIMAL(5,2),
    
    created_at TIMESTAMP WITH TIME ZONE DEFAULT CURRENT_TIMESTAMP,
    PRIMARY KEY (symbol, date)
);

-- Technical Momentum Analysis
CREATE TABLE IF NOT EXISTS technical_momentum_analysis (
    symbol VARCHAR(10),
    date DATE,
    
    -- Moving Average Analysis
    price_vs_ma50 DECIMAL(8,4), -- (Price - MA50) / MA50
    price_vs_ma200 DECIMAL(8,4), -- (Price - MA200) / MA200
    ma50_vs_ma200 DECIMAL(8,4), -- (MA50 - MA200) / MA200
    
    -- Technical Indicators
    rsi_14 DECIMAL(6,2), -- 14-day RSI
    macd_signal DECIMAL(8,6), -- MACD line vs signal line
    macd_histogram DECIMAL(8,6), -- MACD histogram
    
    -- Momentum Oscillators
    stochastic_k DECIMAL(6,2),
    stochastic_d DECIMAL(6,2),
    williams_r DECIMAL(6,2),
    
    -- Trend Strength
    adx_14 DECIMAL(6,2), -- Average Directional Index
    aroon_up DECIMAL(6,2),
    aroon_down DECIMAL(6,2),
    
    -- Scores (0-100)
    ma_trend_score DECIMAL(5,2),
    oscillator_score DECIMAL(5,2),
    trend_strength_score DECIMAL(5,2),
    composite_technical_score DECIMAL(5,2),
    
    created_at TIMESTAMP WITH TIME ZONE DEFAULT CURRENT_TIMESTAMP,
    PRIMARY KEY (symbol, date)
);

-- ================================
-- SENTIMENT SCORE TABLES
-- ================================

-- Analyst Sentiment Analysis
CREATE TABLE IF NOT EXISTS analyst_sentiment_analysis (
    symbol VARCHAR(10),
    date DATE,
    
    -- Recommendation Summary
    strong_buy_count INTEGER,
    buy_count INTEGER,
    hold_count INTEGER,
    sell_count INTEGER,
    strong_sell_count INTEGER,
    total_analysts INTEGER,
    
    -- Recommendation Trends
    upgrades_last_30d INTEGER,
    downgrades_last_30d INTEGER,
    initiations_last_30d INTEGER,
    
    -- Price Target Analysis
    avg_price_target DECIMAL(10,4),
    high_price_target DECIMAL(10,4),
    low_price_target DECIMAL(10,4),
    price_target_vs_current DECIMAL(8,4), -- (Target - Current) / Current
    
    -- Estimate Revisions
    eps_revisions_up_last_30d INTEGER,
    eps_revisions_down_last_30d INTEGER,
    revenue_revisions_up_last_30d INTEGER,
    revenue_revisions_down_last_30d INTEGER,
    
    -- Scores (0-100)
    recommendation_score DECIMAL(5,2),
    price_target_score DECIMAL(5,2),
    revision_momentum_score DECIMAL(5,2),
    composite_analyst_sentiment_score DECIMAL(5,2),
    
    created_at TIMESTAMP WITH TIME ZONE DEFAULT CURRENT_TIMESTAMP,
    PRIMARY KEY (symbol, date)
);

-- Social Sentiment Analysis
CREATE TABLE IF NOT EXISTS social_sentiment_analysis (
    symbol VARCHAR(10),
    date DATE,
    
    -- Reddit Sentiment
    reddit_mention_count INTEGER,
    reddit_sentiment_score DECIMAL(6,4), -- -1 to 1 scale
    reddit_volume_normalized_sentiment DECIMAL(6,4), -- Adjusted for mention volume
    
    -- Google Trends
    search_volume_index INTEGER, -- 0-100 relative search volume
    search_trend_7d DECIMAL(8,4), -- % change in search volume
    search_trend_30d DECIMAL(8,4),
    
    -- News Sentiment
    news_article_count INTEGER,
    news_sentiment_score DECIMAL(6,4), -- -1 to 1 scale
    news_source_quality_weight DECIMAL(5,2), -- Weighted by source credibility
    
    -- Social Media Aggregated
    twitter_sentiment DECIMAL(6,4), -- If available
    social_media_volume INTEGER,
    viral_score DECIMAL(5,2), -- 0-100 viral potential
    
    -- Scores (0-100)
    reddit_sentiment_score_normalized DECIMAL(5,2),
    search_interest_score DECIMAL(5,2),
    news_sentiment_score_normalized DECIMAL(5,2),
    composite_social_sentiment_score DECIMAL(5,2),
    
    created_at TIMESTAMP WITH TIME ZONE DEFAULT CURRENT_TIMESTAMP,
    PRIMARY KEY (symbol, date)
);

-- ================================
-- POSITIONING SCORE TABLES
-- ================================

-- Institutional Positioning Analysis
CREATE TABLE IF NOT EXISTS institutional_positioning (
    symbol VARCHAR(10),
    date DATE,
    
    -- 13F Holdings Analysis
    institutional_ownership_pct DECIMAL(8,4), -- % of shares owned by institutions
    institutional_ownership_change DECIMAL(8,4), -- Quarter-over-quarter change
    top_10_holders_concentration DECIMAL(8,4), -- % owned by top 10 holders
    
    -- Smart Money Tracking
    hedge_fund_ownership_pct DECIMAL(8,4),
    pension_fund_ownership_pct DECIMAL(8,4),
    mutual_fund_ownership_pct DECIMAL(8,4),
    
    -- Flow Analysis
    institutional_buying_pressure DECIMAL(8,4), -- Net buying/selling pressure
    fund_concentration_score DECIMAL(5,2), -- Risk from concentrated ownership
    
    -- Scores (0-100)
    ownership_quality_score DECIMAL(5,2),
    smart_money_score DECIMAL(5,2),
    flow_momentum_score DECIMAL(5,2),
    composite_institutional_score DECIMAL(5,2),
    
    created_at TIMESTAMP WITH TIME ZONE DEFAULT CURRENT_TIMESTAMP,
    PRIMARY KEY (symbol, date)
);

-- Insider Trading Analysis
CREATE TABLE IF NOT EXISTS insider_trading_analysis (
    symbol VARCHAR(10),
    date DATE,
    
    -- Insider Activity Summary
    insider_buys_count INTEGER,
    insider_sells_count INTEGER,
    insider_buy_value DECIMAL(15,2), -- Dollar value of purchases
    insider_sell_value DECIMAL(15,2), -- Dollar value of sales
    
    -- Activity Analysis
    net_insider_activity DECIMAL(15,2), -- Buys - Sells
    insider_buy_sell_ratio DECIMAL(8,4), -- Buy value / Sell value
    
    -- Timing Analysis
    days_since_last_buy INTEGER,
    days_since_last_sell INTEGER,
    insider_activity_trend DECIMAL(8,4), -- Increasing/decreasing activity
    
    -- Scores (0-100)
    insider_sentiment_score DECIMAL(5,2),
    insider_timing_score DECIMAL(5,2),
    composite_insider_score DECIMAL(5,2),
    
    created_at TIMESTAMP WITH TIME ZONE DEFAULT CURRENT_TIMESTAMP,
    PRIMARY KEY (symbol, date)
);

-- ================================
-- MASTER SCORING TABLES
-- ================================

-- Individual Score Categories
CREATE TABLE IF NOT EXISTS stock_scores (
    symbol VARCHAR(10),
    date DATE,
    
    -- Primary Scores (0-100)
    quality_score DECIMAL(5,2),
    growth_score DECIMAL(5,2),
    value_score DECIMAL(5,2),
    momentum_score DECIMAL(5,2),
    sentiment_score DECIMAL(5,2),
    positioning_score DECIMAL(5,2),
    
    -- Sub-component Scores for Quality
    earnings_quality_subscore DECIMAL(5,2),
    balance_sheet_subscore DECIMAL(5,2),
    profitability_subscore DECIMAL(5,2),
    management_subscore DECIMAL(5,2),
    
    -- Sub-component Scores for Value
    multiples_subscore DECIMAL(5,2),
    intrinsic_value_subscore DECIMAL(5,2),
    relative_value_subscore DECIMAL(5,2),
    
    -- Sub-component Scores for Growth
    revenue_growth_subscore DECIMAL(5,2),
    earnings_growth_subscore DECIMAL(5,2),
    sustainable_growth_subscore DECIMAL(5,2),
    
    -- Sub-component Scores for Momentum
    price_momentum_subscore DECIMAL(5,2),
    fundamental_momentum_subscore DECIMAL(5,2),
    technical_momentum_subscore DECIMAL(5,2),
    
    -- Sub-component Scores for Sentiment
    analyst_sentiment_subscore DECIMAL(5,2),
    social_sentiment_subscore DECIMAL(5,2),
    news_sentiment_subscore DECIMAL(5,2),
    
    -- Sub-component Scores for Positioning
    institutional_subscore DECIMAL(5,2),
    insider_subscore DECIMAL(5,2),
    short_interest_subscore DECIMAL(5,2),
    
    -- Composite Scores
    composite_score DECIMAL(5,2), -- Weighted average of all scores
    percentile_rank DECIMAL(5,2), -- Percentile rank vs universe
    sector_adjusted_score DECIMAL(5,2), -- Sector-neutral score
    
    -- Metadata
    market_regime VARCHAR(20), -- bull, bear, normal at time of calculation
    confidence_score DECIMAL(5,2), -- 0-100 confidence in score accuracy
    data_completeness DECIMAL(5,2), -- % of required data available
    
    created_at TIMESTAMP WITH TIME ZONE DEFAULT CURRENT_TIMESTAMP,
    PRIMARY KEY (symbol, date)
);

-- Historical Score Performance Tracking
CREATE TABLE IF NOT EXISTS score_performance_tracking (
    symbol VARCHAR(10),
    score_date DATE,
    evaluation_date DATE, -- Date when performance is evaluated
    
    -- Performance Metrics
    forward_return_1m DECIMAL(8,4), -- 1-month forward return
    forward_return_3m DECIMAL(8,4), -- 3-month forward return
    forward_return_6m DECIMAL(8,4), -- 6-month forward return
    forward_return_12m DECIMAL(8,4), -- 12-month forward return
    
    -- Risk-Adjusted Performance
    sharpe_ratio_1m DECIMAL(8,4),
    max_drawdown_3m DECIMAL(8,4),
    volatility_6m DECIMAL(8,4),
    
    -- Score at Time of Investment
    original_composite_score DECIMAL(5,2),
    original_quality_score DECIMAL(5,2),
    original_value_score DECIMAL(5,2),
    original_momentum_score DECIMAL(5,2),
    
    created_at TIMESTAMP WITH TIME ZONE DEFAULT CURRENT_TIMESTAMP,
    PRIMARY KEY (symbol, score_date, evaluation_date)
);

-- ================================
-- INDEXES FOR PERFORMANCE
-- ================================

-- Primary indexes for fast lookups
CREATE INDEX IF NOT EXISTS idx_stock_scores_symbol_date ON stock_scores(symbol, date DESC);
CREATE INDEX IF NOT EXISTS idx_stock_scores_date_composite ON stock_scores(date DESC, composite_score DESC);
CREATE INDEX IF NOT EXISTS idx_stock_scores_sector ON stock_scores(date DESC, sector_adjusted_score DESC);

-- Performance tracking indexes
CREATE INDEX IF NOT EXISTS idx_score_performance_symbol ON score_performance_tracking(symbol, score_date DESC);
CREATE INDEX IF NOT EXISTS idx_score_performance_evaluation ON score_performance_tracking(evaluation_date DESC);

-- Quality metrics indexes
CREATE INDEX IF NOT EXISTS idx_earnings_quality_symbol_date ON earnings_quality_metrics(symbol, date DESC);
CREATE INDEX IF NOT EXISTS idx_balance_sheet_symbol_date ON balance_sheet_strength(symbol, date DESC);
CREATE INDEX IF NOT EXISTS idx_profitability_symbol_date ON profitability_metrics(symbol, date DESC);

-- Value metrics indexes
CREATE INDEX IF NOT EXISTS idx_valuation_multiples_symbol_date ON valuation_multiples(symbol, date DESC);
CREATE INDEX IF NOT EXISTS idx_intrinsic_value_symbol_date ON intrinsic_value_analysis(symbol, date DESC);

-- Market regime index
CREATE INDEX IF NOT EXISTS idx_market_regime_date ON market_regime(date DESC);

-- Comments for documentation
COMMENT ON TABLE stock_scores IS 'Master table containing all computed scores for stocks based on 6-factor model';
COMMENT ON TABLE score_performance_tracking IS 'Historical performance validation of scoring system';
COMMENT ON TABLE market_regime IS 'Market regime classification for dynamic score weighting';

-- Grant permissions (adjust as needed for your setup)
-- GRANT SELECT, INSERT, UPDATE ON ALL TABLES IN SCHEMA public TO webapp_user;
-- GRANT USAGE, SELECT ON ALL SEQUENCES IN SCHEMA public TO webapp_user;