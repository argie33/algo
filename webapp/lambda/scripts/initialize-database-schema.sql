-- ============================================================================
-- FINANCIAL WEBAPP DATABASE SCHEMA INITIALIZATION
-- ============================================================================
-- This script creates all required tables for the financial webapp
-- Run this script when setting up a new database instance

-- Enable required extensions
CREATE EXTENSION IF NOT EXISTS "uuid-ossp";

-- ============================================================================
-- USER MANAGEMENT TABLES
-- ============================================================================

-- Users table with complete profile and authentication fields
CREATE TABLE IF NOT EXISTS users (
    id VARCHAR(255) PRIMARY KEY,
    username VARCHAR(100) UNIQUE NOT NULL,
    email VARCHAR(255) UNIQUE NOT NULL,
    first_name VARCHAR(100),
    last_name VARCHAR(100),
    phone VARCHAR(20),
    timezone VARCHAR(50) DEFAULT 'America/New_York',
    currency VARCHAR(3) DEFAULT 'USD',
    two_factor_enabled BOOLEAN DEFAULT FALSE,
    two_factor_secret VARCHAR(255),
    recovery_codes TEXT,
    deleted_at TIMESTAMP,
    created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
    updated_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP
);

-- User notification preferences
CREATE TABLE IF NOT EXISTS user_notification_preferences (
    user_id VARCHAR(255) PRIMARY KEY REFERENCES users(id) ON DELETE CASCADE,
    email_notifications BOOLEAN DEFAULT TRUE,
    push_notifications BOOLEAN DEFAULT TRUE,
    price_alerts BOOLEAN DEFAULT TRUE,
    portfolio_updates BOOLEAN DEFAULT TRUE,
    market_news BOOLEAN DEFAULT FALSE,
    weekly_reports BOOLEAN DEFAULT TRUE,
    created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
    updated_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP
);

-- User theme preferences
CREATE TABLE IF NOT EXISTS user_theme_preferences (
    user_id VARCHAR(255) PRIMARY KEY REFERENCES users(id) ON DELETE CASCADE,
    dark_mode BOOLEAN DEFAULT FALSE,
    primary_color VARCHAR(20) DEFAULT '#1976d2',
    chart_style VARCHAR(20) DEFAULT 'candlestick',
    layout VARCHAR(20) DEFAULT 'standard',
    created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
    updated_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP
);

-- ============================================================================
-- STOCK DATA TABLES
-- ============================================================================

-- Main stocks table
CREATE TABLE IF NOT EXISTS stocks (
    ticker VARCHAR(10) PRIMARY KEY,
    company_name VARCHAR(255) NOT NULL,
    short_name VARCHAR(100),
    exchange VARCHAR(10),
    sector VARCHAR(100),
    industry VARCHAR(255),
    market_cap BIGINT,
    shares_outstanding BIGINT,
    price DECIMAL(10,2),
    volume BIGINT,
    avg_volume BIGINT,
    last_updated TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
    created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP
);

-- Stock prices (historical and real-time)
CREATE TABLE IF NOT EXISTS stock_prices (
    id SERIAL PRIMARY KEY,
    symbol VARCHAR(10) NOT NULL,
    date DATE NOT NULL,
    open_price DECIMAL(10,2),
    high_price DECIMAL(10,2),
    low_price DECIMAL(10,2),
    close_price DECIMAL(10,2),
    adjusted_close DECIMAL(10,2),
    volume BIGINT,
    created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
    UNIQUE(symbol, date)
);

-- Real-time market data
CREATE TABLE IF NOT EXISTS market_data (
    symbol VARCHAR(10) PRIMARY KEY,
    current_price DECIMAL(10,2),
    price_change DECIMAL(10,2),
    price_change_percent DECIMAL(5,2),
    day_high DECIMAL(10,2),
    day_low DECIMAL(10,2),
    volume BIGINT,
    avg_volume BIGINT,
    market_cap BIGINT,
    pe_ratio DECIMAL(8,2),
    dividend_yield DECIMAL(5,2),
    last_updated TIMESTAMP DEFAULT CURRENT_TIMESTAMP
);

-- ============================================================================
-- FINANCIAL STATEMENTS TABLES
-- ============================================================================

