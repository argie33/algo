-- Comprehensive database schema for algo trading system
-- Created: 2026-07-05
-- Purpose: Initialize all tables needed for data loaders, API, and orchestration

-- ============================================================================
-- METRIC TABLES (Foundation for stock scoring)
-- ============================================================================

CREATE TABLE IF NOT EXISTS growth_metrics (
    symbol VARCHAR(20) NOT NULL PRIMARY KEY,
    revenue_growth_1y NUMERIC(6, 2),
    revenue_growth_3y NUMERIC(6, 2),
    revenue_growth_5y NUMERIC(6, 2),
    eps_growth_1y NUMERIC(6, 2),
    eps_growth_3y NUMERIC(6, 2),
    eps_growth_5y NUMERIC(6, 2),
    quarterly_growth_momentum NUMERIC(6, 2),
    revenue_growth_yoy NUMERIC(6, 2),
    revenue_growth_1y_unavailable_reason VARCHAR(255),
    revenue_growth_3y_unavailable_reason VARCHAR(255),
    revenue_growth_5y_unavailable_reason VARCHAR(255),
    eps_growth_1y_unavailable_reason VARCHAR(255),
    eps_growth_3y_unavailable_reason VARCHAR(255),
    eps_growth_5y_unavailable_reason VARCHAR(255),
    data_unavailable BOOLEAN DEFAULT FALSE,
    reason VARCHAR(500),
    updated_at TIMESTAMP WITH TIME ZONE DEFAULT CURRENT_TIMESTAMP
);
CREATE INDEX IF NOT EXISTS idx_growth_metrics_updated_at ON growth_metrics(updated_at DESC);

CREATE TABLE IF NOT EXISTS quality_metrics (
    symbol VARCHAR(20) NOT NULL PRIMARY KEY,
    quality_score NUMERIC(5, 2),
    roe NUMERIC(6, 2),
    operating_margin NUMERIC(6, 2),
    net_margin NUMERIC(6, 2),
    debt_to_equity NUMERIC(8, 2),
    current_ratio NUMERIC(6, 2),
    debt_to_capital NUMERIC(6, 2),
    roa NUMERIC(6, 2),
    fcf_yield NUMERIC(6, 2),
    roe_unavailable_reason VARCHAR(255),
    operating_margin_unavailable_reason VARCHAR(255),
    net_margin_unavailable_reason VARCHAR(255),
    data_unavailable BOOLEAN DEFAULT FALSE,
    reason VARCHAR(500),
    updated_at TIMESTAMP WITH TIME ZONE DEFAULT CURRENT_TIMESTAMP
);
CREATE INDEX IF NOT EXISTS idx_quality_metrics_updated_at ON quality_metrics(updated_at DESC);

CREATE TABLE IF NOT EXISTS value_metrics (
    symbol VARCHAR(20) NOT NULL PRIMARY KEY,
    pe_ratio NUMERIC(8, 2),
    pb_ratio NUMERIC(8, 2),
    ps_ratio NUMERIC(8, 2),
    pcf_ratio NUMERIC(8, 2),
    dividend_yield NUMERIC(6, 4),
    peg_ratio NUMERIC(8, 2),
    fcf_to_earnings NUMERIC(8, 2),
    pe_ratio_unavailable_reason VARCHAR(255),
    data_unavailable BOOLEAN DEFAULT FALSE,
    reason VARCHAR(500),
    updated_at TIMESTAMP WITH TIME ZONE DEFAULT CURRENT_TIMESTAMP
);
CREATE INDEX IF NOT EXISTS idx_value_metrics_updated_at ON value_metrics(updated_at DESC);

CREATE TABLE IF NOT EXISTS positioning_metrics (
    symbol VARCHAR(20) NOT NULL PRIMARY KEY,
    institutional_ownership_pct NUMERIC(6, 2),
    short_interest_pct NUMERIC(6, 2),
    insider_ownership_pct NUMERIC(6, 2),
    float_pct NUMERIC(6, 2),
    institutional_ownership_pct_unavailable_reason VARCHAR(255),
    data_unavailable BOOLEAN DEFAULT FALSE,
    reason VARCHAR(500),
    updated_at TIMESTAMP WITH TIME ZONE DEFAULT CURRENT_TIMESTAMP
);
CREATE INDEX IF NOT EXISTS idx_positioning_metrics_updated_at ON positioning_metrics(updated_at DESC);

