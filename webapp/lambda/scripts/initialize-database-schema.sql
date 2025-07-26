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
-- HIGH FREQUENCY TRADING (HFT) TABLES
-- ============================================================================

-- HFT Strategies table
CREATE TABLE IF NOT EXISTS hft_strategies (
    id SERIAL PRIMARY KEY,
    user_id VARCHAR(255) NOT NULL REFERENCES users(id),
    name VARCHAR(255) NOT NULL,
    type VARCHAR(50) NOT NULL CHECK (type IN ('scalping', 'momentum', 'arbitrage', 'mean_reversion', 'market_making')),
    symbols TEXT[] NOT NULL, -- Array of symbols this strategy trades
    parameters JSONB NOT NULL, -- Strategy-specific parameters
    risk_parameters JSONB NOT NULL, -- Risk management parameters
    enabled BOOLEAN DEFAULT false,
    paper_trading BOOLEAN DEFAULT true,
    max_position_size DECIMAL(15,8) DEFAULT 1000,
    max_daily_loss DECIMAL(15,2) DEFAULT 500,
    created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
    updated_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
    deployed_at TIMESTAMP,
    last_signal_at TIMESTAMP
);

-- HFT Positions table
CREATE TABLE IF NOT EXISTS hft_positions (
    id SERIAL PRIMARY KEY,
    user_id VARCHAR(255) NOT NULL REFERENCES users(id),
    strategy_id INTEGER NOT NULL REFERENCES hft_strategies(id) ON DELETE CASCADE,
    symbol VARCHAR(20) NOT NULL,
    position_type VARCHAR(10) NOT NULL CHECK (position_type IN ('LONG', 'SHORT')),
    quantity DECIMAL(15,8) NOT NULL,
    entry_price DECIMAL(15,8) NOT NULL,
    current_price DECIMAL(15,8),
    unrealized_pnl DECIMAL(15,2) DEFAULT 0,
    realized_pnl DECIMAL(15,2) DEFAULT 0,
    stop_loss DECIMAL(15,8),
    take_profit DECIMAL(15,8),
    opened_at TIMESTAMP NOT NULL DEFAULT CURRENT_TIMESTAMP,
    closed_at TIMESTAMP,
    status VARCHAR(20) DEFAULT 'OPEN' CHECK (status IN ('OPEN', 'CLOSED', 'PARTIAL')),
    alpaca_position_id VARCHAR(255), -- External broker position ID
    metadata JSONB -- Additional position metadata
);

-- HFT Orders table
CREATE TABLE IF NOT EXISTS hft_orders (
    id SERIAL PRIMARY KEY,
    user_id VARCHAR(255) NOT NULL REFERENCES users(id),
    strategy_id INTEGER NOT NULL REFERENCES hft_strategies(id) ON DELETE CASCADE,
    position_id INTEGER REFERENCES hft_positions(id),
    symbol VARCHAR(20) NOT NULL,
    order_type VARCHAR(20) NOT NULL CHECK (order_type IN ('market', 'limit', 'stop', 'stop_limit')),
    side VARCHAR(10) NOT NULL CHECK (side IN ('BUY', 'SELL')),
    quantity DECIMAL(15,8) NOT NULL,
    price DECIMAL(15,8), -- NULL for market orders
    stop_price DECIMAL(15,8), -- For stop orders
    status VARCHAR(20) DEFAULT 'PENDING' CHECK (status IN ('PENDING', 'SUBMITTED', 'FILLED', 'PARTIAL', 'CANCELLED', 'REJECTED')),
    time_in_force VARCHAR(10) DEFAULT 'IOC' CHECK (time_in_force IN ('IOC', 'GTC', 'DAY', 'FOK')),
    
    -- Execution details
    alpaca_order_id VARCHAR(255), -- External broker order ID
    execution_time_ms INTEGER, -- Execution latency in milliseconds
    filled_quantity DECIMAL(15,8) DEFAULT 0,
    avg_fill_price DECIMAL(15,8),
    commission DECIMAL(10,4) DEFAULT 0,
    
    -- Timestamps
    created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
    submitted_at TIMESTAMP,
    filled_at TIMESTAMP,
    
    -- Additional data
    metadata JSONB -- Order metadata and execution details
);

