-- Portfolio Database Schema
-- Created: 2025-07-17
-- Purpose: Store comprehensive portfolio data for financial analysis platform

-- Drop existing tables if they exist (for clean recreation)
DROP TABLE IF EXISTS portfolio_transactions CASCADE;
DROP TABLE IF EXISTS portfolio_performance CASCADE;
DROP TABLE IF EXISTS portfolio_holdings CASCADE;
DROP TABLE IF EXISTS portfolio_metadata CASCADE;
DROP TABLE IF EXISTS user_api_keys CASCADE;
DROP TABLE IF EXISTS stock_symbols_enhanced CASCADE;
DROP TABLE IF EXISTS price_daily CASCADE;
DROP TABLE IF EXISTS trading_alerts CASCADE;

-- Enhanced stock symbols table with additional market data
CREATE TABLE stock_symbols_enhanced (
    id SERIAL PRIMARY KEY,
    symbol VARCHAR(20) NOT NULL UNIQUE,
    company_name VARCHAR(200) NOT NULL,
    exchange VARCHAR(50),
    sector VARCHAR(100),
    industry VARCHAR(150),
    market_cap BIGINT,
    market_cap_tier VARCHAR(20), -- 'large_cap', 'mid_cap', 'small_cap', 'micro_cap'
    country VARCHAR(50) DEFAULT 'US',
    currency VARCHAR(10) DEFAULT 'USD',
    beta DECIMAL(10, 4),
    volatility_30d DECIMAL(10, 4),
    avg_volume_30d BIGINT,
    price_to_earnings DECIMAL(10, 4),
    price_to_book DECIMAL(10, 4),
    dividend_yield DECIMAL(10, 4),
    is_active BOOLEAN DEFAULT true,
    created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
    updated_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP
);

-- Daily price data table
CREATE TABLE price_daily (
    id SERIAL PRIMARY KEY,
    symbol VARCHAR(20) NOT NULL,
    date DATE NOT NULL,
    open_price DECIMAL(12, 4),
    high_price DECIMAL(12, 4),
    low_price DECIMAL(12, 4),
    close_price DECIMAL(12, 4),
    adj_close_price DECIMAL(12, 4),
    volume BIGINT,
    change_amount DECIMAL(12, 4),
    change_percent DECIMAL(10, 4),
    created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
    
    -- Composite unique constraint
    UNIQUE(symbol, date),
    
    -- Foreign key to stock symbols
    FOREIGN KEY (symbol) REFERENCES stock_symbols_enhanced(symbol) ON DELETE CASCADE
);

-- User API keys table for broker connections
CREATE TABLE user_api_keys (
    id SERIAL PRIMARY KEY,
    user_id UUID NOT NULL,
    broker_name VARCHAR(50) NOT NULL,
    encrypted_api_key TEXT NOT NULL,
    encrypted_api_secret TEXT,
    key_iv VARCHAR(32) NOT NULL,
    key_auth_tag VARCHAR(32) NOT NULL,
    secret_iv VARCHAR(32),
    secret_auth_tag VARCHAR(32),
    is_sandbox BOOLEAN DEFAULT true,
    created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
    updated_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
    last_used TIMESTAMP,
    
    -- Composite unique constraint
    UNIQUE(user_id, broker_name)
);

-- Portfolio metadata table
CREATE TABLE portfolio_metadata (
    id SERIAL PRIMARY KEY,
    user_id UUID NOT NULL,
    broker VARCHAR(50) NOT NULL,
    total_value DECIMAL(15, 2) DEFAULT 0,
    total_cash DECIMAL(15, 2) DEFAULT 0,
    total_pnl DECIMAL(15, 2) DEFAULT 0,
    total_pnl_percent DECIMAL(10, 4) DEFAULT 0,
    day_pnl DECIMAL(15, 2) DEFAULT 0,
    day_pnl_percent DECIMAL(10, 4) DEFAULT 0,
    positions_count INTEGER DEFAULT 0,
    buying_power DECIMAL(15, 2) DEFAULT 0,
    account_status VARCHAR(50) DEFAULT 'active',
    environment VARCHAR(20) DEFAULT 'live',
    imported_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
    last_sync TIMESTAMP,
    created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
    updated_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
    
    -- Composite unique constraint
    UNIQUE(user_id, broker)
);