CREATE TABLE IF NOT EXISTS stability_metrics (
    symbol VARCHAR(20) NOT NULL PRIMARY KEY,
    beta NUMERIC(6, 2),
    volatility_30d NUMERIC(6, 4),
    volatility_60d NUMERIC(6, 4),
    volatility_90d NUMERIC(6, 4),
    volatility_252d NUMERIC(6, 4),
    correlation_spy NUMERIC(6, 4),
    max_drawdown_1y NUMERIC(6, 2),
    beta_unavailable_reason VARCHAR(255),
    volatility_30d_unavailable_reason VARCHAR(255),
    data_unavailable BOOLEAN DEFAULT FALSE,
    reason VARCHAR(500),
    updated_at TIMESTAMP WITH TIME ZONE DEFAULT CURRENT_TIMESTAMP
);
CREATE INDEX IF NOT EXISTS idx_stability_metrics_updated_at ON stability_metrics(updated_at DESC);

-- ============================================================================
-- SCORE TABLES (Aggregated metrics for trading decisions)
-- ============================================================================

CREATE TABLE IF NOT EXISTS stock_scores (
    symbol VARCHAR(20) NOT NULL PRIMARY KEY,
    composite_score NUMERIC(5, 2),
    momentum_score NUMERIC(5, 2),
    quality_score NUMERIC(5, 2),
    growth_score NUMERIC(5, 2),
    value_score NUMERIC(5, 2),
    positioning_score NUMERIC(5, 2),
    stability_score NUMERIC(5, 2),
    rs_percentile NUMERIC(5, 2),
    data_completeness NUMERIC(5, 2),
    data_unavailable BOOLEAN DEFAULT FALSE,
    unavailable_metrics JSONB,
    reason VARCHAR(500),
    updated_at TIMESTAMP WITH TIME ZONE DEFAULT CURRENT_TIMESTAMP
);
CREATE INDEX IF NOT EXISTS idx_stock_scores_composite ON stock_scores(composite_score DESC);
CREATE INDEX IF NOT EXISTS idx_stock_scores_updated_at ON stock_scores(updated_at DESC);

-- ============================================================================
-- SIGNAL TABLES (Trading signals and decisions)
-- ============================================================================

CREATE TABLE IF NOT EXISTS signals_daily (
    symbol VARCHAR(20) NOT NULL,
    date DATE NOT NULL,
    signal_type VARCHAR(50),
    signal_strength NUMERIC(5, 2),
    signal_score NUMERIC(5, 2),
    quality_score NUMERIC(5, 2),
    growth_score NUMERIC(5, 2),
    momentum_score NUMERIC(5, 2),
    reasons JSONB,
    components JSONB,
    data_unavailable BOOLEAN DEFAULT FALSE,
    created_at TIMESTAMP WITH TIME ZONE DEFAULT CURRENT_TIMESTAMP,
    updated_at TIMESTAMP WITH TIME ZONE DEFAULT CURRENT_TIMESTAMP,
    PRIMARY KEY (symbol, date)
);
CREATE INDEX IF NOT EXISTS idx_signals_daily_symbol ON signals_daily(symbol);
CREATE INDEX IF NOT EXISTS idx_signals_daily_date ON signals_daily(date DESC);
CREATE INDEX IF NOT EXISTS idx_signals_daily_signal_score ON signals_daily(signal_score DESC);

-- ============================================================================
-- PRICE DATA (Historical price information)
-- ============================================================================

CREATE TABLE IF NOT EXISTS price_daily (
    symbol VARCHAR(20) NOT NULL,
    date DATE NOT NULL,
    open NUMERIC(12, 4),
    high NUMERIC(12, 4),
    low NUMERIC(12, 4),
    close NUMERIC(12, 4),
    adj_close NUMERIC(12, 4),
    volume BIGINT,
    split_coefficient NUMERIC(12, 4) DEFAULT 1.0,
    PRIMARY KEY (symbol, date)
);
CREATE INDEX IF NOT EXISTS idx_price_daily_symbol ON price_daily(symbol);
CREATE INDEX IF NOT EXISTS idx_price_daily_date ON price_daily(date DESC);
CREATE INDEX IF NOT EXISTS idx_price_daily_symbol_date ON price_daily(symbol, date DESC);