-- HFT Performance Metrics table
CREATE TABLE IF NOT EXISTS hft_performance_metrics (
    id SERIAL PRIMARY KEY,
    user_id VARCHAR(255) NOT NULL REFERENCES users(id),
    strategy_id INTEGER NOT NULL REFERENCES hft_strategies(id) ON DELETE CASCADE,
    date DATE NOT NULL,
    
    -- Trade statistics
    total_trades INTEGER DEFAULT 0,
    profitable_trades INTEGER DEFAULT 0,
    losing_trades INTEGER DEFAULT 0,
    
    -- P&L metrics
    total_pnl DECIMAL(15,2) DEFAULT 0,
    realized_pnl DECIMAL(15,2) DEFAULT 0,
    unrealized_pnl DECIMAL(15,2) DEFAULT 0,
    commission_paid DECIMAL(10,4) DEFAULT 0,
    
    -- Risk metrics
    max_drawdown DECIMAL(15,2) DEFAULT 0,
    max_daily_loss DECIMAL(15,2) DEFAULT 0,
    var_95 DECIMAL(15,2), -- Value at Risk (95% confidence)
    sharpe_ratio DECIMAL(8,4),
    
    -- Performance metrics
    avg_execution_time_ms DECIMAL(8,2),
    min_execution_time_ms INTEGER,
    max_execution_time_ms INTEGER,
    win_rate DECIMAL(5,4), -- Percentage as decimal (0.0 to 1.0)
    profit_factor DECIMAL(8,4),
    
    -- Volume and activity
    total_volume DECIMAL(15,8) DEFAULT 0,
    avg_trade_size DECIMAL(15,8),
    max_position_size DECIMAL(15,8),
    
    created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
    updated_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
    
    -- Ensure one record per strategy per day
    UNIQUE(strategy_id, date)
);

-- HFT Risk Events table for risk management tracking
CREATE TABLE IF NOT EXISTS hft_risk_events (
    id SERIAL PRIMARY KEY,
    user_id VARCHAR(255) NOT NULL REFERENCES users(id),
    strategy_id INTEGER REFERENCES hft_strategies(id) ON DELETE CASCADE,
    event_type VARCHAR(50) NOT NULL CHECK (event_type IN ('STOP_LOSS', 'TAKE_PROFIT', 'MAX_DRAWDOWN', 'DAILY_LOSS_LIMIT', 'POSITION_LIMIT', 'CIRCUIT_BREAKER', 'POSITION_DISCREPANCY')),
    severity VARCHAR(20) NOT NULL CHECK (severity IN ('LOW', 'MEDIUM', 'HIGH', 'CRITICAL')),
    symbol VARCHAR(20),
    trigger_value DECIMAL(15,8),
    threshold_value DECIMAL(15,8),
    action_taken VARCHAR(100),
    description TEXT,
    created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
    resolved_at TIMESTAMP,
    metadata JSONB
);

-- HFT Market Data table for historical data and backtesting
CREATE TABLE IF NOT EXISTS hft_market_data (
    id SERIAL PRIMARY KEY,
    symbol VARCHAR(20) NOT NULL,
    timestamp TIMESTAMP NOT NULL,
    price DECIMAL(15,8) NOT NULL,
    bid DECIMAL(15,8),
    ask DECIMAL(15,8),
    volume DECIMAL(15,8),
    spread DECIMAL(15,8),
    source VARCHAR(20) DEFAULT 'alpaca',
    latency_ms INTEGER, -- Data latency for HFT analysis
    created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
    
    -- Index for fast time-series queries
    UNIQUE(symbol, timestamp, source)
);

-- HFT Sync Events table for real-time position synchronization tracking
CREATE TABLE IF NOT EXISTS hft_sync_events (
    id SERIAL PRIMARY KEY,
    user_id VARCHAR(255) NOT NULL REFERENCES users(id),
    sync_type VARCHAR(20) NOT NULL CHECK (sync_type IN ('IMMEDIATE', 'BATCHED', 'SCHEDULED', 'MANUAL')),
    reason VARCHAR(50) NOT NULL,
    latency_ms INTEGER NOT NULL,
    synced_count INTEGER DEFAULT 0,
    discrepancy_count INTEGER DEFAULT 0,
    metadata JSONB,
    created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP
);

-- Create indexes for HFT performance optimization
CREATE INDEX IF NOT EXISTS idx_hft_strategies_user_enabled ON hft_strategies(user_id, enabled);
CREATE INDEX IF NOT EXISTS idx_hft_strategies_symbols ON hft_strategies USING GIN(symbols);