-- Portfolio holdings table
CREATE TABLE portfolio_holdings (
    id SERIAL PRIMARY KEY,
    user_id UUID NOT NULL,
    symbol VARCHAR(20) NOT NULL,
    quantity DECIMAL(15, 6) NOT NULL,
    market_value DECIMAL(15, 2) NOT NULL,
    cost_basis DECIMAL(15, 2) NOT NULL,
    pnl DECIMAL(15, 2) DEFAULT 0,
    pnl_percent DECIMAL(10, 4) DEFAULT 0,
    weight DECIMAL(10, 4) DEFAULT 0, -- Portfolio weight percentage
    sector VARCHAR(100),
    current_price DECIMAL(12, 4),
    average_entry_price DECIMAL(12, 4),
    day_change DECIMAL(15, 2) DEFAULT 0,
    day_change_percent DECIMAL(10, 4) DEFAULT 0,
    exchange VARCHAR(50),
    asset_class VARCHAR(50) DEFAULT 'equity',
    broker VARCHAR(50) NOT NULL,
    last_updated TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
    created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
    
    -- Composite unique constraint
    UNIQUE(user_id, symbol, broker),
    
    -- Foreign key to stock symbols
    FOREIGN KEY (symbol) REFERENCES stock_symbols_enhanced(symbol) ON DELETE CASCADE
);

-- Portfolio performance history table
CREATE TABLE portfolio_performance (
    id SERIAL PRIMARY KEY,
    user_id UUID NOT NULL,
    date DATE NOT NULL,
    total_value DECIMAL(15, 2) NOT NULL,
    daily_pnl DECIMAL(15, 2) DEFAULT 0,
    daily_pnl_percent DECIMAL(10, 4) DEFAULT 0,
    total_pnl DECIMAL(15, 2) DEFAULT 0,
    total_pnl_percent DECIMAL(10, 4) DEFAULT 0,
    benchmark_return DECIMAL(10, 4) DEFAULT 0,
    alpha DECIMAL(10, 4) DEFAULT 0,
    beta DECIMAL(10, 4) DEFAULT 1,
    sharpe_ratio DECIMAL(10, 4) DEFAULT 0,
    max_drawdown DECIMAL(10, 4) DEFAULT 0,
    volatility DECIMAL(10, 4) DEFAULT 0,
    broker VARCHAR(50) NOT NULL,
    created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
    
    -- Composite unique constraint
    UNIQUE(user_id, date, broker)
);

-- Portfolio transactions table
CREATE TABLE portfolio_transactions (
    id SERIAL PRIMARY KEY,
    user_id UUID NOT NULL,
    external_id VARCHAR(100), -- Transaction ID from broker
    symbol VARCHAR(20) NOT NULL,
    transaction_type VARCHAR(50) NOT NULL, -- 'buy', 'sell', 'dividend', 'split', 'transfer'
    side VARCHAR(10), -- 'buy', 'sell'
    quantity DECIMAL(15, 6),
    price DECIMAL(12, 4),
    amount DECIMAL(15, 2) NOT NULL,
    transaction_date TIMESTAMP NOT NULL,
    description TEXT,
    broker VARCHAR(50) NOT NULL,
    status VARCHAR(20) DEFAULT 'completed',
    created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
    updated_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
    
    -- Composite unique constraint for external transactions
    UNIQUE(user_id, external_id, broker),
    
    -- Foreign key to stock symbols
    FOREIGN KEY (symbol) REFERENCES stock_symbols_enhanced(symbol) ON DELETE CASCADE
);