CREATE TABLE IF NOT EXISTS price_weekly (
    symbol VARCHAR(20) NOT NULL,
    date DATE NOT NULL,
    open NUMERIC(12, 4),
    high NUMERIC(12, 4),
    low NUMERIC(12, 4),
    close NUMERIC(12, 4),
    volume BIGINT,
    PRIMARY KEY (symbol, date)
);
CREATE INDEX IF NOT EXISTS idx_price_weekly_symbol ON price_weekly(symbol);
CREATE INDEX IF NOT EXISTS idx_price_weekly_date ON price_weekly(date DESC);

CREATE TABLE IF NOT EXISTS price_monthly (
    symbol VARCHAR(20) NOT NULL,
    date DATE NOT NULL,
    open NUMERIC(12, 4),
    high NUMERIC(12, 4),
    low NUMERIC(12, 4),
    close NUMERIC(12, 4),
    volume BIGINT,
    PRIMARY KEY (symbol, date)
);
CREATE INDEX IF NOT EXISTS idx_price_monthly_symbol ON price_monthly(symbol);
CREATE INDEX IF NOT EXISTS idx_price_monthly_date ON price_monthly(date DESC);

-- ============================================================================
-- MARKET DATA (Market health, sectors, industries)
-- ============================================================================

CREATE TABLE IF NOT EXISTS market_health_daily (
    date DATE NOT NULL PRIMARY KEY,
    vix_close NUMERIC(6, 2),
    breadth_advance NUMERIC(6, 2),
    breadth_decline NUMERIC(6, 2),
    breadth_unch NUMERIC(6, 2),
    breadth_advance_pct NUMERIC(5, 2),
    breadth_decline_pct NUMERIC(5, 2),
    new_highs NUMERIC(6, 2),
    new_lows NUMERIC(6, 2),
    upticks_pct NUMERIC(5, 2),
    downticks_pct NUMERIC(5, 2),
    put_call_ratio NUMERIC(6, 4),
    cumulative_breadth NUMERIC(12, 2),
    spy_close NUMERIC(8, 2),
    spy_change_pct NUMERIC(6, 2),
    data_unavailable BOOLEAN DEFAULT FALSE,
    reason VARCHAR(500),
    updated_at TIMESTAMP WITH TIME ZONE DEFAULT CURRENT_TIMESTAMP
);
CREATE INDEX IF NOT EXISTS idx_market_health_daily_date ON market_health_daily(date DESC);

CREATE TABLE IF NOT EXISTS sector_ranking (
    date DATE NOT NULL,
    sector_name VARCHAR(100) NOT NULL,
    current_rank INTEGER,
    momentum_score NUMERIC(6, 2),
    relative_strength NUMERIC(6, 2),
    updated_at TIMESTAMP WITH TIME ZONE DEFAULT CURRENT_TIMESTAMP,
    PRIMARY KEY (date, sector_name)
);
CREATE INDEX IF NOT EXISTS idx_sector_ranking_date ON sector_ranking(date DESC);

CREATE TABLE IF NOT EXISTS industry_ranking (
    date_recorded DATE NOT NULL,
    industry VARCHAR(100) NOT NULL,
    momentum_score NUMERIC(6, 2),
    relative_strength NUMERIC(6, 2),
    updated_at TIMESTAMP WITH TIME ZONE DEFAULT CURRENT_TIMESTAMP,
    PRIMARY KEY (date_recorded, industry)
);
CREATE INDEX IF NOT EXISTS idx_industry_ranking_date ON industry_ranking(date_recorded DESC);

-- ============================================================================
-- CONFIGURATION & SYSTEM TABLES
-- ============================================================================

CREATE TABLE IF NOT EXISTS algo_config (
    key VARCHAR(255) NOT NULL PRIMARY KEY,
    value VARCHAR(1024),
    data_type VARCHAR(50),
    is_critical BOOLEAN DEFAULT FALSE,
    updated_at TIMESTAMP WITH TIME ZONE DEFAULT CURRENT_TIMESTAMP,
    updated_by VARCHAR(255)
);

CREATE TABLE IF NOT EXISTS orchestrator_execution_log (
    id SERIAL PRIMARY KEY,
    execution_phase VARCHAR(100),
    status VARCHAR(50),
    symbol_count INTEGER,
    started_at TIMESTAMP WITH TIME ZONE,
    completed_at TIMESTAMP WITH TIME ZONE,
    error_message TEXT,
    created_at TIMESTAMP WITH TIME ZONE DEFAULT CURRENT_TIMESTAMP
);
CREATE INDEX IF NOT EXISTS idx_orchestrator_execution_log_created_at ON orchestrator_execution_log(created_at DESC);