-- Annual balance sheet
CREATE TABLE IF NOT EXISTS annual_balance_sheet (
    id SERIAL PRIMARY KEY,
    symbol VARCHAR(10) NOT NULL,
    date DATE NOT NULL,
    item_name VARCHAR(255) NOT NULL,
    value DECIMAL(20,2),
    fetched_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
    UNIQUE(symbol, date, item_name)
);

-- Quarterly balance sheet
CREATE TABLE IF NOT EXISTS quarterly_balance_sheet (
    id SERIAL PRIMARY KEY,
    symbol VARCHAR(10) NOT NULL,
    date DATE NOT NULL,
    item_name VARCHAR(255) NOT NULL,
    value DECIMAL(20,2),
    fetched_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
    UNIQUE(symbol, date, item_name)
);

-- Annual income statement
CREATE TABLE IF NOT EXISTS annual_income_statement (
    id SERIAL PRIMARY KEY,
    symbol VARCHAR(10) NOT NULL,
    date DATE NOT NULL,
    item_name VARCHAR(255) NOT NULL,
    value DECIMAL(20,2),
    fetched_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
    UNIQUE(symbol, date, item_name)
);

-- Quarterly income statement
CREATE TABLE IF NOT EXISTS quarterly_income_statement (
    id SERIAL PRIMARY KEY,
    symbol VARCHAR(10) NOT NULL,
    date DATE NOT NULL,
    item_name VARCHAR(255) NOT NULL,
    value DECIMAL(20,2),
    fetched_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
    UNIQUE(symbol, date, item_name)
);

-- TTM income statement
CREATE TABLE IF NOT EXISTS ttm_income_stmt (
    id SERIAL PRIMARY KEY,
    symbol VARCHAR(10) NOT NULL,
    date DATE NOT NULL,
    item_name VARCHAR(255) NOT NULL,
    value DECIMAL(20,2),
    fetched_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
    UNIQUE(symbol, date, item_name)
);

-- Annual cash flow
CREATE TABLE IF NOT EXISTS annual_cash_flow (
    id SERIAL PRIMARY KEY,
    symbol VARCHAR(10) NOT NULL,
    date DATE NOT NULL,
    item_name VARCHAR(255) NOT NULL,
    value DECIMAL(20,2),
    fetched_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
    UNIQUE(symbol, date, item_name)
);

-- Quarterly cash flow
CREATE TABLE IF NOT EXISTS quarterly_cash_flow (
    id SERIAL PRIMARY KEY,
    symbol VARCHAR(10) NOT NULL,
    date DATE NOT NULL,
    item_name VARCHAR(255) NOT NULL,
    value DECIMAL(20,2),
    fetched_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
    UNIQUE(symbol, date, item_name)
);

-- TTM cash flow
CREATE TABLE IF NOT EXISTS ttm_cashflow (
    id SERIAL PRIMARY KEY,
    symbol VARCHAR(10) NOT NULL,
    date DATE NOT NULL,
    item_name VARCHAR(255) NOT NULL,
    value DECIMAL(20,2),
    fetched_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
    UNIQUE(symbol, date, item_name)
);

-- Key metrics
CREATE TABLE IF NOT EXISTS key_metrics (
    ticker VARCHAR(10) PRIMARY KEY,
    trailing_pe DECIMAL(8,2),
    forward_pe DECIMAL(8,2),
    price_to_sales_ttm DECIMAL(8,2),
    price_to_book DECIMAL(8,2),
    book_value DECIMAL(10,2),
    peg_ratio DECIMAL(8,2),
    enterprise_value BIGINT,
    ev_to_revenue DECIMAL(8,2),
    ev_to_ebitda DECIMAL(8,2),
    total_revenue BIGINT,
    net_income BIGINT,
    ebitda BIGINT,
    gross_profit BIGINT,
    eps_trailing DECIMAL(8,2),
    eps_forward DECIMAL(8,2),
    eps_current_year DECIMAL(8,2),
    price_eps_current_year DECIMAL(8,2),
    earnings_q_growth_pct DECIMAL(5,2),
    revenue_growth_pct DECIMAL(5,2),
    earnings_growth_pct DECIMAL(5,2),
    total_cash BIGINT,
    cash_per_share DECIMAL(8,2),
    operating_cashflow BIGINT,
    free_cashflow BIGINT,
    total_debt BIGINT,
    debt_to_equity DECIMAL(8,2),
    quick_ratio DECIMAL(8,2),
    current_ratio DECIMAL(8,2),
    profit_margin_pct DECIMAL(5,2),
    gross_margin_pct DECIMAL(5,2),
    ebitda_margin_pct DECIMAL(5,2),
    operating_margin_pct DECIMAL(5,2),
    return_on_assets_pct DECIMAL(5,2),
    return_on_equity_pct DECIMAL(5,2),
    dividend_rate DECIMAL(8,2),
    dividend_yield DECIMAL(5,2),
    five_year_avg_dividend_yield DECIMAL(5,2),
    payout_ratio DECIMAL(5,2),
    last_updated TIMESTAMP DEFAULT CURRENT_TIMESTAMP
);