-- Trading alerts table
CREATE TABLE trading_alerts (
    id SERIAL PRIMARY KEY,
    user_id UUID NOT NULL,
    symbol VARCHAR(20) NOT NULL,
    alert_type VARCHAR(50) NOT NULL, -- 'price_target', 'volume_spike', 'technical_signal'
    condition_type VARCHAR(20) NOT NULL, -- 'above', 'below', 'crosses'
    target_value DECIMAL(12, 4),
    current_value DECIMAL(12, 4),
    is_active BOOLEAN DEFAULT true,
    is_triggered BOOLEAN DEFAULT false,
    triggered_at TIMESTAMP,
    message TEXT,
    created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
    updated_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
    
    -- Foreign key to stock symbols
    FOREIGN KEY (symbol) REFERENCES stock_symbols_enhanced(symbol) ON DELETE CASCADE
);

-- Create indexes for performance optimization
CREATE INDEX idx_stock_symbols_enhanced_symbol ON stock_symbols_enhanced(symbol);
CREATE INDEX idx_stock_symbols_enhanced_sector ON stock_symbols_enhanced(sector);
CREATE INDEX idx_stock_symbols_enhanced_market_cap_tier ON stock_symbols_enhanced(market_cap_tier);

CREATE INDEX idx_price_daily_symbol_date ON price_daily(symbol, date DESC);
CREATE INDEX idx_price_daily_date ON price_daily(date DESC);

CREATE INDEX idx_user_api_keys_user_broker ON user_api_keys(user_id, broker_name);
CREATE INDEX idx_user_api_keys_last_used ON user_api_keys(last_used DESC);

CREATE INDEX idx_portfolio_metadata_user_broker ON portfolio_metadata(user_id, broker);
CREATE INDEX idx_portfolio_metadata_last_sync ON portfolio_metadata(last_sync DESC);

CREATE INDEX idx_portfolio_holdings_user_symbol ON portfolio_holdings(user_id, symbol);
CREATE INDEX idx_portfolio_holdings_user_broker ON portfolio_holdings(user_id, broker);
CREATE INDEX idx_portfolio_holdings_symbol ON portfolio_holdings(symbol);

CREATE INDEX idx_portfolio_performance_user_date ON portfolio_performance(user_id, date DESC);
CREATE INDEX idx_portfolio_performance_user_broker ON portfolio_performance(user_id, broker);

CREATE INDEX idx_portfolio_transactions_user_symbol ON portfolio_transactions(user_id, symbol);
CREATE INDEX idx_portfolio_transactions_user_date ON portfolio_transactions(user_id, transaction_date DESC);
CREATE INDEX idx_portfolio_transactions_external_id ON portfolio_transactions(external_id);

CREATE INDEX idx_trading_alerts_user_symbol ON trading_alerts(user_id, symbol);
CREATE INDEX idx_trading_alerts_active ON trading_alerts(is_active) WHERE is_active = true;