-- ============================================================================
-- AUDIT LOG (Critical for dashboard activity/audit endpoints)
-- ============================================================================

CREATE TABLE IF NOT EXISTS algo_audit_log (
    id SERIAL PRIMARY KEY,
    action_type VARCHAR(100) NOT NULL,
    symbol VARCHAR(20),
    action_date TIMESTAMP WITH TIME ZONE,
    details JSONB,
    actor VARCHAR(100),
    status VARCHAR(50),
    error_message TEXT,
    severity VARCHAR(50),
    created_at TIMESTAMP WITH TIME ZONE DEFAULT CURRENT_TIMESTAMP,
    operation_type VARCHAR(50),
    entity_type VARCHAR(50),
    entity_id VARCHAR(100),
    operation_details TEXT,
    updated_at TIMESTAMP WITH TIME ZONE DEFAULT CURRENT_TIMESTAMP
);
CREATE INDEX IF NOT EXISTS idx_algo_audit_log_created_at ON algo_audit_log(created_at DESC);
CREATE INDEX IF NOT EXISTS idx_algo_audit_log_action_type ON algo_audit_log(action_type);
CREATE INDEX IF NOT EXISTS idx_algo_audit_log_symbol ON algo_audit_log(symbol);
CREATE INDEX IF NOT EXISTS idx_algo_audit_log_actor ON algo_audit_log(actor);
CREATE INDEX IF NOT EXISTS idx_algo_audit_log_operation_type ON algo_audit_log(operation_type);
CREATE INDEX IF NOT EXISTS idx_algo_audit_log_entity_type ON algo_audit_log(entity_type);

-- ============================================================================
-- SIGNAL STORAGE (Critical for dashboard and API)
-- ============================================================================

CREATE TABLE IF NOT EXISTS algo_signals (
    id SERIAL PRIMARY KEY,
    signal_date DATE NOT NULL,
    symbol VARCHAR(20) NOT NULL,
    source_table VARCHAR(50),
    source_timeframe VARCHAR(20),
    raw_signal VARCHAR(20),
    entry_price DECIMAL(12, 4),
    entry_stage VARCHAR(20),
    signal_active BOOLEAN DEFAULT TRUE,
    signal_quality_score INTEGER,
    risk_score DECIMAL(8, 2),
    created_at TIMESTAMP WITH TIME ZONE DEFAULT CURRENT_TIMESTAMP,
    updated_at TIMESTAMP WITH TIME ZONE DEFAULT CURRENT_TIMESTAMP,
    UNIQUE(signal_date, symbol, source_timeframe)
);
CREATE INDEX IF NOT EXISTS idx_algo_signals_symbol_date ON algo_signals(symbol, signal_date DESC);
CREATE INDEX IF NOT EXISTS idx_algo_signals_entry_stage ON algo_signals(entry_stage) WHERE entry_stage IS NOT NULL;
CREATE INDEX IF NOT EXISTS idx_algo_signals_active ON algo_signals(signal_active);

-- ============================================================================
-- MARKET SENTIMENT (Critical for market data endpoints)
-- ============================================================================

CREATE TABLE IF NOT EXISTS market_sentiment (
    id SERIAL PRIMARY KEY,
    date DATE NOT NULL UNIQUE,
    fear_greed_index DECIMAL(8, 4),
    put_call_ratio DECIMAL(8, 4),
    vix DECIMAL(8, 4),
    sentiment_score DECIMAL(8, 4),
    bullish_pct DECIMAL(8, 2),
    bearish_pct DECIMAL(8, 2),
    neutral_pct DECIMAL(8, 2),
    created_at TIMESTAMP WITH TIME ZONE DEFAULT CURRENT_TIMESTAMP
);
CREATE INDEX IF NOT EXISTS idx_market_sentiment_date ON market_sentiment(date DESC);

-- ============================================================================
-- MARKET CONSTITUENTS (S&P 500, ETF memberships)
-- ============================================================================

CREATE TABLE IF NOT EXISTS sp500_constituents (
    symbol VARCHAR(20) NOT NULL PRIMARY KEY,
    company_name VARCHAR(500),
    sector VARCHAR(100),
    industry VARCHAR(100),
    weight_pct NUMERIC(8, 4),
    updated_at TIMESTAMP WITH TIME ZONE DEFAULT CURRENT_TIMESTAMP
);

