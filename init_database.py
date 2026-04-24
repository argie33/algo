#!/usr/bin/env python3
"""
Initialize database schema - creates all required tables for loaders
Run this BEFORE running any loaders
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
-- Company profile table (required by most routes for company info)
CREATE TABLE IF NOT EXISTS company_profile (
    ticker VARCHAR(20) PRIMARY KEY,
    short_name VARCHAR(255),
    long_name VARCHAR(255),
    display_name VARCHAR(255),
    quote_type VARCHAR(50),
    symbol_type VARCHAR(50),
    triggerable BOOLEAN,
    has_pre_post_market_data BOOLEAN,
    price_hint INTEGER,
    max_age_sec INTEGER,
    language VARCHAR(10),
    region VARCHAR(50),
    financial_currency VARCHAR(10),
    currency VARCHAR(10),
    market VARCHAR(50),
    quote_source_name VARCHAR(100),
    custom_price_alert_confidence FLOAT,
    address1 VARCHAR(255),
    city VARCHAR(100),
    state VARCHAR(100),
    postal_code VARCHAR(20),
    country VARCHAR(100),
    phone_number VARCHAR(30),
    website_url VARCHAR(255),
    ir_website_url VARCHAR(255),
    message_board_id VARCHAR(100),
    corporate_actions JSONB,
    sector VARCHAR(100),
    sector_key VARCHAR(100),
    sector_disp VARCHAR(100),
    industry VARCHAR(100),
    industry_key VARCHAR(100),
    industry_disp VARCHAR(100),
    business_summary TEXT,
    employee_count BIGINT,
    first_trade_date_ms BIGINT,
    gmt_offset_ms BIGINT,
    exchange VARCHAR(50),
    full_exchange_name VARCHAR(100),
    exchange_timezone_name VARCHAR(100),
    exchange_timezone_short_name VARCHAR(20),
    exchange_data_delayed_by_sec INTEGER,
    post_market_time_ms BIGINT,
    regular_market_time_ms BIGINT,
    created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
    updated_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP
);

-- Key metrics table (required by most loaders)
CREATE TABLE IF NOT EXISTS key_metrics (
    ticker VARCHAR(20) PRIMARY KEY,
    market_cap BIGINT,
    employees INTEGER,
    sector VARCHAR(100),
    industry VARCHAR(100),
    website VARCHAR(255),
    currency_code VARCHAR(10),
    quote_type VARCHAR(50),
    exchange VARCHAR(20),
    short_name VARCHAR(255),
    long_name VARCHAR(255),
    created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
    updated_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP
);

-- Ensure stock_symbols table exists
CREATE TABLE IF NOT EXISTS stock_symbols (
    symbol VARCHAR(20) PRIMARY KEY,
    exchange VARCHAR(50),
    security_name VARCHAR(255),
    cqs_symbol VARCHAR(20),
    market_category VARCHAR(50),
    test_issue VARCHAR(10),
    financial_status VARCHAR(50),
    round_lot_size INTEGER,
    etf CHAR(1),
    secondary_symbol VARCHAR(20),
    created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
    updated_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP
);

-- Annual financial statements
CREATE TABLE IF NOT EXISTS annual_income_statement (
    id SERIAL PRIMARY KEY,
    symbol VARCHAR(20) NOT NULL,
    fiscal_year INTEGER,
    revenue BIGINT,
    cost_of_revenue BIGINT,
    gross_profit BIGINT,
    operating_expenses BIGINT,
    operating_income BIGINT,
    net_income BIGINT,
    created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
    UNIQUE(symbol, fiscal_year)
);

CREATE TABLE IF NOT EXISTS annual_balance_sheet (
    id SERIAL PRIMARY KEY,
    symbol VARCHAR(20) NOT NULL,
    fiscal_year INTEGER,
    total_assets BIGINT,
    total_liabilities BIGINT,
    stockholders_equity BIGINT,
    current_assets BIGINT,
    current_liabilities BIGINT,
    created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
    UNIQUE(symbol, fiscal_year)
);

CREATE TABLE IF NOT EXISTS annual_cash_flow (
    id SERIAL PRIMARY KEY,
    symbol VARCHAR(20) NOT NULL,
    fiscal_year INTEGER,
    operating_cash_flow BIGINT,
    capital_expenditures BIGINT,
    free_cash_flow BIGINT,
    created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
    UNIQUE(symbol, fiscal_year)
);

-- Quarterly financial statements
CREATE TABLE IF NOT EXISTS quarterly_income_statement (
    id SERIAL PRIMARY KEY,
    symbol VARCHAR(20) NOT NULL,
    fiscal_year INTEGER,
    fiscal_quarter INTEGER,
    revenue BIGINT,
    net_income BIGINT,
    created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
    UNIQUE(symbol, fiscal_year, fiscal_quarter)
);

CREATE TABLE IF NOT EXISTS quarterly_balance_sheet (
    id SERIAL PRIMARY KEY,
    symbol VARCHAR(20) NOT NULL,
    fiscal_year INTEGER,
    fiscal_quarter INTEGER,
    total_assets BIGINT,
    total_liabilities BIGINT,
    created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
    UNIQUE(symbol, fiscal_year, fiscal_quarter)
);

CREATE TABLE IF NOT EXISTS quarterly_cash_flow (
    id SERIAL PRIMARY KEY,
    symbol VARCHAR(20) NOT NULL,
    fiscal_year INTEGER,
    fiscal_quarter INTEGER,
    operating_cash_flow BIGINT,
    created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
    UNIQUE(symbol, fiscal_year, fiscal_quarter)
);

-- Metric tables
CREATE TABLE IF NOT EXISTS quality_metrics (
    symbol VARCHAR(20) PRIMARY KEY,
    return_on_equity_pct FLOAT,
    return_on_assets_pct FLOAT,
    gross_margin_pct FLOAT,
    debt_to_equity FLOAT,
    current_ratio FLOAT,
    earnings_beat_rate FLOAT,
    created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP
);

CREATE TABLE IF NOT EXISTS growth_metrics (
    symbol VARCHAR(20) PRIMARY KEY,
    revenue_growth_3y_cagr FLOAT,
    eps_growth_3y_cagr FLOAT,
    fcf_growth_yoy FLOAT,
    created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP
);

CREATE TABLE IF NOT EXISTS value_metrics (
    symbol VARCHAR(20) PRIMARY KEY,
    trailing_pe FLOAT,
    forward_pe FLOAT,
    price_to_book FLOAT,
    price_to_sales_ttm FLOAT,
    dividend_yield FLOAT,
    created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP
);

CREATE TABLE IF NOT EXISTS stability_metrics (
    symbol VARCHAR(20),
    date DATE,
    volatility_12m FLOAT,
    downside_volatility FLOAT,
    max_drawdown_52w FLOAT,
    beta FLOAT,
    volume_consistency FLOAT,
    turnover_velocity FLOAT,
    volatility_volume_ratio FLOAT,
    daily_spread FLOAT,
    created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
    PRIMARY KEY (symbol, date)
);

CREATE TABLE IF NOT EXISTS momentum_metrics (
    symbol VARCHAR(20),
    date DATE,
    momentum_1m FLOAT,
    momentum_3m FLOAT,
    momentum_6m FLOAT,
    momentum_12m FLOAT,
    price_vs_sma_50 FLOAT,
    price_vs_sma_200 FLOAT,
    price_vs_52w_high FLOAT,
    created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
    PRIMARY KEY (symbol, date)
);

CREATE TABLE IF NOT EXISTS positioning_metrics (
    symbol VARCHAR(20) PRIMARY KEY,
    date DATE,
    institutional_ownership_pct FLOAT,
    institutional_holders_count INTEGER,
    insider_ownership_pct FLOAT,
    short_ratio FLOAT,
    short_interest_pct FLOAT,
    short_percent_of_float FLOAT,
    ad_rating FLOAT,
    created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP
);

-- Price data
CREATE TABLE IF NOT EXISTS price_daily (
    symbol VARCHAR(20),
    date DATE,
    open FLOAT,
    high FLOAT,
    low FLOAT,
    close FLOAT,
    adj_close FLOAT,
    volume BIGINT,
    dividends FLOAT DEFAULT 0,
    stock_splits FLOAT DEFAULT 0,
    created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
    PRIMARY KEY (symbol, date)
);

CREATE TABLE IF NOT EXISTS price_weekly (
    symbol VARCHAR(20),
    date DATE,
    open FLOAT,
    high FLOAT,
    low FLOAT,
    close FLOAT,
    adj_close FLOAT,
    volume BIGINT,
    created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
    PRIMARY KEY (symbol, date)
);

CREATE TABLE IF NOT EXISTS price_monthly (
    symbol VARCHAR(20),
    date DATE,
    open FLOAT,
    high FLOAT,
    low FLOAT,
    close FLOAT,
    adj_close FLOAT,
    volume BIGINT,
    created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
    PRIMARY KEY (symbol, date)
);

-- Trading signals
CREATE TABLE IF NOT EXISTS buy_sell_daily (
    id SERIAL PRIMARY KEY,
    symbol VARCHAR(20),
    timeframe VARCHAR(10),
    date DATE,
    signal VARCHAR(10),
    signal_triggered_date DATE,
    strength FLOAT,
    created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
    UNIQUE(symbol, date)
);

CREATE TABLE IF NOT EXISTS buy_sell_weekly (
    id SERIAL PRIMARY KEY,
    symbol VARCHAR(20),
    timeframe VARCHAR(10),
    date DATE,
    signal VARCHAR(10),
    signal_triggered_date DATE,
    strength FLOAT,
    created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
    UNIQUE(symbol, date)
);

CREATE TABLE IF NOT EXISTS buy_sell_monthly (
    id SERIAL PRIMARY KEY,
    symbol VARCHAR(20),
    timeframe VARCHAR(10),
    date DATE,
    signal VARCHAR(10),
    signal_triggered_date DATE,
    strength FLOAT,
    created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
    UNIQUE(symbol, date)
);

-- Stock scores
CREATE TABLE IF NOT EXISTS stock_scores (
    symbol VARCHAR(20) PRIMARY KEY,
    quality_score FLOAT,
    growth_score FLOAT,
    value_score FLOAT,
    stability_score FLOAT,
    momentum_score FLOAT,
    positioning_score FLOAT,
    composite_score FLOAT,
    percentile_rank FLOAT,
    created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP
);

-- Earnings history table (required by signals routes for earnings dates)
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

-- Analyst data
CREATE TABLE IF NOT EXISTS analyst_upgrade_downgrade (
    id SERIAL PRIMARY KEY,
    symbol VARCHAR(20),
    action_date DATE,
    firm VARCHAR(100),
    old_rating VARCHAR(50),
    new_rating VARCHAR(50),
    action VARCHAR(20),
    created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP
);

-- Other required tables
CREATE TABLE IF NOT EXISTS last_updated (
    script_name VARCHAR(100) PRIMARY KEY,
    last_run TIMESTAMP,
    status VARCHAR(50),
    record_count INTEGER
);

CREATE TABLE IF NOT EXISTS market_data (
    id SERIAL PRIMARY KEY,
    metric_name VARCHAR(100),
    metric_value FLOAT,
    date DATE,
    created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP
);

-- Create indexes for common queries
CREATE INDEX IF NOT EXISTS idx_price_daily_symbol ON price_daily(symbol);
CREATE INDEX IF NOT EXISTS idx_price_daily_date ON price_daily(date);
CREATE INDEX IF NOT EXISTS idx_stock_scores_composite ON stock_scores(composite_score);
CREATE INDEX IF NOT EXISTS idx_buy_sell_symbol ON buy_sell_daily(symbol);
CREATE INDEX IF NOT EXISTS idx_analyst_symbol ON analyst_upgrade_downgrade(symbol);
"""

def init_database():
    """Initialize database schema."""
    try:
        conn = psycopg2.connect(**DB_CONFIG)
        cur = conn.cursor()

        print("Initializing database schema...")

        # Split by semicolon and execute each statement
        statements = [s.strip() for s in SCHEMA.split(';') if s.strip()]

        for i, stmt in enumerate(statements):
            try:
                cur.execute(stmt)
                print(f"  [{i+1}/{len(statements)}] OK")
            except Exception as e:
                print(f"  [{i+1}/{len(statements)}] ERROR: {e}")

        conn.commit()
        print("\nDatabase schema initialized successfully!")

    except Exception as e:
        print(f"ERROR: {e}")
        return False
    finally:
        if conn:
            cur.close()
            conn.close()

    return True

if __name__ == "__main__":
    init_database()