-- Earnings history
CREATE TABLE IF NOT EXISTS earnings_history (
    id SERIAL PRIMARY KEY,
    symbol VARCHAR(10) NOT NULL,
    report_date DATE NOT NULL,
    actual_eps DECIMAL(8,2),
    estimated_eps DECIMAL(8,2),
    surprise_percent DECIMAL(5,2),
    revenue_actual BIGINT,
    revenue_estimated BIGINT,
    revenue_surprise_percent DECIMAL(5,2),
    created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
    UNIQUE(symbol, report_date)
);

-- ============================================================================
-- PORTFOLIO MANAGEMENT TABLES
-- ============================================================================

-- User portfolios
CREATE TABLE IF NOT EXISTS portfolios (
    id SERIAL PRIMARY KEY,
    user_id VARCHAR(255) NOT NULL REFERENCES users(id) ON DELETE CASCADE,
    name VARCHAR(255) NOT NULL,
    description TEXT,
    is_default BOOLEAN DEFAULT FALSE,
    total_value DECIMAL(15,2) DEFAULT 0,
    total_cost DECIMAL(15,2) DEFAULT 0,
    total_gain_loss DECIMAL(15,2) DEFAULT 0,
    total_gain_loss_percent DECIMAL(5,2) DEFAULT 0,
    created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
    updated_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP
);

-- Portfolio holdings
CREATE TABLE IF NOT EXISTS portfolio_holdings (
    id SERIAL PRIMARY KEY,
    portfolio_id INTEGER NOT NULL REFERENCES portfolios(id) ON DELETE CASCADE,
    symbol VARCHAR(10) NOT NULL,
    shares DECIMAL(12,4) NOT NULL,
    average_cost DECIMAL(10,2) NOT NULL,
    current_price DECIMAL(10,2),
    total_value DECIMAL(15,2),
    gain_loss DECIMAL(15,2),
    gain_loss_percent DECIMAL(5,2),
    last_updated TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
    created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
    UNIQUE(portfolio_id, symbol)
);

-- Trading transactions
CREATE TABLE IF NOT EXISTS transactions (
    id SERIAL PRIMARY KEY,
    user_id VARCHAR(255) NOT NULL REFERENCES users(id) ON DELETE CASCADE,
    portfolio_id INTEGER REFERENCES portfolios(id) ON DELETE SET NULL,
    symbol VARCHAR(10) NOT NULL,
    transaction_type VARCHAR(10) NOT NULL CHECK (transaction_type IN ('BUY', 'SELL')),
    shares DECIMAL(12,4) NOT NULL,
    price DECIMAL(10,2) NOT NULL,
    total_amount DECIMAL(15,2) NOT NULL,
    fees DECIMAL(10,2) DEFAULT 0,
    transaction_date TIMESTAMP NOT NULL,
    created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP
);

-- Watchlists
CREATE TABLE IF NOT EXISTS watchlists (
    id SERIAL PRIMARY KEY,
    user_id VARCHAR(255) NOT NULL REFERENCES users(id) ON DELETE CASCADE,
    name VARCHAR(255) NOT NULL,
    description TEXT,
    is_default BOOLEAN DEFAULT FALSE,
    created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
    updated_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP
);