CREATE TABLE IF NOT EXISTS etf_symbols (
    symbol VARCHAR(20) NOT NULL PRIMARY KEY,
    etf_name VARCHAR(500),
    etf_type VARCHAR(50),
    updated_at TIMESTAMP WITH TIME ZONE DEFAULT CURRENT_TIMESTAMP
);

-- ============================================================================
-- TECHNICAL & FUNDAMENTAL DATA
-- ============================================================================

CREATE TABLE IF NOT EXISTS technical_data_daily (
    symbol VARCHAR(20) NOT NULL,
    date DATE NOT NULL,
    sma_50 NUMERIC(12, 4),
    sma_200 NUMERIC(12, 4),
    rsi_14 NUMERIC(6, 2),
    macd_line NUMERIC(12, 4),
    macd_signal NUMERIC(12, 4),
    macd_histogram NUMERIC(12, 4),
    bb_upper NUMERIC(12, 4),
    bb_middle NUMERIC(12, 4),
    bb_lower NUMERIC(12, 4),
    atr_14 NUMERIC(12, 4),
    stochastic_k NUMERIC(6, 2),
    stochastic_d NUMERIC(6, 2),
    updated_at TIMESTAMP WITH TIME ZONE DEFAULT CURRENT_TIMESTAMP,
    PRIMARY KEY (symbol, date)
);
CREATE INDEX IF NOT EXISTS idx_technical_data_daily_symbol ON technical_data_daily(symbol);
CREATE INDEX IF NOT EXISTS idx_technical_data_daily_date ON technical_data_daily(date DESC);

CREATE TABLE IF NOT EXISTS annual_income_statement (
    symbol VARCHAR(20) NOT NULL,
    fiscal_year INTEGER NOT NULL,
    revenue NUMERIC(18, 2),
    operating_income NUMERIC(18, 2),
    net_income NUMERIC(18, 2),
    eps_basic NUMERIC(12, 4),
    eps_diluted NUMERIC(12, 4),
    updated_at TIMESTAMP WITH TIME ZONE DEFAULT CURRENT_TIMESTAMP,
    PRIMARY KEY (symbol, fiscal_year)
);

-- ============================================================================
-- EARNINGS & ANALYST DATA
-- ============================================================================

CREATE TABLE IF NOT EXISTS earnings_calendar (
    symbol VARCHAR(20) NOT NULL,
    earnings_date DATE,
    eps_estimate NUMERIC(12, 4),
    eps_actual NUMERIC(12, 4),
    revenue_estimate NUMERIC(18, 2),
    revenue_actual NUMERIC(18, 2),
    market_cap NUMERIC(18, 2),
    updated_at TIMESTAMP WITH TIME ZONE DEFAULT CURRENT_TIMESTAMP,
    PRIMARY KEY (symbol, earnings_date)
);
CREATE INDEX IF NOT EXISTS idx_earnings_calendar_symbol ON earnings_calendar(symbol);
CREATE INDEX IF NOT EXISTS idx_earnings_calendar_date ON earnings_calendar(earnings_date DESC);

CREATE TABLE IF NOT EXISTS analyst_upgrade_downgrade (
    symbol VARCHAR(20) NOT NULL,
    action_date DATE NOT NULL,
    action VARCHAR(50),
    action_detail TEXT,
    analyst_firm VARCHAR(100),
    old_rating VARCHAR(50),
    new_rating VARCHAR(50),
    price_target NUMERIC(12, 2),
    updated_at TIMESTAMP WITH TIME ZONE DEFAULT CURRENT_TIMESTAMP,
    PRIMARY KEY (symbol, action_date)
);
CREATE INDEX IF NOT EXISTS idx_analyst_upgrade_downgrade_symbol ON analyst_upgrade_downgrade(symbol);
CREATE INDEX IF NOT EXISTS idx_analyst_upgrade_downgrade_date ON analyst_upgrade_downgrade(action_date DESC);

-- ============================================================================
-- SENTIMENT & BREADTH DATA
-- ============================================================================

CREATE TABLE IF NOT EXISTS aaii_sentiment (
    date DATE NOT NULL PRIMARY KEY,
    bullish NUMERIC(5, 2),
    bearish NUMERIC(5, 2),
    neutral NUMERIC(5, 2),
    updated_at TIMESTAMP WITH TIME ZONE DEFAULT CURRENT_TIMESTAMP
);
CREATE INDEX IF NOT EXISTS idx_aaii_sentiment_date ON aaii_sentiment(date DESC);

