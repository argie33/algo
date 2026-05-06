#!/usr/bin/env python3
"""
AUTHORITATIVE Database Schema Initialization

This is the SINGLE SOURCE OF TRUTH for all table definitions.
All loaders must reference this file and insert only into defined columns.

DO NOT modify without updating SCHEMA_DEFINITION.md

Generated: 2026-04-25
Status: ✅ AUTHORITATIVE
"""

import os
import psycopg2
from pathlib import Path
from dotenv import load_dotenv

env_file = Path(__file__).parent / '.env.local'
if env_file.exists():
    load_dotenv(env_file)

DB_CONFIG = {
    "host": os.getenv("DB_HOST", "localhost"),
    "port": int(os.getenv("DB_PORT", 5432)),
    "user": os.getenv("DB_USER", "stocks"),
    "password": os.getenv("DB_PASSWORD", ""),
    "database": os.getenv("DB_NAME", "stocks"),
}

SCHEMA = """
-- ════════════════════════════════════════════════════════════════════════════
-- CORE TABLES - Required for all systems
-- ════════════════════════════════════════════════════════════════════════════

-- Stock symbols and identifiers
CREATE TABLE IF NOT EXISTS stock_symbols (
    symbol VARCHAR(20) PRIMARY KEY,
    exchange VARCHAR(50),
    security_name VARCHAR(255),
    market_category VARCHAR(50),
    is_sp500 BOOLEAN DEFAULT FALSE,
    etf VARCHAR(5),
    created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP
);

-- Daily OHLCV price data
CREATE TABLE IF NOT EXISTS price_daily (
    id SERIAL PRIMARY KEY,
    symbol VARCHAR(20) NOT NULL,
    date DATE NOT NULL,
    open DECIMAL(12, 4),
    high DECIMAL(12, 4),
    low DECIMAL(12, 4),
    close DECIMAL(12, 4),
    volume BIGINT,
    adj_close DECIMAL(12, 4),
    created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
    UNIQUE(symbol, date)
);

-- Weekly price data
CREATE TABLE IF NOT EXISTS price_weekly (
    id SERIAL PRIMARY KEY,
    symbol VARCHAR(20) NOT NULL,
    date DATE NOT NULL,
    open DECIMAL(12, 4),
    high DECIMAL(12, 4),
    low DECIMAL(12, 4),
    close DECIMAL(12, 4),
    volume BIGINT,
    created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
    UNIQUE(symbol, date)
);

-- Monthly price data
CREATE TABLE IF NOT EXISTS price_monthly (
    id SERIAL PRIMARY KEY,
    symbol VARCHAR(20) NOT NULL,
    date DATE NOT NULL,
    open DECIMAL(12, 4),
    high DECIMAL(12, 4),
    low DECIMAL(12, 4),
    close DECIMAL(12, 4),
    volume BIGINT,
    created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
    UNIQUE(symbol, date)
);

-- ════════════════════════════════════════════════════════════════════════════
-- EARNINGS & FINANCIAL DATA
-- ════════════════════════════════════════════════════════════════════════════

-- Historical and forward-looking earnings data
CREATE TABLE IF NOT EXISTS earnings_estimates (
    id SERIAL PRIMARY KEY,
    symbol VARCHAR(20) NOT NULL,
    quarter DATE,
    fiscal_quarter INTEGER,
    fiscal_year INTEGER,
    earnings_date DATE,
    estimated BOOLEAN,
    eps_actual DECIMAL(12, 4),
    revenue_actual DECIMAL(16, 2),
    eps_estimate DECIMAL(12, 4),
    revenue_estimate DECIMAL(16, 2),
    eps_surprise_pct DECIMAL(8, 2),
    revenue_surprise_pct DECIMAL(8, 2),
    eps_difference DECIMAL(12, 4),
    revenue_difference DECIMAL(16, 2),
    beat_miss_flag VARCHAR(20),
    surprise_percent DECIMAL(8, 2),
    estimate_revision_days INTEGER,
    estimate_revision_count INTEGER,
    fetched_at TIMESTAMP,
    created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
    UNIQUE(symbol, quarter)
);

-- Earnings history (actual reported earnings + estimates)
CREATE TABLE IF NOT EXISTS earnings_history (
    id SERIAL PRIMARY KEY,
    symbol VARCHAR(20),
    quarter DATE,
    fiscal_quarter INTEGER,
    fiscal_year INTEGER,
    earnings_date DATE,
    estimated BOOLEAN,
    eps_actual DECIMAL(12, 4),
    revenue_actual DECIMAL(16, 2),
    eps_estimate DECIMAL(12, 4),
    revenue_estimate DECIMAL(16, 2),
    eps_surprise_pct DECIMAL(8, 2),
    revenue_surprise_pct DECIMAL(8, 2),
    eps_difference DECIMAL(12, 4),
    revenue_difference DECIMAL(16, 2),
    beat_miss_flag VARCHAR(20),
    surprise_percent DECIMAL(8, 2),
    estimate_revision_days INTEGER,
    estimate_revision_count INTEGER,
    fetched_at TIMESTAMP,
    created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
    UNIQUE(symbol, quarter)
);

-- ════════════════════════════════════════════════════════════════════════════
-- ANALYST DATA
-- ════════════════════════════════════════════════════════════════════════════

-- Analyst rating changes
CREATE TABLE IF NOT EXISTS analyst_upgrade_downgrade (
    id SERIAL PRIMARY KEY,
    symbol VARCHAR(20) NOT NULL,
    action_date DATE,
    firm VARCHAR(100),
    old_rating VARCHAR(50),
    new_rating VARCHAR(50),
    action VARCHAR(20),
    company_name VARCHAR(255),
    created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP
);

-- Analyst sentiment summary
CREATE TABLE IF NOT EXISTS analyst_sentiment_analysis (
    id SERIAL PRIMARY KEY,
    symbol VARCHAR(20) NOT NULL,
    date DATE,
    analyst_count INTEGER,
    bullish_count INTEGER,
    bearish_count INTEGER,
    neutral_count INTEGER,
    target_price DECIMAL(12, 4),
    current_price DECIMAL(12, 4),
    upside_downside_percent DECIMAL(8, 2),
    created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
    UNIQUE(symbol, date)
);

-- ════════════════════════════════════════════════════════════════════════════
-- TECHNICAL INDICATORS
-- ════════════════════════════════════════════════════════════════════════════

-- Daily technical indicators
CREATE TABLE IF NOT EXISTS technical_data_daily (
    id SERIAL PRIMARY KEY,
    symbol VARCHAR(20) NOT NULL,
    date DATE NOT NULL,
    rsi DECIMAL(8, 4),
    macd DECIMAL(12, 4),
    macd_signal DECIMAL(12, 4),
    macd_hist DECIMAL(12, 4),
    mom DECIMAL(12, 4),
    roc DECIMAL(8, 4),
    roc_10d DECIMAL(8, 4),
    roc_20d DECIMAL(8, 4),
    roc_60d DECIMAL(8, 4),
    roc_120d DECIMAL(8, 4),
    roc_252d DECIMAL(8, 4),
    sma_20 DECIMAL(12, 4),
    sma_50 DECIMAL(12, 4),
    sma_200 DECIMAL(12, 4),
    ema_12 DECIMAL(12, 4),
    ema_26 DECIMAL(12, 4),
    atr DECIMAL(12, 4),
    adx DECIMAL(8, 4),
    plus_di DECIMAL(8, 4),
    minus_di DECIMAL(8, 4),
    mansfield_rs DECIMAL(8, 4),
    created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
    UNIQUE(symbol, date)
);

-- Weekly technical indicators
CREATE TABLE IF NOT EXISTS technical_data_weekly (
    id SERIAL PRIMARY KEY,
    symbol VARCHAR(20) NOT NULL,
    date DATE NOT NULL,
    rsi DECIMAL(8, 4),
    macd DECIMAL(12, 4),
    macd_signal DECIMAL(12, 4),
    macd_hist DECIMAL(12, 4),
    sma_20 DECIMAL(12, 4),
    sma_50 DECIMAL(12, 4),
    sma_200 DECIMAL(12, 4),
    ema_12 DECIMAL(12, 4),
    ema_26 DECIMAL(12, 4),
    atr DECIMAL(12, 4),
    adx DECIMAL(8, 4),
    created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
    UNIQUE(symbol, date)
);

-- Monthly technical indicators
CREATE TABLE IF NOT EXISTS technical_data_monthly (
    id SERIAL PRIMARY KEY,
    symbol VARCHAR(20) NOT NULL,
    date DATE NOT NULL,
    rsi DECIMAL(8, 4),
    macd DECIMAL(12, 4),
    macd_signal DECIMAL(12, 4),
    macd_hist DECIMAL(12, 4),
    sma_20 DECIMAL(12, 4),
    sma_50 DECIMAL(12, 4),
    sma_200 DECIMAL(12, 4),
    ema_12 DECIMAL(12, 4),
    ema_26 DECIMAL(12, 4),
    atr DECIMAL(12, 4),
    adx DECIMAL(8, 4),
    created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
    UNIQUE(symbol, date)
);

-- ════════════════════════════════════════════════════════════════════════════
-- TRADING SIGNALS
-- ════════════════════════════════════════════════════════════════════════════

-- Daily buy/sell signals
CREATE TABLE IF NOT EXISTS buy_sell_daily (
    id SERIAL PRIMARY KEY,
    symbol VARCHAR(20) NOT NULL,
    date DATE NOT NULL,
    signal VARCHAR(20),
    strength DECIMAL(8, 4),
    reason VARCHAR(255),
    created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
    UNIQUE(symbol, date)
);

-- Weekly buy/sell signals
CREATE TABLE IF NOT EXISTS buy_sell_weekly (
    id SERIAL PRIMARY KEY,
    symbol VARCHAR(20) NOT NULL,
    date DATE NOT NULL,
    signal VARCHAR(20),
    strength DECIMAL(8, 4),
    reason VARCHAR(255),
    created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
    UNIQUE(symbol, date)
);

-- Monthly buy/sell signals
CREATE TABLE IF NOT EXISTS buy_sell_monthly (
    id SERIAL PRIMARY KEY,
    symbol VARCHAR(20) NOT NULL,
    date DATE NOT NULL,
    signal VARCHAR(20),
    strength DECIMAL(8, 4),
    reason VARCHAR(255),
    created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
    UNIQUE(symbol, date)
);

-- ════════════════════════════════════════════════════════════════════════════
-- QUALITY METRICS
-- ════════════════════════════════════════════════════════════════════════════

-- Profitability and efficiency metrics
CREATE TABLE IF NOT EXISTS quality_metrics (
    symbol VARCHAR(20) PRIMARY KEY,
    operating_margin DECIMAL(8, 4),
    net_margin DECIMAL(8, 4),
    roe DECIMAL(8, 4),
    roa DECIMAL(8, 4),
    debt_to_equity DECIMAL(8, 4),
    current_ratio DECIMAL(8, 4),
    quick_ratio DECIMAL(8, 4),
    interest_coverage DECIMAL(8, 4),
    created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP
);

-- Growth metrics
CREATE TABLE IF NOT EXISTS growth_metrics (
    symbol VARCHAR(20) PRIMARY KEY,
    revenue_growth_5y DECIMAL(8, 4),
    revenue_growth_3y DECIMAL(8, 4),
    revenue_growth_1y DECIMAL(8, 4),
    eps_growth_5y DECIMAL(8, 4),
    eps_growth_3y DECIMAL(8, 4),
    eps_growth_1y DECIMAL(8, 4),
    created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP
);

-- Stability metrics
CREATE TABLE IF NOT EXISTS stability_metrics (
    symbol VARCHAR(20) PRIMARY KEY,
    volatility_30d DECIMAL(8, 4),
    volatility_60d DECIMAL(8, 4),
    volatility_252d DECIMAL(8, 4),
    beta DECIMAL(8, 4),
    debt_to_assets DECIMAL(8, 4),
    created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP
);

-- Value metrics
CREATE TABLE IF NOT EXISTS value_metrics (
    symbol VARCHAR(20) PRIMARY KEY,
    pe_ratio DECIMAL(8, 4),
    pb_ratio DECIMAL(8, 4),
    ps_ratio DECIMAL(8, 4),
    peg_ratio DECIMAL(8, 4),
    dividend_yield DECIMAL(8, 4),
    fcf_yield DECIMAL(8, 4),
    created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP
);

-- Positioning metrics
CREATE TABLE IF NOT EXISTS positioning_metrics (
    symbol VARCHAR(20) PRIMARY KEY,
    institutional_ownership DECIMAL(8, 4),
    insider_ownership DECIMAL(8, 4),
    short_interest_percent DECIMAL(8, 4),
    shares_short_prior_month BIGINT,
    short_interest_trend VARCHAR(20),
    created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP
);

-- ════════════════════════════════════════════════════════════════════════════
-- COMPOSITE SCORES
-- ════════════════════════════════════════════════════════════════════════════

-- Overall stock quality score
CREATE TABLE IF NOT EXISTS stock_scores (
    id SERIAL PRIMARY KEY,
    symbol VARCHAR(20) NOT NULL UNIQUE,
    composite_score DECIMAL(8, 2),
    quality_score DECIMAL(8, 2),
    growth_score DECIMAL(8, 2),
    stability_score DECIMAL(8, 2),
    value_score DECIMAL(8, 2),
    momentum_score DECIMAL(8, 2),
    positioning_score DECIMAL(8, 2),
    created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
    updated_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP
);

-- ════════════════════════════════════════════════════════════════════════════
-- USER MANAGEMENT & SYSTEM TABLES
-- ════════════════════════════════════════════════════════════════════════════

-- User accounts and authentication
CREATE TABLE IF NOT EXISTS users (
    id SERIAL PRIMARY KEY,
    email VARCHAR(255) UNIQUE NOT NULL,
    username VARCHAR(100) UNIQUE,
    password_hash VARCHAR(255),
    created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
    updated_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP
);

-- User dashboard settings and preferences
CREATE TABLE IF NOT EXISTS user_dashboard_settings (
    user_id INTEGER PRIMARY KEY REFERENCES users(id) ON DELETE CASCADE,
    theme VARCHAR(20) DEFAULT 'light',
    notifications BOOLEAN DEFAULT TRUE,
    preferences JSONB,
    updated_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP
);

-- User alerts for stock price changes
CREATE TABLE IF NOT EXISTS user_alerts (
    id SERIAL PRIMARY KEY,
    user_id INTEGER NOT NULL REFERENCES users(id) ON DELETE CASCADE,
    symbol VARCHAR(20) NOT NULL,
    alert_type VARCHAR(50),
    threshold DECIMAL(12, 4),
    triggered_at TIMESTAMP,
    created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP
);

-- User API keys for integrations
CREATE TABLE IF NOT EXISTS user_api_keys (
    id SERIAL PRIMARY KEY,
    user_id INTEGER NOT NULL REFERENCES users(id) ON DELETE CASCADE,
    broker VARCHAR(50),
    api_key VARCHAR(500),
    api_secret VARCHAR(500),
    created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
    last_used_at TIMESTAMP
);

-- Manual trades entered by users
CREATE TABLE IF NOT EXISTS trades (
    id SERIAL PRIMARY KEY,
    user_id INTEGER,
    symbol VARCHAR(20) NOT NULL,
    side VARCHAR(10),
    quantity DECIMAL(12, 2),
    execution_price DECIMAL(12, 4),
    trade_date DATE,
    created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
    updated_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP
);

-- Manual portfolio positions
CREATE TABLE IF NOT EXISTS manual_positions (
    id SERIAL PRIMARY KEY,
    user_id INTEGER,
    symbol VARCHAR(20) NOT NULL,
    quantity DECIMAL(12, 2),
    average_cost DECIMAL(12, 4),
    updated_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP
);

-- Community feature signups
CREATE TABLE IF NOT EXISTS community_signups (
    id SERIAL PRIMARY KEY,
    email VARCHAR(255) NOT NULL,
    status VARCHAR(20) DEFAULT 'pending',
    subscribed_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP
);

-- Contact form submissions
CREATE TABLE IF NOT EXISTS contact_submissions (
    id SERIAL PRIMARY KEY,
    name VARCHAR(255),
    email VARCHAR(255),
    subject VARCHAR(255),
    message TEXT,
    status VARCHAR(20) DEFAULT 'new',
    submitted_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP
);

-- ════════════════════════════════════════════════════════════════════════════
-- COMPANY & FUNDAMENTAL DATA
-- ════════════════════════════════════════════════════════════════════════════

-- Company profile and basic information
CREATE TABLE IF NOT EXISTS company_profile (
    ticker VARCHAR(20) PRIMARY KEY,
    symbol VARCHAR(20),
    short_name VARCHAR(255),
    long_name VARCHAR(255),
    display_name VARCHAR(255),
    sector VARCHAR(100),
    industry VARCHAR(100),
    exchange VARCHAR(50),
    website VARCHAR(255),
    employees BIGINT,
    currency_code VARCHAR(10),
    created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
    updated_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP
);

-- Key financial metrics per company
CREATE TABLE IF NOT EXISTS key_metrics (
    ticker VARCHAR(20) PRIMARY KEY,
    symbol VARCHAR(20),
    market_cap BIGINT,
    held_percent_insiders DECIMAL(8, 4),
    held_percent_institutions DECIMAL(8, 4),
    created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
    updated_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP
);

-- Insider transaction data
CREATE TABLE IF NOT EXISTS insider_transactions (
    id SERIAL PRIMARY KEY,
    symbol VARCHAR(20) NOT NULL,
    insider_name VARCHAR(255),
    title VARCHAR(255),
    trade_type VARCHAR(20),
    shares BIGINT,
    trade_price DECIMAL(12, 4),
    trade_date DATE,
    created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP
);

-- Institutional ownership positioning
CREATE TABLE IF NOT EXISTS institutional_positioning (
    id SERIAL PRIMARY KEY,
    symbol VARCHAR(20) NOT NULL,
    date DATE,
    shares_held BIGINT,
    percent_held DECIMAL(8, 4),
    change_from_prior BIGINT,
    created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP
);

-- Positioning metrics summary
CREATE TABLE IF NOT EXISTS positioning_metrics (
    symbol VARCHAR(20) PRIMARY KEY,
    institutional_ownership DECIMAL(8, 4),
    insider_ownership DECIMAL(8, 4),
    short_interest_percent DECIMAL(8, 4),
    shares_short_prior_month BIGINT,
    created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP
);

-- ════════════════════════════════════════════════════════════════════════════
-- COMMODITY & MARKET DATA
-- ════════════════════════════════════════════════════════════════════════════

-- Commodity prices and data
CREATE TABLE IF NOT EXISTS commodity_prices (
    id SERIAL PRIMARY KEY,
    symbol VARCHAR(20) NOT NULL,
    name VARCHAR(255),
    price DECIMAL(12, 4),
    date DATE,
    created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP
);

-- Commodity price history
CREATE TABLE IF NOT EXISTS commodity_price_history (
    id SERIAL PRIMARY KEY,
    symbol VARCHAR(20) NOT NULL,
    date DATE,
    open DECIMAL(12, 4),
    high DECIMAL(12, 4),
    low DECIMAL(12, 4),
    close DECIMAL(12, 4),
    volume BIGINT,
    created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP
);

-- Commodity categories and relationships
CREATE TABLE IF NOT EXISTS commodity_categories (
    id SERIAL PRIMARY KEY,
    category VARCHAR(100),
    symbols TEXT
);

-- COT (Commitments of Traders) data
CREATE TABLE IF NOT EXISTS cot_data (
    id SERIAL PRIMARY KEY,
    symbol VARCHAR(20) NOT NULL,
    date DATE,
    commercial_long BIGINT,
    commercial_short BIGINT,
    non_commercial_long BIGINT,
    non_commercial_short BIGINT,
    created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP
);

-- Market distribution days
CREATE TABLE IF NOT EXISTS distribution_days (
    id SERIAL PRIMARY KEY,
    symbol VARCHAR(20) NOT NULL,
    date DATE,
    distribution_count INTEGER,
    created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP
);

-- General market data
CREATE TABLE IF NOT EXISTS market_data (
    id SERIAL PRIMARY KEY,
    metric_name VARCHAR(100),
    value DECIMAL(12, 4),
    date DATE,
    created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP
);

-- ════════════════════════════════════════════════════════════════════════════
-- SENTIMENT & PSYCHOLOGICAL DATA
-- ════════════════════════════════════════════════════════════════════════════

-- AAII investor sentiment survey
CREATE TABLE IF NOT EXISTS aaii_sentiment (
    id SERIAL PRIMARY KEY,
    date DATE UNIQUE,
    bullish DECIMAL(8, 4),
    neutral DECIMAL(8, 4),
    bearish DECIMAL(8, 4),
    created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP
);

-- NAAIM market strategists index
CREATE TABLE IF NOT EXISTS naaim (
    id SERIAL PRIMARY KEY,
    date DATE UNIQUE,
    naaim_number_mean DECIMAL(8, 4),
    bullish DECIMAL(8, 4),
    bearish DECIMAL(8, 4),
    created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP
);

-- Fear and Greed Index
CREATE TABLE IF NOT EXISTS fear_greed_index (
    id SERIAL PRIMARY KEY,
    date DATE UNIQUE,
    fear_greed_value DECIMAL(8, 4),
    fear_greed_label VARCHAR(50),
    created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP
);

-- Analyst sentiment analysis for stocks
CREATE TABLE IF NOT EXISTS analyst_sentiment_analysis (
    id SERIAL PRIMARY KEY,
    symbol VARCHAR(20),
    date DATE,
    analyst_count INTEGER,
    bullish_count INTEGER,
    bearish_count INTEGER,
    neutral_count INTEGER,
    total_analysts INTEGER,
    created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
    UNIQUE(symbol, date)
);

-- ════════════════════════════════════════════════════════════════════════════
-- OPTIONS DATA
-- ════════════════════════════════════════════════════════════════════════════

-- Options chains for stocks
CREATE TABLE IF NOT EXISTS options_chains (
    id SERIAL PRIMARY KEY,
    symbol VARCHAR(20) NOT NULL,
    contract_symbol VARCHAR(50),
    option_type VARCHAR(10),
    expiration_date DATE,
    strike_price DECIMAL(12, 4),
    bid DECIMAL(12, 4),
    ask DECIMAL(12, 4),
    last_price DECIMAL(12, 4),
    volume BIGINT,
    open_interest BIGINT,
    data_date DATE,
    created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP
);

-- Options Greeks (Delta, Gamma, Theta, Vega, Rho)
CREATE TABLE IF NOT EXISTS options_greeks (
    id SERIAL PRIMARY KEY,
    symbol VARCHAR(20) NOT NULL,
    contract_symbol VARCHAR(50),
    delta DECIMAL(8, 4),
    gamma DECIMAL(8, 4),
    theta DECIMAL(8, 4),
    vega DECIMAL(8, 4),
    rho DECIMAL(8, 4),
    data_date DATE,
    created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP
);

-- Implied volatility history
CREATE TABLE IF NOT EXISTS iv_history (
    id SERIAL PRIMARY KEY,
    symbol VARCHAR(20) NOT NULL,
    date DATE,
    iv_30d DECIMAL(8, 4),
    iv_60d DECIMAL(8, 4),
    iv_180d DECIMAL(8, 4),
    created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP
);

-- ════════════════════════════════════════════════════════════════════════════
-- PORTFOLIO & HOLDINGS DATA
-- ════════════════════════════════════════════════════════════════════════════

-- Portfolio holdings for users
CREATE TABLE IF NOT EXISTS portfolio_holdings (
    id SERIAL PRIMARY KEY,
    user_id INTEGER,
    symbol VARCHAR(20) NOT NULL,
    quantity DECIMAL(12, 4),
    average_cost DECIMAL(12, 4),
    current_price DECIMAL(12, 4),
    created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
    updated_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP
);

-- Portfolio performance metrics
CREATE TABLE IF NOT EXISTS portfolio_performance (
    id SERIAL PRIMARY KEY,
    user_id INTEGER,
    date DATE,
    total_value DECIMAL(16, 2),
    total_gain_loss DECIMAL(16, 2),
    total_return_pct DECIMAL(8, 4),
    created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP
);

-- ════════════════════════════════════════════════════════════════════════════
-- ECONOMIC & MARKET INDEX DATA
-- ════════════════════════════════════════════════════════════════════════════

-- Economic calendar events
CREATE TABLE IF NOT EXISTS economic_calendar (
    id SERIAL PRIMARY KEY,
    date DATE,
    event_name VARCHAR(255),
    country VARCHAR(50),
    importance VARCHAR(20),
    forecast DECIMAL(12, 4),
    actual DECIMAL(12, 4),
    previous DECIMAL(12, 4),
    created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP
);

-- Economic data time series
CREATE TABLE IF NOT EXISTS economic_data (
    id SERIAL PRIMARY KEY,
    series_id VARCHAR(50),
    date DATE,
    value DECIMAL(12, 4),
    created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP
);

-- Index metrics (market breadth, etc.)
CREATE TABLE IF NOT EXISTS index_metrics (
    id SERIAL PRIMARY KEY,
    symbol VARCHAR(20) NOT NULL,
    date DATE,
    closing_price DECIMAL(12, 4),
    momentum DECIMAL(8, 4),
    created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP
);

-- ════════════════════════════════════════════════════════════════════════════
-- SECTOR & INDUSTRY ANALYSIS
-- ════════════════════════════════════════════════════════════════════════════

-- Sector performance rankings
CREATE TABLE IF NOT EXISTS sector_ranking (
    id SERIAL PRIMARY KEY,
    sector_name VARCHAR(100),
    date_recorded DATE,
    current_rank INTEGER,
    momentum_score DECIMAL(8, 4),
    created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP
);

-- Sector performance data
CREATE TABLE IF NOT EXISTS sector_performance (
    id SERIAL PRIMARY KEY,
    sector VARCHAR(100),
    date DATE,
    return_pct DECIMAL(8, 4),
    relative_strength DECIMAL(8, 4),
    created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP
);

-- Industry rankings
CREATE TABLE IF NOT EXISTS industry_ranking (
    id SERIAL PRIMARY KEY,
    industry VARCHAR(100),
    date_recorded DATE,
    current_rank INTEGER,
    momentum_score DECIMAL(8, 4),
    created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP
);

-- Industry performance data
CREATE TABLE IF NOT EXISTS industry_performance (
    id SERIAL PRIMARY KEY,
    industry VARCHAR(100),
    date DATE,
    return_pct DECIMAL(8, 4),
    created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP
);

-- ════════════════════════════════════════════════════════════════════════════
-- SEASONALITY DATA
-- ════════════════════════════════════════════════════════════════════════════

-- Day of week seasonality
CREATE TABLE IF NOT EXISTS seasonality_day_of_week (
    id SERIAL PRIMARY KEY,
    symbol VARCHAR(20),
    day_of_week INTEGER,
    avg_return_pct DECIMAL(8, 4),
    win_rate_pct DECIMAL(8, 4),
    created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP
);

-- Monthly seasonality patterns
CREATE TABLE IF NOT EXISTS seasonality_monthly_stats (
    id SERIAL PRIMARY KEY,
    symbol VARCHAR(20),
    month INTEGER,
    avg_return_pct DECIMAL(8, 4),
    win_rate_pct DECIMAL(8, 4),
    created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP
);

-- ════════════════════════════════════════════════════════════════════════════
-- STRATEGY & ANALYSIS DATA
-- ════════════════════════════════════════════════════════════════════════════

-- Covered call opportunities
CREATE TABLE IF NOT EXISTS covered_call_opportunities (
    id SERIAL PRIMARY KEY,
    symbol VARCHAR(20) NOT NULL,
    strike_price DECIMAL(12, 4),
    expiration_date DATE,
    annual_return_pct DECIMAL(8, 4),
    probability_profit DECIMAL(8, 4),
    data_date DATE,
    created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP
);

-- ════════════════════════════════════════════════════════════════════════════
-- EARNINGS & FINANCIAL FORECASTS
-- ════════════════════════════════════════════════════════════════════════════

-- Earnings estimate trends
CREATE TABLE IF NOT EXISTS earnings_estimate_trends (
    id SERIAL PRIMARY KEY,
    symbol VARCHAR(20) NOT NULL,
    quarter DATE,
    fiscal_year INTEGER,
    period VARCHAR(20),
    current_estimate DECIMAL(12, 4),
    prior_estimate DECIMAL(12, 4),
    change_estimate DECIMAL(12, 4),
    created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP
);

-- Earnings estimate revisions
CREATE TABLE IF NOT EXISTS earnings_estimate_revisions (
    id SERIAL PRIMARY KEY,
    symbol VARCHAR(20) NOT NULL,
    quarter DATE,
    fiscal_year INTEGER,
    revision_date DATE,
    estimate_before DECIMAL(12, 4),
    estimate_after DECIMAL(12, 4),
    revision_type VARCHAR(20),
    created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP
);

-- ════════════════════════════════════════════════════════════════════════════
-- ALTERNATIVE METRICS
-- ════════════════════════════════════════════════════════════════════════════

-- Momentum metrics for stocks
CREATE TABLE IF NOT EXISTS momentum_metrics (
    symbol VARCHAR(20) PRIMARY KEY,
    momentum_1m DECIMAL(8, 4),
    momentum_3m DECIMAL(8, 4),
    momentum_6m DECIMAL(8, 4),
    momentum_12m DECIMAL(8, 4),
    created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP
);

-- Beta and volatility validation
CREATE TABLE IF NOT EXISTS beta_validation (
    id SERIAL PRIMARY KEY,
    symbol VARCHAR(20) UNIQUE,
    beta_yfinance DECIMAL(8, 4),
    beta_calculated DECIMAL(8, 4),
    validation_status VARCHAR(50),
    created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP
);

-- ════════════════════════════════════════════════════════════════════════════
-- FINANCIAL STATEMENTS
-- ════════════════════════════════════════════════════════════════════════════

-- Annual income statements
CREATE TABLE IF NOT EXISTS annual_income_statement (
    id SERIAL PRIMARY KEY,
    symbol VARCHAR(20),
    fiscal_year INTEGER,
    revenue DECIMAL(16, 2),
    cost_of_revenue DECIMAL(16, 2),
    gross_profit DECIMAL(16, 2),
    operating_income DECIMAL(16, 2),
    net_income DECIMAL(16, 2),
    earnings_per_share DECIMAL(12, 4),
    created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
    UNIQUE(symbol, fiscal_year)
);

-- Annual balance sheets
CREATE TABLE IF NOT EXISTS annual_balance_sheet (
    id SERIAL PRIMARY KEY,
    symbol VARCHAR(20),
    fiscal_year INTEGER,
    total_assets DECIMAL(16, 2),
    current_assets DECIMAL(16, 2),
    total_liabilities DECIMAL(16, 2),
    stockholders_equity DECIMAL(16, 2),
    created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
    UNIQUE(symbol, fiscal_year)
);

-- Annual cash flows
CREATE TABLE IF NOT EXISTS annual_cash_flow (
    id SERIAL PRIMARY KEY,
    symbol VARCHAR(20),
    fiscal_year INTEGER,
    operating_cash_flow DECIMAL(16, 2),
    investing_cash_flow DECIMAL(16, 2),
    financing_cash_flow DECIMAL(16, 2),
    free_cash_flow DECIMAL(16, 2),
    created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
    UNIQUE(symbol, fiscal_year)
);

-- Quarterly income statements
CREATE TABLE IF NOT EXISTS quarterly_income_statement (
    id SERIAL PRIMARY KEY,
    symbol VARCHAR(20),
    fiscal_year INTEGER,
    fiscal_quarter INTEGER,
    revenue DECIMAL(16, 2),
    net_income DECIMAL(16, 2),
    earnings_per_share DECIMAL(12, 4),
    created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
    UNIQUE(symbol, fiscal_year, fiscal_quarter)
);

-- Quarterly balance sheets
CREATE TABLE IF NOT EXISTS quarterly_balance_sheet (
    id SERIAL PRIMARY KEY,
    symbol VARCHAR(20),
    fiscal_year INTEGER,
    fiscal_quarter INTEGER,
    total_assets DECIMAL(16, 2),
    total_liabilities DECIMAL(16, 2),
    stockholders_equity DECIMAL(16, 2),
    created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
    UNIQUE(symbol, fiscal_year, fiscal_quarter)
);

-- Quarterly cash flows
CREATE TABLE IF NOT EXISTS quarterly_cash_flow (
    id SERIAL PRIMARY KEY,
    symbol VARCHAR(20),
    fiscal_year INTEGER,
    fiscal_quarter INTEGER,
    operating_cash_flow DECIMAL(16, 2),
    free_cash_flow DECIMAL(16, 2),
    created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
    UNIQUE(symbol, fiscal_year, fiscal_quarter)
);

-- TTM (Trailing Twelve Months) income statement
CREATE TABLE IF NOT EXISTS ttm_income_statement (
    id SERIAL PRIMARY KEY,
    symbol VARCHAR(20),
    date DATE,
    item_name VARCHAR(255),
    value DECIMAL(16, 2),
    created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP
);

-- TTM cash flow statement
CREATE TABLE IF NOT EXISTS ttm_cash_flow (
    id SERIAL PRIMARY KEY,
    symbol VARCHAR(20),
    date DATE,
    item_name VARCHAR(255),
    value DECIMAL(16, 2),
    created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP
);

-- ════════════════════════════════════════════════════════════════════════════
-- ETF DATA
-- ════════════════════════════════════════════════════════════════════════════

-- ETF price data - Daily
CREATE TABLE IF NOT EXISTS etf_price_daily (
    id SERIAL PRIMARY KEY,
    symbol VARCHAR(20) NOT NULL,
    date DATE NOT NULL,
    open DECIMAL(12, 4),
    high DECIMAL(12, 4),
    low DECIMAL(12, 4),
    close DECIMAL(12, 4),
    volume BIGINT,
    created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
    UNIQUE(symbol, date)
);

-- ETF price data - Weekly
CREATE TABLE IF NOT EXISTS etf_price_weekly (
    id SERIAL PRIMARY KEY,
    symbol VARCHAR(20) NOT NULL,
    date DATE NOT NULL,
    open DECIMAL(12, 4),
    high DECIMAL(12, 4),
    low DECIMAL(12, 4),
    close DECIMAL(12, 4),
    volume BIGINT,
    created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
    UNIQUE(symbol, date)
);

-- ETF price data - Monthly
CREATE TABLE IF NOT EXISTS etf_price_monthly (
    id SERIAL PRIMARY KEY,
    symbol VARCHAR(20) NOT NULL,
    date DATE NOT NULL,
    open DECIMAL(12, 4),
    high DECIMAL(12, 4),
    low DECIMAL(12, 4),
    close DECIMAL(12, 4),
    volume BIGINT,
    created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
    UNIQUE(symbol, date)
);

-- ETF buy/sell signals - Daily
CREATE TABLE IF NOT EXISTS buy_sell_daily_etf (
    id SERIAL PRIMARY KEY,
    symbol VARCHAR(20) NOT NULL,
    date DATE NOT NULL,
    signal VARCHAR(20),
    strength DECIMAL(8, 4),
    created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
    UNIQUE(symbol, date)
);

-- ETF buy/sell signals - Weekly
CREATE TABLE IF NOT EXISTS buy_sell_weekly_etf (
    id SERIAL PRIMARY KEY,
    symbol VARCHAR(20) NOT NULL,
    date DATE NOT NULL,
    signal VARCHAR(20),
    strength DECIMAL(8, 4),
    created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
    UNIQUE(symbol, date)
);

-- ETF buy/sell signals - Monthly
CREATE TABLE IF NOT EXISTS buy_sell_monthly_etf (
    id SERIAL PRIMARY KEY,
    symbol VARCHAR(20) NOT NULL,
    date DATE NOT NULL,
    signal VARCHAR(20),
    strength DECIMAL(8, 4),
    created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
    UNIQUE(symbol, date)
);

-- ════════════════════════════════════════════════════════════════════════════
-- CALENDAR & NEWS
-- ════════════════════════════════════════════════════════════════════════════

-- Calendar events (earnings, dividends, etc)
CREATE TABLE IF NOT EXISTS calendar_events (
    id SERIAL PRIMARY KEY,
    symbol VARCHAR(20),
    event_type VARCHAR(50),
    event_date DATE,
    event_description VARCHAR(255),
    created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP
);

-- ════════════════════════════════════════════════════════════════════════════
-- SWING TRADING ALGO SYSTEM
-- ════════════════════════════════════════════════════════════════════════════

-- Algo configuration (hot-reload enabled, no restart needed)
CREATE TABLE IF NOT EXISTS algo_config (
    id SERIAL PRIMARY KEY,
    key VARCHAR(100) NOT NULL UNIQUE,
    value TEXT,
    value_type VARCHAR(20),
    description TEXT,
    updated_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
    updated_by VARCHAR(100)
);

-- Market health daily (market breadth, distribution days, trend)
CREATE TABLE IF NOT EXISTS market_health_daily (
    id SERIAL PRIMARY KEY,
    date DATE NOT NULL UNIQUE,
    market_trend VARCHAR(20),
    market_stage INTEGER,
    distribution_days_4w INTEGER,
    distribution_days_20d INTEGER,
    up_volume_percent DECIMAL(8, 2),
    advance_decline_ratio DECIMAL(10, 2),
    new_highs_count INTEGER,
    new_lows_count INTEGER,
    breadth_momentum_10d DECIMAL(8, 4),
    vix_level DECIMAL(8, 2),
    put_call_ratio DECIMAL(8, 4),
    yield_curve_slope DECIMAL(8, 4),
    fed_rate_environment VARCHAR(50),
    market_comment TEXT,
    created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP
);

-- Trend template fields per symbol (52w highs/lows, MA slopes, stages)
CREATE TABLE IF NOT EXISTS trend_template_data (
    id SERIAL PRIMARY KEY,
    symbol VARCHAR(20) NOT NULL,
    date DATE NOT NULL,
    price_52w_high DECIMAL(12, 4),
    price_52w_low DECIMAL(12, 4),
    percent_from_52w_low DECIMAL(8, 2),
    percent_from_52w_high DECIMAL(8, 2),
    sma_50_slope DECIMAL(8, 4),
    sma_200_slope DECIMAL(8, 4),
    price_above_sma50 BOOLEAN,
    price_above_sma200 BOOLEAN,
    sma50_above_sma200 BOOLEAN,
    ma_spread_percent DECIMAL(8, 4),
    minervini_trend_score INTEGER,
    weinstein_stage INTEGER,
    trend_direction VARCHAR(20),
    consolidation_flag BOOLEAN,
    created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
    UNIQUE(symbol, date)
);

-- CAN SLIM fundamentals per symbol
CREATE TABLE IF NOT EXISTS can_slim_metrics (
    symbol VARCHAR(20) PRIMARY KEY,
    eps_growth_current DECIMAL(8, 4),
    eps_growth_5y DECIMAL(8, 4),
    sales_growth_current DECIMAL(8, 4),
    profit_margin DECIMAL(8, 4),
    roe DECIMAL(8, 4),
    institutional_ownership_pct DECIMAL(8, 2),
    shares_float_millions INTEGER,
    new_product_catalyst TEXT,
    relative_price_strength DECIMAL(8, 4),
    can_slim_score INTEGER,
    updated_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP
);

-- VCP detection (Volatility Contraction Pattern)
CREATE TABLE IF NOT EXISTS vcp_patterns (
    id SERIAL PRIMARY KEY,
    symbol VARCHAR(20) NOT NULL,
    date DATE NOT NULL,
    atr_30d_avg DECIMAL(12, 4),
    atr_current DECIMAL(12, 4),
    atr_compression_pct DECIMAL(8, 2),
    range_30d_avg DECIMAL(12, 4),
    range_current DECIMAL(12, 4),
    vcp_strength INTEGER,
    breakout_volume_ratio DECIMAL(8, 2),
    created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
    UNIQUE(symbol, date)
);

-- Signal Quality Score composite ranking
CREATE TABLE IF NOT EXISTS signal_quality_scores (
    id SERIAL PRIMARY KEY,
    symbol VARCHAR(20) NOT NULL,
    date DATE NOT NULL,
    trend_template_score INTEGER,
    base_quality_score INTEGER,
    volume_confirmation_score INTEGER,
    distance_from_high_score INTEGER,
    institutional_ownership_score INTEGER,
    market_stage_score INTEGER,
    vcp_pattern_score INTEGER,
    distribution_days_score INTEGER,
    earnings_proximity_score INTEGER,
    composite_sqs INTEGER,
    rank_vs_all_signals INTEGER,
    created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
    UNIQUE(symbol, date)
);

-- Data completeness score per symbol
CREATE TABLE IF NOT EXISTS data_completeness_scores (
    symbol VARCHAR(20) PRIMARY KEY,
    price_data_pct DECIMAL(8, 2),
    technical_data_pct DECIMAL(8, 2),
    earnings_data_pct DECIMAL(8, 2),
    analyst_coverage_pct DECIMAL(8, 2),
    institutional_data_pct DECIMAL(8, 2),
    composite_completeness_pct DECIMAL(8, 2),
    is_tradeable BOOLEAN,
    completeness_comment TEXT,
    updated_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP
);

-- Theme and correlation tags
CREATE TABLE IF NOT EXISTS signal_themes (
    id SERIAL PRIMARY KEY,
    symbol VARCHAR(20) NOT NULL,
    date DATE NOT NULL,
    sector_theme VARCHAR(100),
    thematic_group VARCHAR(100),
    correlation_cluster VARCHAR(100),
    correlation_to_spy DECIMAL(8, 4),
    correlation_to_qqq DECIMAL(8, 4),
    correlation_to_iwm DECIMAL(8, 4),
    relative_strength_group VARCHAR(50),
    created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
    UNIQUE(symbol, date)
);

-- Signals evaluated through filter pipeline
CREATE TABLE IF NOT EXISTS algo_signals_evaluated (
    id SERIAL PRIMARY KEY,
    signal_date DATE NOT NULL,
    symbol VARCHAR(20) NOT NULL,
    source_table VARCHAR(50),
    source_timeframe VARCHAR(20),
    raw_signal VARCHAR(20),
    entry_price DECIMAL(12, 4),
    filter_tier_1_pass BOOLEAN,
    filter_tier_2_pass BOOLEAN,
    filter_tier_3_pass BOOLEAN,
    filter_tier_4_pass BOOLEAN,
    filter_tier_5_pass BOOLEAN,
    final_signal_quality_score INTEGER,
    final_risk_score DECIMAL(8, 2),
    evaluated_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
    evaluation_reason TEXT,
    created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
    UNIQUE(signal_date, symbol, source_timeframe)
);

-- Trades executed by algo
CREATE TABLE IF NOT EXISTS algo_trades (
    id SERIAL PRIMARY KEY,
    trade_id VARCHAR(100) UNIQUE NOT NULL,
    symbol VARCHAR(20) NOT NULL,
    signal_date DATE NOT NULL,
    trade_date DATE NOT NULL,
    entry_price DECIMAL(12, 4) NOT NULL,
    entry_time TIMESTAMP,
    entry_quantity INTEGER NOT NULL,
    entry_reason TEXT,
    position_size_pct DECIMAL(8, 2),
    stop_loss_price DECIMAL(12, 4),
    stop_loss_method VARCHAR(50),
    target_1_price DECIMAL(12, 4),
    target_1_r_multiple DECIMAL(8, 2),
    target_2_price DECIMAL(12, 4),
    target_2_r_multiple DECIMAL(8, 2),
    target_3_price DECIMAL(12, 4),
    target_3_r_multiple DECIMAL(8, 2),
    status VARCHAR(20),
    exit_date DATE,
    exit_time TIMESTAMP,
    exit_price DECIMAL(12, 4),
    exit_reason VARCHAR(100),
    exit_r_multiple DECIMAL(8, 2),
    profit_loss_dollars DECIMAL(12, 2),
    profit_loss_pct DECIMAL(8, 4),
    trade_duration_days INTEGER,
    execution_mode VARCHAR(20),
    alpaca_order_id VARCHAR(100),
    alpaca_trade_id VARCHAR(100),
    created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
    updated_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
    UNIQUE(symbol, signal_date, entry_price)
);

-- Active positions tracking
CREATE TABLE IF NOT EXISTS algo_positions (
    id SERIAL PRIMARY KEY,
    position_id VARCHAR(100) UNIQUE NOT NULL,
    symbol VARCHAR(20) NOT NULL,
    quantity INTEGER NOT NULL,
    avg_entry_price DECIMAL(12, 4),
    current_price DECIMAL(12, 4),
    position_value DECIMAL(14, 2),
    unrealized_pnl DECIMAL(12, 2),
    unrealized_pnl_pct DECIMAL(8, 4),
    trade_ids VARCHAR(1000),
    trade_ids_arr TEXT[],
    status VARCHAR(20),
    stage_in_exit_plan VARCHAR(50),
    distribution_day_count INTEGER,
    profit_loss_dollars DECIMAL(12, 2),
    trade_duration_days INTEGER,
    days_since_entry INTEGER,
    target_levels_hit INTEGER DEFAULT 0,
    current_stop_price DECIMAL(12, 4),
    updated_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
    closed_at TIMESTAMP,
    created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP
);

-- Daily portfolio snapshots
CREATE TABLE IF NOT EXISTS algo_portfolio_snapshots (
    id SERIAL PRIMARY KEY,
    snapshot_date DATE NOT NULL UNIQUE,
    total_portfolio_value DECIMAL(14, 2),
    total_cash DECIMAL(14, 2),
    total_equity DECIMAL(14, 2),
    position_count INTEGER,
    largest_position_pct DECIMAL(8, 2),
    average_position_size_pct DECIMAL(8, 2),
    concentration_risk_pct DECIMAL(8, 2),
    realized_pnl_today DECIMAL(12, 2),
    unrealized_pnl_total DECIMAL(12, 2),
    unrealized_pnl_pct DECIMAL(8, 4),
    win_count_today INTEGER,
    loss_count_today INTEGER,
    daily_return_pct DECIMAL(8, 4),
    cumulative_return_pct DECIMAL(8, 4),
    max_drawdown_pct DECIMAL(8, 4),
    sharpe_ratio DECIMAL(8, 4),
    distribution_days_market INTEGER,
    market_health_status VARCHAR(50),
    created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP
);

-- Audit log for all algo actions (compliance + debugging)
CREATE TABLE IF NOT EXISTS algo_audit_log (
    id SERIAL PRIMARY KEY,
    action_type VARCHAR(50) NOT NULL,
    symbol VARCHAR(20),
    action_date TIMESTAMP NOT NULL,
    details JSONB,
    actor VARCHAR(100),
    status VARCHAR(20),
    error_message TEXT,
    created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP
);

-- Pyramid add tracking (for position scaling)
CREATE TABLE IF NOT EXISTS algo_trade_adds (
    id SERIAL PRIMARY KEY,
    trade_id VARCHAR(20) NOT NULL,
    add_number INTEGER NOT NULL,
    add_date DATE NOT NULL,
    add_price DECIMAL(15, 4) NOT NULL,
    add_quantity INTEGER NOT NULL,
    fraction_of_original DECIMAL(5, 4),
    r_multiple_at_add DECIMAL(5, 2),
    trigger_reason TEXT,
    created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
    UNIQUE(trade_id, add_number)
);

-- Data loader status monitoring
CREATE TABLE IF NOT EXISTS data_loader_status (
    table_name VARCHAR(80) PRIMARY KEY,
    frequency VARCHAR(20),
    role VARCHAR(80),
    latest_date DATE,
    age_days INTEGER,
    row_count BIGINT,
    stale_threshold_days INTEGER,
    status VARCHAR(20),
    last_audit_at TIMESTAMP,
    error_message TEXT
);

-- Data patrol audit log
CREATE TABLE IF NOT EXISTS data_patrol_log (
    id SERIAL PRIMARY KEY,
    patrol_date DATE NOT NULL,
    check_name VARCHAR(100) NOT NULL,
    severity VARCHAR(20),
    table_name VARCHAR(80),
    status VARCHAR(20),
    details TEXT,
    created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP
);

-- Data remediation log
CREATE TABLE IF NOT EXISTS data_remediation_log (
    id SERIAL PRIMARY KEY,
    remediation_date DATE NOT NULL,
    table_name VARCHAR(80) NOT NULL,
    fix_type VARCHAR(50),
    rows_affected INTEGER,
    status VARCHAR(20),
    error_message TEXT,
    created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP
);

-- Market exposure daily snapshots
CREATE TABLE IF NOT EXISTS market_exposure_daily (
    id SERIAL PRIMARY KEY,
    date DATE NOT NULL,
    market_exposure_pct DECIMAL(8, 4),
    long_exposure_pct DECIMAL(8, 4),
    short_exposure_pct DECIMAL(8, 4),
    exposure_tier VARCHAR(30),
    is_entry_allowed BOOLEAN,
    created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
    UNIQUE(date)
);

-- Notifications for UI
CREATE TABLE IF NOT EXISTS algo_notifications (
    id SERIAL PRIMARY KEY,
    kind VARCHAR(40) NOT NULL,
    severity VARCHAR(20) NOT NULL,
    title VARCHAR(200) NOT NULL,
    message TEXT,
    symbol VARCHAR(20),
    details JSONB,
    seen BOOLEAN DEFAULT FALSE,
    seen_at TIMESTAMP,
    created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP
);

-- Transaction Cost Analysis (TCA) - Execution quality tracking
CREATE TABLE IF NOT EXISTS algo_tca (
    tca_id SERIAL PRIMARY KEY,
    trade_id INTEGER REFERENCES algo_trades(id) ON DELETE CASCADE,
    symbol VARCHAR(10) NOT NULL,
    signal_date DATE NOT NULL,
    signal_price DECIMAL(12, 4) NOT NULL,
    fill_price DECIMAL(12, 4) NOT NULL,
    shares_requested INTEGER NOT NULL,
    shares_filled INTEGER NOT NULL,
    fill_rate_pct DECIMAL(6, 2),
    slippage_bps DECIMAL(10, 2),
    side VARCHAR(4) NOT NULL,
    execution_latency_ms INTEGER,
    created_at TIMESTAMPTZ DEFAULT now()
);

-- Live Performance Metrics - Daily aggregation for institutional comparison
CREATE TABLE IF NOT EXISTS algo_performance_daily (
    report_date DATE PRIMARY KEY,
    rolling_sharpe_252d NUMERIC(8, 4),
    win_rate_50t NUMERIC(6, 2),
    avg_win_r_50t NUMERIC(6, 3),
    avg_loss_r_50t NUMERIC(6, 3),
    expectancy NUMERIC(6, 4),
    max_drawdown_pct NUMERIC(8, 2),
    live_vs_backtest_ratio NUMERIC(6, 4),
    created_at TIMESTAMPTZ DEFAULT now(),
    updated_at TIMESTAMPTZ DEFAULT now()
);

-- Portfolio Risk Metrics - Daily VaR, CVaR, concentration, beta
CREATE TABLE IF NOT EXISTS algo_risk_daily (
    report_date DATE PRIMARY KEY,
    var_pct_95 NUMERIC(8, 3),
    cvar_pct_95 NUMERIC(8, 3),
    stressed_var_pct NUMERIC(8, 3),
    portfolio_beta NUMERIC(6, 2),
    top_5_concentration NUMERIC(6, 2),
    status VARCHAR(20) DEFAULT 'ok',
    created_at TIMESTAMPTZ DEFAULT now(),
    updated_at TIMESTAMPTZ DEFAULT now()
);

-- Sector rotation signals
CREATE TABLE IF NOT EXISTS sector_rotation_signal (
    id SERIAL PRIMARY KEY,
    date DATE NOT NULL,
    sector VARCHAR(50) NOT NULL,
    signal VARCHAR(20),
    strength DECIMAL(8, 4),
    rank INTEGER,
    details JSONB,
    created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
    UNIQUE(date, sector)
);

-- Swing trader scores
CREATE TABLE IF NOT EXISTS swing_trader_scores (
    id SERIAL PRIMARY KEY,
    symbol VARCHAR(20) NOT NULL,
    date DATE NOT NULL,
    score DECIMAL(8, 4),
    components JSONB,
    created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
    UNIQUE(symbol, date)
);

-- Model Registry - Track deployed strategies and parameters
CREATE TABLE IF NOT EXISTS algo_model_registry (
    registry_id SERIAL PRIMARY KEY,
    strategy_name VARCHAR(100) NOT NULL,
    git_commit_hash VARCHAR(40) NOT NULL,
    param_snapshot JSONB NOT NULL,
    backtest_sharpe NUMERIC(8, 4),
    backtest_max_dd NUMERIC(8, 4),
    backtest_win_rate NUMERIC(6, 4),
    walk_forward_efficiency NUMERIC(6, 4),
    paper_sharpe NUMERIC(8, 4),
    paper_period_start DATE,
    paper_period_end DATE,
    deployed_at TIMESTAMPTZ,
    deployed_by VARCHAR(100),
    status VARCHAR(20) DEFAULT 'active',
    notes TEXT,
    created_at TIMESTAMPTZ DEFAULT now()
);

-- Configuration Audit Log - Track all parameter changes
CREATE TABLE IF NOT EXISTS algo_config_audit (
    audit_id SERIAL PRIMARY KEY,
    config_key VARCHAR(100) NOT NULL,
    old_value TEXT,
    new_value TEXT,
    changed_by VARCHAR(100),
    change_reason TEXT,
    changed_at TIMESTAMPTZ DEFAULT now()
);

-- Champion/Challenger Results - A/B test results
CREATE TABLE IF NOT EXISTS algo_champion_challenger (
    trial_id SERIAL PRIMARY KEY,
    trial_date DATE NOT NULL,
    champion_registry_id INTEGER REFERENCES algo_model_registry(registry_id),
    challenger_registry_id INTEGER REFERENCES algo_model_registry(registry_id),
    champion_trades INTEGER,
    challenger_trades INTEGER,
    champion_pnl_pct NUMERIC(8, 2),
    challenger_pnl_pct NUMERIC(8, 2),
    t_statistic NUMERIC(8, 4),
    p_value NUMERIC(8, 6),
    winner VARCHAR(20),
    created_at TIMESTAMPTZ DEFAULT now()
);

-- Information Coefficient - Signal quality metric
CREATE TABLE IF NOT EXISTS algo_information_coefficient (
    ic_date DATE PRIMARY KEY,
    signal_name VARCHAR(100),
    lookback_days INTEGER,
    ic_pearson NUMERIC(8, 4),
    ic_spearman NUMERIC(8, 4),
    ic_interpretation VARCHAR(50),
    created_at TIMESTAMPTZ DEFAULT now()
);

-- ════════════════════════════════════════════════════════════════════════════
-- INDEXES for Performance
-- ════════════════════════════════════════════════════════════════════════════

CREATE INDEX IF NOT EXISTS idx_price_daily_symbol ON price_daily(symbol);
CREATE INDEX IF NOT EXISTS idx_price_daily_date ON price_daily(date);
CREATE INDEX IF NOT EXISTS idx_price_daily_symbol_date ON price_daily(symbol, date);

CREATE INDEX IF NOT EXISTS idx_technical_daily_symbol ON technical_data_daily(symbol);
CREATE INDEX IF NOT EXISTS idx_technical_daily_date ON technical_data_daily(date);

CREATE INDEX IF NOT EXISTS idx_buy_sell_daily_symbol ON buy_sell_daily(symbol);
CREATE INDEX IF NOT EXISTS idx_earnings_symbol ON earnings_estimates(symbol);
CREATE INDEX IF NOT EXISTS idx_analyst_symbol ON analyst_upgrade_downgrade(symbol);
CREATE INDEX IF NOT EXISTS idx_sentiment_symbol ON analyst_sentiment_analysis(symbol);

-- Algo system indexes
CREATE INDEX IF NOT EXISTS idx_market_health_daily_date ON market_health_daily(date);
CREATE INDEX IF NOT EXISTS idx_trend_template_symbol ON trend_template_data(symbol);
CREATE INDEX IF NOT EXISTS idx_trend_template_date ON trend_template_data(date);
CREATE INDEX IF NOT EXISTS idx_vcp_patterns_symbol_date ON vcp_patterns(symbol, date);
CREATE INDEX IF NOT EXISTS idx_signal_quality_symbol_date ON signal_quality_scores(symbol, date);
CREATE INDEX IF NOT EXISTS idx_algo_signals_evaluated_date ON algo_signals_evaluated(signal_date);
CREATE INDEX IF NOT EXISTS idx_algo_signals_evaluated_symbol ON algo_signals_evaluated(symbol);
CREATE INDEX IF NOT EXISTS idx_algo_trades_symbol ON algo_trades(symbol);
CREATE INDEX IF NOT EXISTS idx_algo_trades_status ON algo_trades(status);
CREATE INDEX IF NOT EXISTS idx_algo_positions_symbol ON algo_positions(symbol);
CREATE INDEX IF NOT EXISTS idx_algo_positions_status ON algo_positions(status);
CREATE INDEX IF NOT EXISTS idx_portfolio_snapshots_date ON algo_portfolio_snapshots(snapshot_date);
CREATE INDEX IF NOT EXISTS idx_audit_log_action_type ON algo_audit_log(action_type);
CREATE INDEX IF NOT EXISTS idx_audit_log_date ON algo_audit_log(action_date);

-- Indexes for TCA
CREATE INDEX IF NOT EXISTS idx_algo_tca_trade_id ON algo_tca(trade_id);
CREATE INDEX IF NOT EXISTS idx_algo_tca_symbol ON algo_tca(symbol);
CREATE INDEX IF NOT EXISTS idx_algo_tca_signal_date ON algo_tca(signal_date);

-- Indexes for Performance metrics
CREATE INDEX IF NOT EXISTS idx_algo_performance_daily_date ON algo_performance_daily(report_date);

-- Indexes for Risk metrics
CREATE INDEX IF NOT EXISTS idx_algo_risk_daily_date ON algo_risk_daily(report_date);

-- Indexes for Model Governance
CREATE INDEX IF NOT EXISTS idx_algo_model_registry_commit ON algo_model_registry(git_commit_hash);
CREATE INDEX IF NOT EXISTS idx_algo_model_registry_status ON algo_model_registry(status);
CREATE INDEX IF NOT EXISTS idx_algo_model_registry_deployed_at ON algo_model_registry(deployed_at);
CREATE INDEX IF NOT EXISTS idx_algo_config_audit_key ON algo_config_audit(config_key);
CREATE INDEX IF NOT EXISTS idx_algo_config_audit_date ON algo_config_audit(changed_at);
CREATE INDEX IF NOT EXISTS idx_algo_champion_challenger_date ON algo_champion_challenger(trial_date);
CREATE INDEX IF NOT EXISTS idx_algo_information_coefficient_date ON algo_information_coefficient(ic_date);

-- Indexes for new tables
CREATE INDEX IF NOT EXISTS idx_trade_adds_trade_id ON algo_trade_adds(trade_id);
CREATE INDEX IF NOT EXISTS idx_data_patrol_log_date ON data_patrol_log(patrol_date);
CREATE INDEX IF NOT EXISTS idx_data_patrol_log_severity ON data_patrol_log(severity);
CREATE INDEX IF NOT EXISTS idx_data_remediation_log_date ON data_remediation_log(remediation_date);
CREATE INDEX IF NOT EXISTS idx_market_exposure_daily_date ON market_exposure_daily(date);
CREATE INDEX IF NOT EXISTS idx_notif_unseen ON algo_notifications(seen, created_at) WHERE seen = FALSE;
CREATE INDEX IF NOT EXISTS idx_notif_severity ON algo_notifications(severity);
CREATE INDEX IF NOT EXISTS idx_sector_rotation_date ON sector_rotation_signal(date);
CREATE INDEX IF NOT EXISTS idx_sector_rotation_sector ON sector_rotation_signal(sector);
CREATE INDEX IF NOT EXISTS idx_swing_scores_symbol_date ON swing_trader_scores(symbol, date);
"""