-- Insert sample stock symbols data
INSERT INTO stock_symbols_enhanced (symbol, company_name, exchange, sector, industry, market_cap_tier, beta, volatility_30d) VALUES
('AAPL', 'Apple Inc.', 'NASDAQ', 'Technology', 'Consumer Electronics', 'large_cap', 1.20, 25.4),
('MSFT', 'Microsoft Corporation', 'NASDAQ', 'Technology', 'Software', 'large_cap', 0.95, 22.1),
('GOOGL', 'Alphabet Inc.', 'NASDAQ', 'Technology', 'Internet Services', 'large_cap', 1.05, 28.7),
('AMZN', 'Amazon.com Inc.', 'NASDAQ', 'Consumer Discretionary', 'E-commerce', 'large_cap', 1.15, 30.2),
('TSLA', 'Tesla Inc.', 'NASDAQ', 'Consumer Discretionary', 'Electric Vehicles', 'large_cap', 1.85, 45.6),
('META', 'Meta Platforms Inc.', 'NASDAQ', 'Technology', 'Social Media', 'large_cap', 1.25, 32.8),
('NVDA', 'NVIDIA Corporation', 'NASDAQ', 'Technology', 'Semiconductors', 'large_cap', 1.65, 40.3),
('NFLX', 'Netflix Inc.', 'NASDAQ', 'Communication Services', 'Streaming', 'large_cap', 1.35, 35.1),
('JPM', 'JPMorgan Chase & Co.', 'NYSE', 'Financials', 'Banking', 'large_cap', 1.10, 26.4),
('JNJ', 'Johnson & Johnson', 'NYSE', 'Healthcare', 'Pharmaceuticals', 'large_cap', 0.75, 18.2),
('V', 'Visa Inc.', 'NYSE', 'Financials', 'Payment Processing', 'large_cap', 0.90, 20.8),
('PG', 'Procter & Gamble Co.', 'NYSE', 'Consumer Staples', 'Household Products', 'large_cap', 0.65, 16.5),
('UNH', 'UnitedHealth Group Inc.', 'NYSE', 'Healthcare', 'Health Insurance', 'large_cap', 0.85, 19.7),
('HD', 'The Home Depot Inc.', 'NYSE', 'Consumer Discretionary', 'Home Improvement', 'large_cap', 1.00, 24.3),
('DIS', 'The Walt Disney Company', 'NYSE', 'Communication Services', 'Entertainment', 'large_cap', 1.20, 29.5),
('SPY', 'SPDR S&P 500 ETF Trust', 'NYSE', 'ETF', 'Broad Market ETF', 'large_cap', 1.00, 15.0),
('QQQ', 'Invesco QQQ Trust', 'NASDAQ', 'ETF', 'Technology ETF', 'large_cap', 1.15, 20.2),
('VTI', 'Vanguard Total Stock Market ETF', 'NYSE', 'ETF', 'Total Market ETF', 'large_cap', 1.00, 16.1),
('IWM', 'iShares Russell 2000 ETF', 'NYSE', 'ETF', 'Small Cap ETF', 'large_cap', 1.25, 22.7),
('GLD', 'SPDR Gold Shares', 'NYSE', 'ETF', 'Gold ETF', 'large_cap', 0.30, 18.8)
ON CONFLICT (symbol) DO UPDATE SET
    company_name = EXCLUDED.company_name,
    exchange = EXCLUDED.exchange,
    sector = EXCLUDED.sector,
    industry = EXCLUDED.industry,
    market_cap_tier = EXCLUDED.market_cap_tier,
    beta = EXCLUDED.beta,
    volatility_30d = EXCLUDED.volatility_30d,
    updated_at = CURRENT_TIMESTAMP;

-- Insert sample price data for key symbols
INSERT INTO price_daily (symbol, date, open_price, high_price, low_price, close_price, adj_close_price, volume, change_amount, change_percent) VALUES
('AAPL', CURRENT_DATE - INTERVAL '1 day', 175.20, 178.45, 174.80, 177.25, 177.25, 45000000, 2.05, 1.17),
('MSFT', CURRENT_DATE - INTERVAL '1 day', 420.50, 425.30, 418.75, 423.80, 423.80, 22000000, 3.30, 0.78),
('GOOGL', CURRENT_DATE - INTERVAL '1 day', 142.80, 145.25, 141.90, 144.75, 144.75, 28000000, 1.95, 1.37),
('AMZN', CURRENT_DATE - INTERVAL '1 day', 148.30, 151.20, 147.60, 150.40, 150.40, 35000000, 2.10, 1.42),
('TSLA', CURRENT_DATE - INTERVAL '1 day', 245.60, 252.80, 243.10, 250.25, 250.25, 85000000, 4.65, 1.89),
('SPY', CURRENT_DATE - INTERVAL '1 day', 445.20, 447.80, 444.30, 446.95, 446.95, 65000000, 1.75, 0.39),
('QQQ', CURRENT_DATE - INTERVAL '1 day', 385.40, 388.60, 384.20, 387.30, 387.30, 42000000, 1.90, 0.49)
ON CONFLICT (symbol, date) DO UPDATE SET
    open_price = EXCLUDED.open_price,
    high_price = EXCLUDED.high_price,
    low_price = EXCLUDED.low_price,
    close_price = EXCLUDED.close_price,
    adj_close_price = EXCLUDED.adj_close_price,
    volume = EXCLUDED.volume,
    change_amount = EXCLUDED.change_amount,
    change_percent = EXCLUDED.change_percent;