-- Watchlist items
CREATE TABLE IF NOT EXISTS watchlist_items (
    id SERIAL PRIMARY KEY,
    watchlist_id INTEGER NOT NULL REFERENCES watchlists(id) ON DELETE CASCADE,
    symbol VARCHAR(10) NOT NULL,
    added_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
    UNIQUE(watchlist_id, symbol)
);

-- ============================================================================
-- API KEY MANAGEMENT TABLES
-- ============================================================================

-- User API keys (legacy table for backward compatibility)
CREATE TABLE IF NOT EXISTS user_api_keys (
    id SERIAL PRIMARY KEY,
    user_id VARCHAR(255) NOT NULL REFERENCES users(id) ON DELETE CASCADE,
    provider VARCHAR(50) NOT NULL,
    api_key_encrypted TEXT NOT NULL,
    api_secret_encrypted TEXT,
    description VARCHAR(255),
    is_sandbox BOOLEAN DEFAULT TRUE,
    is_active BOOLEAN DEFAULT TRUE,
    last_used TIMESTAMP,
    created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
    updated_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
    UNIQUE(user_id, provider)
);

-- ============================================================================
-- MARKET DATA TABLES
-- ============================================================================

-- Sectors and industries
CREATE TABLE IF NOT EXISTS sectors (
    id SERIAL PRIMARY KEY,
    name VARCHAR(100) UNIQUE NOT NULL,
    description TEXT,
    created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP
);

CREATE TABLE IF NOT EXISTS industries (
    id SERIAL PRIMARY KEY,
    sector_id INTEGER REFERENCES sectors(id) ON DELETE SET NULL,
    name VARCHAR(255) UNIQUE NOT NULL,
    description TEXT,
    created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP
);

-- Market indices
CREATE TABLE IF NOT EXISTS market_indices (
    symbol VARCHAR(10) PRIMARY KEY,
    name VARCHAR(255) NOT NULL,
    current_value DECIMAL(10,2),
    change_value DECIMAL(10,2),
    change_percent DECIMAL(5,2),
    last_updated TIMESTAMP DEFAULT CURRENT_TIMESTAMP
);

-- Economic indicators
CREATE TABLE IF NOT EXISTS economic_indicators (
    id SERIAL PRIMARY KEY,
    indicator_name VARCHAR(255) NOT NULL,
    value DECIMAL(15,4),
    date DATE NOT NULL,
    source VARCHAR(100),
    created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
    UNIQUE(indicator_name, date)
);

-- ============================================================================
-- TRADING AND ANALYTICS TABLES
-- ============================================================================

-- Trading signals
CREATE TABLE IF NOT EXISTS trading_signals (
    id SERIAL PRIMARY KEY,
    symbol VARCHAR(10) NOT NULL,
    signal_type VARCHAR(50) NOT NULL,
    signal_strength VARCHAR(20) NOT NULL,
    price_target DECIMAL(10,2),
    stop_loss DECIMAL(10,2),
    confidence DECIMAL(3,1),
    description TEXT,
    generated_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
    expires_at TIMESTAMP
);

-- Backtesting results
CREATE TABLE IF NOT EXISTS backtest_results (
    id SERIAL PRIMARY KEY,
    user_id VARCHAR(255) NOT NULL REFERENCES users(id) ON DELETE CASCADE,
    strategy_name VARCHAR(255) NOT NULL,
    symbol VARCHAR(10) NOT NULL,
    start_date DATE NOT NULL,
    end_date DATE NOT NULL,
    initial_capital DECIMAL(15,2) NOT NULL,
    final_value DECIMAL(15,2) NOT NULL,
    total_return DECIMAL(5,2) NOT NULL,
    max_drawdown DECIMAL(5,2),
    sharpe_ratio DECIMAL(5,2),
    num_trades INTEGER,
    win_rate DECIMAL(5,2),
    avg_trade_return DECIMAL(5,2),
    created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP
);

-- ============================================================================
-- INDEXES FOR PERFORMANCE
-- ============================================================================

-- Stock data indexes
CREATE INDEX IF NOT EXISTS idx_stock_prices_symbol_date ON stock_prices(symbol, date DESC);
CREATE INDEX IF NOT EXISTS idx_market_data_last_updated ON market_data(last_updated DESC);