CREATE INDEX IF NOT EXISTS idx_hft_positions_user_strategy ON hft_positions(user_id, strategy_id);
CREATE INDEX IF NOT EXISTS idx_hft_positions_symbol_status ON hft_positions(symbol, status);
CREATE INDEX IF NOT EXISTS idx_hft_positions_opened_at ON hft_positions(opened_at);

CREATE INDEX IF NOT EXISTS idx_hft_orders_user_strategy ON hft_orders(user_id, strategy_id);
CREATE INDEX IF NOT EXISTS idx_hft_orders_symbol_status ON hft_orders(symbol, status);
CREATE INDEX IF NOT EXISTS idx_hft_orders_created_at ON hft_orders(created_at);
CREATE INDEX IF NOT EXISTS idx_hft_orders_alpaca_id ON hft_orders(alpaca_order_id);

CREATE INDEX IF NOT EXISTS idx_hft_performance_strategy_date ON hft_performance_metrics(strategy_id, date);
CREATE INDEX IF NOT EXISTS idx_hft_performance_user_date ON hft_performance_metrics(user_id, date);

CREATE INDEX IF NOT EXISTS idx_hft_risk_events_user_created ON hft_risk_events(user_id, created_at);
CREATE INDEX IF NOT EXISTS idx_hft_risk_events_strategy_type ON hft_risk_events(strategy_id, event_type);

CREATE INDEX IF NOT EXISTS idx_hft_market_data_symbol_time ON hft_market_data(symbol, timestamp DESC);
CREATE INDEX IF NOT EXISTS idx_hft_market_data_created_at ON hft_market_data(created_at);

CREATE INDEX IF NOT EXISTS idx_hft_sync_events_user_created ON hft_sync_events(user_id, created_at);
CREATE INDEX IF NOT EXISTS idx_hft_sync_events_type_reason ON hft_sync_events(sync_type, reason);

-- Create triggers for automatic timestamp updates
CREATE OR REPLACE FUNCTION update_updated_at_column()
RETURNS TRIGGER AS $$
BEGIN
    NEW.updated_at = CURRENT_TIMESTAMP;
    RETURN NEW;
END;
$$ language 'plpgsql';

-- Apply triggers to HFT tables
DROP TRIGGER IF EXISTS update_hft_strategies_updated_at ON hft_strategies;
CREATE TRIGGER update_hft_strategies_updated_at 
    BEFORE UPDATE ON hft_strategies 
    FOR EACH ROW EXECUTE FUNCTION update_updated_at_column();

DROP TRIGGER IF EXISTS update_hft_performance_updated_at ON hft_performance_metrics;
CREATE TRIGGER update_hft_performance_updated_at 
    BEFORE UPDATE ON hft_performance_metrics 
    FOR EACH ROW EXECUTE FUNCTION update_updated_at_column();

-- Create views for common HFT queries
CREATE OR REPLACE VIEW hft_active_positions AS
SELECT 
    p.*,
    s.name as strategy_name,
    s.type as strategy_type,
    (p.current_price - p.entry_price) * p.quantity * 
    CASE WHEN p.position_type = 'LONG' THEN 1 ELSE -1 END as unrealized_pnl_calc
FROM hft_positions p
JOIN hft_strategies s ON p.strategy_id = s.id
WHERE p.status = 'OPEN';

CREATE OR REPLACE VIEW hft_daily_performance AS
SELECT 
    pm.*,
    s.name as strategy_name,
    s.type as strategy_type,
    CASE WHEN pm.total_trades > 0 
         THEN pm.profitable_trades::decimal / pm.total_trades 
         ELSE 0 END as win_rate_calc
FROM hft_performance_metrics pm
JOIN hft_strategies s ON pm.strategy_id = s.id
ORDER BY pm.date DESC, pm.total_pnl DESC;

-- ============================================================================
-- COMPLETION MESSAGE
-- ============================================================================

-- Log completion
DO $$
BEGIN
    RAISE NOTICE 'Database schema initialization completed successfully!';
    RAISE NOTICE 'Created tables: users, stocks, portfolios, watchlists, HFT strategies, and more';
    RAISE NOTICE 'Added indexes for optimal query performance including HFT optimizations';
    RAISE NOTICE 'Inserted sample data for testing purposes';
    RAISE NOTICE 'HFT system ready for high-frequency trading operations';
END $$;