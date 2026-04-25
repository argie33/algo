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
    week_ending DATE NOT NULL,
    open DECIMAL(12, 4),
    high DECIMAL(12, 4),
    low DECIMAL(12, 4),
    close DECIMAL(12, 4),
    volume BIGINT,
    created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
    UNIQUE(symbol, week_ending)
);

-- Monthly price data
CREATE TABLE IF NOT EXISTS price_monthly (
    id SERIAL PRIMARY KEY,
    symbol VARCHAR(20) NOT NULL,
    month_ending DATE NOT NULL,
    open DECIMAL(12, 4),
    high DECIMAL(12, 4),
    low DECIMAL(12, 4),
    close DECIMAL(12, 4),
    volume BIGINT,
    created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
    UNIQUE(symbol, month_ending)
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

-- Earnings history (alias for compatibility)
CREATE TABLE IF NOT EXISTS earnings_history (
    id SERIAL PRIMARY KEY,
    symbol VARCHAR(20),
    quarter DATE,
    fiscal_quarter INTEGER,
    fiscal_year INTEGER,
    earnings_date DATE,
    estimated BOOLEAN,
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
    week_ending DATE NOT NULL,
    signal VARCHAR(20),
    strength DECIMAL(8, 4),
    reason VARCHAR(255),
    created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
    UNIQUE(symbol, week_ending)
);

-- Monthly buy/sell signals
CREATE TABLE IF NOT EXISTS buy_sell_monthly (
    id SERIAL PRIMARY KEY,
    symbol VARCHAR(20) NOT NULL,
    month_ending DATE NOT NULL,
    signal VARCHAR(20),
    strength DECIMAL(8, 4),
    reason VARCHAR(255),
    created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
    UNIQUE(symbol, month_ending)
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