CREATE TABLE IF NOT EXISTS put_call_ratio_daily (
    date DATE NOT NULL PRIMARY KEY,
    equity_put_call NUMERIC(6, 4),
    index_put_call NUMERIC(6, 4),
    total_put_call NUMERIC(6, 4),
    updated_at TIMESTAMP WITH TIME ZONE DEFAULT CURRENT_TIMESTAMP
);

-- ============================================================================
-- SCHEMA VERSIONING
-- ============================================================================

CREATE TABLE IF NOT EXISTS schema_version (
    id SERIAL PRIMARY KEY,
    version VARCHAR(100) UNIQUE NOT NULL,
    description TEXT,
    applied_at TIMESTAMP WITH TIME ZONE DEFAULT CURRENT_TIMESTAMP,
    rolled_back_at TIMESTAMP WITH TIME ZONE NULL,
    applied_by VARCHAR(255),
    checksum VARCHAR(64)
);
CREATE INDEX IF NOT EXISTS idx_schema_version_version ON schema_version(version);
CREATE INDEX IF NOT EXISTS idx_schema_version_applied_at ON schema_version(applied_at DESC);

-- ============================================================================
-- LOAD TRACKING (For monitoring)
-- ============================================================================

CREATE TABLE IF NOT EXISTS loader_status (
    loader_name VARCHAR(100) NOT NULL PRIMARY KEY,
    last_run_time TIMESTAMP WITH TIME ZONE,
    last_success_time TIMESTAMP WITH TIME ZONE,
    status VARCHAR(50),
    error_message TEXT,
    rows_processed INTEGER,
    rows_failed INTEGER,
    updated_at TIMESTAMP WITH TIME ZONE DEFAULT CURRENT_TIMESTAMP
);

-- CRITICAL: Code references data_loader_status (fix for naming mismatch)
CREATE TABLE IF NOT EXISTS data_loader_status (
    id SERIAL PRIMARY KEY,
    table_name VARCHAR(100) NOT NULL,
    last_run TIMESTAMP WITH TIME ZONE,
    completion_pct NUMERIC(5, 2),
    records_loaded INTEGER,
    records_failed INTEGER,
    error_message TEXT,
    is_complete BOOLEAN DEFAULT FALSE,
    is_stale BOOLEAN DEFAULT FALSE,
    last_updated TIMESTAMP WITH TIME ZONE DEFAULT CURRENT_TIMESTAMP,
    UNIQUE(table_name)
);
CREATE INDEX IF NOT EXISTS idx_data_loader_status_table ON data_loader_status(table_name);
CREATE INDEX IF NOT EXISTS idx_data_loader_status_updated ON data_loader_status(last_updated DESC);

-- Orchestrator run history (distinct from orchestrator_execution_log)
CREATE TABLE IF NOT EXISTS algo_orchestrator_runs (
    run_id VARCHAR(255) PRIMARY KEY,
    run_date DATE NOT NULL,
    overall_status VARCHAR(50),
    started_at TIMESTAMP WITH TIME ZONE,
    completed_at TIMESTAMP WITH TIME ZONE,
    execution_time_seconds NUMERIC(10, 2),
    halt_reason VARCHAR(500),
    phase_results JSONB,
    created_at TIMESTAMP WITH TIME ZONE DEFAULT CURRENT_TIMESTAMP
);
CREATE INDEX IF NOT EXISTS idx_algo_orchestrator_runs_date ON algo_orchestrator_runs(run_date DESC);
CREATE INDEX IF NOT EXISTS idx_algo_orchestrator_runs_status ON algo_orchestrator_runs(overall_status);

-- S&P 500 universe (critical for position tracking)
CREATE TABLE IF NOT EXISTS stock_symbols (
    symbol VARCHAR(20) PRIMARY KEY,
    company_name VARCHAR(255),
    sector VARCHAR(100),
    industry VARCHAR(100),
    market_cap_millions DECIMAL(15, 2),
    is_active BOOLEAN DEFAULT TRUE,
    added_date TIMESTAMP WITH TIME ZONE DEFAULT CURRENT_TIMESTAMP,
    updated_at TIMESTAMP WITH TIME ZONE DEFAULT CURRENT_TIMESTAMP
);
CREATE INDEX IF NOT EXISTS idx_stock_symbols_sector ON stock_symbols(sector);
CREATE INDEX IF NOT EXISTS idx_stock_symbols_active ON stock_symbols(is_active);