-- Create triggers for automatic timestamp updates
CREATE OR REPLACE FUNCTION update_portfolio_timestamp()
RETURNS TRIGGER AS $$
BEGIN
    NEW.updated_at = CURRENT_TIMESTAMP;
    RETURN NEW;
END;
$$ LANGUAGE plpgsql;

-- Add triggers for automatic timestamp updates
CREATE TRIGGER update_stock_symbols_enhanced_timestamp
    BEFORE UPDATE ON stock_symbols_enhanced
    FOR EACH ROW
    EXECUTE FUNCTION update_portfolio_timestamp();

CREATE TRIGGER update_user_api_keys_timestamp
    BEFORE UPDATE ON user_api_keys
    FOR EACH ROW
    EXECUTE FUNCTION update_portfolio_timestamp();

CREATE TRIGGER update_portfolio_metadata_timestamp
    BEFORE UPDATE ON portfolio_metadata
    FOR EACH ROW
    EXECUTE FUNCTION update_portfolio_timestamp();

CREATE TRIGGER update_portfolio_transactions_timestamp
    BEFORE UPDATE ON portfolio_transactions
    FOR EACH ROW
    EXECUTE FUNCTION update_portfolio_timestamp();

CREATE TRIGGER update_trading_alerts_timestamp
    BEFORE UPDATE ON trading_alerts
    FOR EACH ROW
    EXECUTE FUNCTION update_portfolio_timestamp();

-- Create views for common queries

-- View for portfolio overview
CREATE VIEW portfolio_overview AS
SELECT 
    pm.user_id,
    pm.broker,
    pm.total_value,
    pm.total_cash,
    pm.total_pnl,
    pm.total_pnl_percent,
    pm.day_pnl,
    pm.day_pnl_percent,
    pm.positions_count,
    pm.account_status,
    pm.last_sync,
    COUNT(ph.id) as actual_positions,
    SUM(ph.market_value) as calculated_value
FROM portfolio_metadata pm
LEFT JOIN portfolio_holdings ph ON pm.user_id = ph.user_id AND pm.broker = ph.broker
GROUP BY pm.user_id, pm.broker, pm.total_value, pm.total_cash, pm.total_pnl, 
         pm.total_pnl_percent, pm.day_pnl, pm.day_pnl_percent, pm.positions_count, 
         pm.account_status, pm.last_sync;

-- View for portfolio performance summary
CREATE VIEW portfolio_performance_summary AS
SELECT 
    user_id,
    broker,
    DATE_TRUNC('month', date) as month,
    AVG(total_value) as avg_value,
    MAX(total_value) as max_value,
    MIN(total_value) as min_value,
    AVG(daily_pnl_percent) as avg_daily_return,
    STDDEV(daily_pnl_percent) as volatility,
    MAX(max_drawdown) as max_drawdown,
    AVG(sharpe_ratio) as avg_sharpe_ratio
FROM portfolio_performance
GROUP BY user_id, broker, DATE_TRUNC('month', date)
ORDER BY user_id, broker, month DESC;

-- Add comments for documentation
COMMENT ON TABLE stock_symbols_enhanced IS 'Enhanced stock symbols with market data and metrics';
COMMENT ON TABLE price_daily IS 'Daily price data for stocks and ETFs';
COMMENT ON TABLE user_api_keys IS 'Encrypted API keys for broker connections';
COMMENT ON TABLE portfolio_metadata IS 'Portfolio summary and account information';
COMMENT ON TABLE portfolio_holdings IS 'Individual portfolio positions and holdings';
COMMENT ON TABLE portfolio_performance IS 'Historical portfolio performance data';
COMMENT ON TABLE portfolio_transactions IS 'Portfolio transaction history';
COMMENT ON TABLE trading_alerts IS 'User-defined trading alerts and notifications';

-- Analyze tables for better query planning
ANALYZE stock_symbols_enhanced;
ANALYZE price_daily;
ANALYZE user_api_keys;
ANALYZE portfolio_metadata;
ANALYZE portfolio_holdings;
ANALYZE portfolio_performance;
ANALYZE portfolio_transactions;
ANALYZE trading_alerts;

-- Print confirmation
SELECT 'Portfolio database schema created successfully' as status;