-- Financial statements indexes
CREATE INDEX IF NOT EXISTS idx_annual_balance_sheet_symbol_date ON annual_balance_sheet(symbol, date DESC);
CREATE INDEX IF NOT EXISTS idx_annual_income_statement_symbol_date ON annual_income_statement(symbol, date DESC);
CREATE INDEX IF NOT EXISTS idx_annual_cash_flow_symbol_date ON annual_cash_flow(symbol, date DESC);

-- Portfolio indexes
CREATE INDEX IF NOT EXISTS idx_portfolio_holdings_portfolio_id ON portfolio_holdings(portfolio_id);
CREATE INDEX IF NOT EXISTS idx_transactions_user_id_date ON transactions(user_id, transaction_date DESC);
CREATE INDEX IF NOT EXISTS idx_watchlist_items_watchlist_id ON watchlist_items(watchlist_id);

-- User management indexes
CREATE INDEX IF NOT EXISTS idx_users_email ON users(email);
CREATE INDEX IF NOT EXISTS idx_users_username ON users(username);

-- ============================================================================
-- SAMPLE DATA FOR TESTING
-- ============================================================================

-- Insert some basic sectors
INSERT INTO sectors (name, description) VALUES 
    ('Technology', 'Technology companies and software'),
    ('Healthcare', 'Healthcare and pharmaceutical companies'),
    ('Finance', 'Banks and financial services'),
    ('Energy', 'Oil, gas, and renewable energy companies'),
    ('Consumer Discretionary', 'Consumer goods and services'),
    ('Industrials', 'Manufacturing and industrial companies')
ON CONFLICT (name) DO NOTHING;

-- Insert sample market indices
INSERT INTO market_indices (symbol, name, current_value, change_value, change_percent) VALUES
    ('SPX', 'S&P 500', 4200.00, 15.25, 0.36),
    ('IXIC', 'NASDAQ Composite', 13000.00, -22.10, -0.17),
    ('DJI', 'Dow Jones Industrial Average', 34000.00, 125.80, 0.37),
    ('RUT', 'Russell 2000', 2000.00, 8.50, 0.43)
ON CONFLICT (symbol) DO NOTHING;

-- Insert popular stocks for testing
INSERT INTO stocks (ticker, company_name, short_name, exchange, sector, industry) VALUES
    ('AAPL', 'Apple Inc.', 'Apple', 'NASDAQ', 'Technology', 'Consumer Electronics'),
    ('GOOGL', 'Alphabet Inc.', 'Google', 'NASDAQ', 'Technology', 'Internet Software'),
    ('MSFT', 'Microsoft Corporation', 'Microsoft', 'NASDAQ', 'Technology', 'Software'),
    ('AMZN', 'Amazon.com Inc.', 'Amazon', 'NASDAQ', 'Consumer Discretionary', 'E-commerce'),
    ('TSLA', 'Tesla, Inc.', 'Tesla', 'NASDAQ', 'Consumer Discretionary', 'Electric Vehicles'),
    ('NVDA', 'NVIDIA Corporation', 'NVIDIA', 'NASDAQ', 'Technology', 'Semiconductors'),
    ('META', 'Meta Platforms, Inc.', 'Meta', 'NASDAQ', 'Technology', 'Social Media'),
    ('JPM', 'JPMorgan Chase & Co.', 'JPMorgan', 'NYSE', 'Finance', 'Banking'),
    ('JNJ', 'Johnson & Johnson', 'J&J', 'NYSE', 'Healthcare', 'Pharmaceuticals'),
    ('V', 'Visa Inc.', 'Visa', 'NYSE', 'Finance', 'Payment Processing')
ON CONFLICT (ticker) DO NOTHING;

-- ============================================================================
-- COMPLETION MESSAGE
-- ============================================================================

-- Log completion
DO $$
BEGIN
    RAISE NOTICE 'Database schema initialization completed successfully!';
    RAISE NOTICE 'Created tables: users, stocks, financial statements, portfolios, and more';
    RAISE NOTICE 'Added indexes for optimal query performance';
    RAISE NOTICE 'Inserted sample data for testing purposes';
END $$;