-- Company fundamental data for sector/industry lookups
CREATE TABLE IF NOT EXISTS company_profile (
    symbol VARCHAR(20) PRIMARY KEY REFERENCES stock_symbols(symbol) ON DELETE CASCADE,
    company_name VARCHAR(255),
    sector VARCHAR(100),
    industry VARCHAR(100),
    market_cap DECIMAL(18, 2),
    employees INTEGER,
    headquarters VARCHAR(255),
    website VARCHAR(255),
    description TEXT,
    ceo VARCHAR(255),
    exchange VARCHAR(20),
    ipo_date DATE,
    updated_at TIMESTAMP WITH TIME ZONE DEFAULT CURRENT_TIMESTAMP
);
CREATE INDEX IF NOT EXISTS idx_company_profile_sector ON company_profile(sector);

-- ============================================================================
-- TRADING TABLES (Core system - CRITICAL for all functionality)
-- ============================================================================

CREATE TABLE IF NOT EXISTS algo_trades (
    id SERIAL PRIMARY KEY,
    symbol VARCHAR(20) NOT NULL,
    entry_date TIMESTAMP NOT NULL,
    entry_price DECIMAL(12, 4) NOT NULL,
    quantity INTEGER NOT NULL,
    entry_reason VARCHAR(255),
    entry_signal_score DECIMAL(5, 2),
    exit_date TIMESTAMP,
    exit_price DECIMAL(12, 4),
    exit_reason VARCHAR(255),
    status VARCHAR(50) DEFAULT 'open',
    unrealized_pnl DECIMAL(18, 4),
    realized_pnl DECIMAL(18, 4),
    avg_entry_price DECIMAL(12, 4),
    current_price DECIMAL(12, 4),
    position_value DECIMAL(18, 4),
    stop_loss_price DECIMAL(12, 4),
    target_1_price DECIMAL(12, 4),
    target_2_price DECIMAL(12, 4),
    target_3_price DECIMAL(12, 4),
    sector VARCHAR(100),
    created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
    updated_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP
);
CREATE INDEX IF NOT EXISTS idx_algo_trades_symbol_status ON algo_trades(symbol, status);
CREATE INDEX IF NOT EXISTS idx_algo_trades_entry_date ON algo_trades(entry_date DESC);
CREATE INDEX IF NOT EXISTS idx_algo_trades_created_at ON algo_trades(created_at DESC);

CREATE TABLE IF NOT EXISTS algo_positions (
    id SERIAL PRIMARY KEY,
    symbol VARCHAR(20) NOT NULL UNIQUE,
    entry_date TIMESTAMP NOT NULL,
    entry_price DECIMAL(12, 4) NOT NULL,
    quantity INTEGER NOT NULL,
    avg_entry_price DECIMAL(12, 4),
    current_price DECIMAL(12, 4),
    position_value DECIMAL(18, 4),
    unrealized_pnl DECIMAL(18, 4),
    unrealized_pnl_pct DECIMAL(6, 2),
    status VARCHAR(50) DEFAULT 'open',
    stop_loss_price DECIMAL(12, 4),
    target_1_price DECIMAL(12, 4),
    target_2_price DECIMAL(12, 4),
    target_3_price DECIMAL(12, 4),
    sector VARCHAR(100),
    created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
    updated_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP
);
CREATE INDEX IF NOT EXISTS idx_algo_positions_symbol ON algo_positions(symbol);
CREATE INDEX IF NOT EXISTS idx_algo_positions_status ON algo_positions(status);
CREATE INDEX IF NOT EXISTS idx_algo_positions_updated_at ON algo_positions(updated_at DESC);