def init_database():
    """Initialize database schema."""
    try:
        conn = psycopg2.connect(**DB_CONFIG)
        cur = conn.cursor()

        print("╔════════════════════════════════════════════════════════╗")
        print("║  Initializing Database Schema (AUTHORITATIVE)         ║")
        print("╚════════════════════════════════════════════════════════╝")
        print()

        # Split by semicolon and execute each statement
        statements = [s.strip() for s in SCHEMA.split(';') if s.strip()]

        succeeded = 0
        failed = 0

        for i, stmt in enumerate(statements, 1):
            try:
                cur.execute(stmt)
                print(f"  ✓ [{i:2d}/{len(statements)}]")
                succeeded += 1
            except Exception as e:
                print(f"  ✗ [{i:2d}/{len(statements)}] {str(e)[:60]}")
                failed += 1

        conn.commit()
        print()
        print(f"✓ Schema initialization complete!")
        print(f"  Succeeded: {succeeded}")
        print(f"  Failed: {failed}")
        print()
        print("Schema is now READY for loaders to use")
        print()
        return failed == 0

    except Exception as e:
        print(f"ERROR: {e}")
        return False
    finally:
        if conn:
            cur.close()
            conn.close()

if __name__ == "__main__":
    import sys
    success = init_database()
    sys.exit(0 if success else 1)