CREATE TABLE IF NOT EXISTS algo_portfolio_snapshots (
    id SERIAL PRIMARY KEY,
    run_id VARCHAR(100),
    snapshot_date DATE UNIQUE NOT NULL,
    total_portfolio_value DECIMAL(18, 2),
    total_cash DECIMAL(18, 2),
    total_equity DECIMAL(18, 2),
    position_count INTEGER,
    largest_position_pct DECIMAL(8, 4),
    average_position_size_pct DECIMAL(8, 4),
    concentration_risk_pct DECIMAL(8, 4),
    realized_pnl_today DECIMAL(18, 2),
    unrealized_pnl_total DECIMAL(18, 2),
    unrealized_pnl_pct DECIMAL(8, 4),
    unrealized_pnl_winning_count INTEGER,
    unrealized_pnl_losing_count INTEGER,
    unrealized_pnl_breakeven_count INTEGER,
    unrealized_pnl_source VARCHAR(100),
    win_count_today INTEGER,
    loss_count_today INTEGER,
    daily_return_pct DECIMAL(8, 4),
    cumulative_return_pct DECIMAL(8, 4),
    max_drawdown_pct DECIMAL(8, 4),
    sharpe_ratio DECIMAL(8, 4),
    market_health_status VARCHAR(50),
    created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
    updated_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP
);
CREATE INDEX IF NOT EXISTS idx_algo_portfolio_snapshots_run_id ON algo_portfolio_snapshots(run_id);
CREATE INDEX IF NOT EXISTS idx_algo_portfolio_snapshots_date ON algo_portfolio_snapshots(snapshot_date DESC);
CREATE INDEX IF NOT EXISTS idx_algo_portfolio_snapshots_created_at ON algo_portfolio_snapshots(created_at DESC);

-- ============================================================================
-- MATERIALIZED VIEWS (Risk-enhanced position data for Phase 9 reconciliation)
-- ============================================================================

CREATE MATERIALIZED VIEW IF NOT EXISTS algo_positions_with_risk AS
SELECT
    ap.id,
    ap.symbol,
    ap.entry_date,
    ap.entry_price,
    ap.quantity,
    ap.avg_entry_price,
    ap.current_price,
    ap.position_value,
    ap.unrealized_pnl,
    ap.unrealized_pnl_pct,
    ap.status,
    ap.stop_loss_price,
    ap.target_1_price,
    ap.target_2_price,
    ap.target_3_price,
    ap.sector,
    ap.created_at,
    ap.updated_at,
    -- Risk calculations
    CASE
        WHEN ap.entry_price > 0 THEN ((ap.current_price - ap.entry_price) / ap.entry_price * 100)
        ELSE NULL
    END as risk_pct,
    CASE
        WHEN ap.stop_loss_price > 0 AND ap.entry_price > 0 THEN ((ap.entry_price - ap.stop_loss_price) / ap.entry_price * 100)
        ELSE NULL
    END as stop_loss_distance_pct,
    CASE
        WHEN ap.target_1_price > 0 THEN ((ap.target_1_price - ap.entry_price) / ap.entry_price * 100)
        ELSE NULL
    END as target_1_distance_pct,
    -- Stability metrics (if available)
    sm.beta,
    sm.volatility_30d,
    -- Quality metrics (if available)
    qm.quality_score
FROM algo_positions ap
LEFT JOIN stability_metrics sm ON ap.symbol = sm.symbol
LEFT JOIN quality_metrics qm ON ap.symbol = qm.symbol
WHERE ap.status = 'open';

CREATE INDEX IF NOT EXISTS idx_algo_positions_with_risk_symbol ON algo_positions_with_risk(symbol);
CREATE INDEX IF NOT EXISTS idx_algo_positions_with_risk_status ON algo_positions_with_risk(status);

-- ============================================================================
-- DATA PATROL TABLE (Data quality monitoring and phase 1 validation)
-- ============================================================================
-- Phase 1 data freshness check requires this table to exist
-- Stores results from DataPatrol data quality checks

CREATE TABLE IF NOT EXISTS data_patrol_log (
    id SERIAL PRIMARY KEY,
    patrol_run_id VARCHAR(100) NOT NULL,
    check_name VARCHAR(100) NOT NULL,
    severity VARCHAR(20) NOT NULL CHECK (severity IN ('info', 'warning', 'error', 'critical')),
    target_table VARCHAR(100),
    message TEXT,
    details JSONB,
    patrol_date DATE DEFAULT CURRENT_DATE,
    created_at TIMESTAMP WITH TIME ZONE DEFAULT CURRENT_TIMESTAMP
);
CREATE INDEX IF NOT EXISTS idx_data_patrol_log_run_id ON data_patrol_log(patrol_run_id);
CREATE INDEX IF NOT EXISTS idx_data_patrol_log_date ON data_patrol_log(patrol_date DESC);
CREATE INDEX IF NOT EXISTS idx_data_patrol_log_severity ON data_patrol_log(severity);

INSERT INTO algo_config (key, value, data_type, is_critical)
SELECT 'system_initialized', 'true', 'boolean', TRUE
WHERE NOT EXISTS (SELECT 1 FROM algo_config WHERE key = 'system_initialized');
