-- Create missing tables for dashboard functionality
-- These tables are needed for the webapp dashboard to function properly

-- Portfolio Holdings Table
CREATE TABLE IF NOT EXISTS portfolio_holdings (
    id SERIAL PRIMARY KEY,
    user_id VARCHAR(255) NOT NULL,
    symbol VARCHAR(10) NOT NULL,
    quantity NUMERIC NOT NULL DEFAULT 0,
    average_cost NUMERIC NOT NULL DEFAULT 0,
    current_price NUMERIC DEFAULT 0,
    market_value NUMERIC GENERATED ALWAYS AS (quantity * current_price) STORED,
    unrealized_pnl NUMERIC GENERATED ALWAYS AS (market_value - (quantity * average_cost)) STORED,
    unrealized_pnl_percent NUMERIC GENERATED ALWAYS AS (
        CASE WHEN (quantity * average_cost) > 0 
        THEN ((market_value - (quantity * average_cost)) / (quantity * average_cost) * 100)
        ELSE 0 END
    ) STORED,
    last_updated TIMESTAMP WITH TIME ZONE DEFAULT CURRENT_TIMESTAMP,
    UNIQUE(user_id, symbol)
);

-- Create index for better performance
CREATE INDEX IF NOT EXISTS idx_portfolio_holdings_user_id ON portfolio_holdings(user_id);
CREATE INDEX IF NOT EXISTS idx_portfolio_holdings_symbol ON portfolio_holdings(symbol);

-- Portfolio Performance Table
CREATE TABLE IF NOT EXISTS portfolio_performance (
    id SERIAL PRIMARY KEY,
    user_id VARCHAR(255) NOT NULL,
    date DATE NOT NULL,
    total_value NUMERIC NOT NULL DEFAULT 0,
    daily_pnl_percent NUMERIC DEFAULT 0,
    total_pnl_percent NUMERIC DEFAULT 0,
    benchmark_return NUMERIC DEFAULT 0,
    created_at TIMESTAMP WITH TIME ZONE DEFAULT CURRENT_TIMESTAMP,
    UNIQUE(user_id, date)
);

-- Create index for better performance
CREATE INDEX IF NOT EXISTS idx_portfolio_performance_user_id ON portfolio_performance(user_id);
CREATE INDEX IF NOT EXISTS idx_portfolio_performance_date ON portfolio_performance(date);

-- Trading Alerts Table
CREATE TABLE IF NOT EXISTS trading_alerts (
    id SERIAL PRIMARY KEY,
    user_id VARCHAR(255) NOT NULL,
    symbol VARCHAR(10) NOT NULL,
    alert_type VARCHAR(50) NOT NULL,
    message TEXT,
    target_value NUMERIC,
    is_active BOOLEAN DEFAULT true,
    created_at TIMESTAMP WITH TIME ZONE DEFAULT CURRENT_TIMESTAMP,
    triggered_at TIMESTAMP WITH TIME ZONE NULL
);

-- Create index for better performance
CREATE INDEX IF NOT EXISTS idx_trading_alerts_user_id ON trading_alerts(user_id);
CREATE INDEX IF NOT EXISTS idx_trading_alerts_symbol ON trading_alerts(symbol);
CREATE INDEX IF NOT EXISTS idx_trading_alerts_active ON trading_alerts(is_active);

-- Economic Data Table (matches loadecondata.py structure)
CREATE TABLE IF NOT EXISTS economic_data (
    series_id TEXT NOT NULL,
    date DATE NOT NULL,
    value DOUBLE PRECISION,
    PRIMARY KEY (series_id, date)
);

-- Create index for better performance
CREATE INDEX IF NOT EXISTS idx_economic_data_series ON economic_data(series_id);
CREATE INDEX IF NOT EXISTS idx_economic_data_date ON economic_data(date);

-- Stocks table (for sector information and name lookups)
-- This table is referenced by dashboard queries but may not exist from loaders
CREATE TABLE IF NOT EXISTS stocks (
    id SERIAL PRIMARY KEY,
    symbol VARCHAR(10) NOT NULL UNIQUE,
    name VARCHAR(255),
    sector VARCHAR(100),
    industry VARCHAR(100),
    market_cap NUMERIC,
    created_at TIMESTAMP WITH TIME ZONE DEFAULT CURRENT_TIMESTAMP,
    updated_at TIMESTAMP WITH TIME ZONE DEFAULT CURRENT_TIMESTAMP
);

-- Create index for better performance
CREATE INDEX IF NOT EXISTS idx_stocks_symbol ON stocks(symbol);
CREATE INDEX IF NOT EXISTS idx_stocks_sector ON stocks(sector);

-- Add some basic stocks data if empty (this ensures dashboard has basic data)
INSERT INTO stocks (symbol, name, sector, industry) VALUES
    ('SPY', 'SPDR S&P 500 ETF Trust', 'ETF', 'Exchange Traded Fund'),
    ('QQQ', 'Invesco QQQ ETF', 'ETF', 'Exchange Traded Fund'),
    ('IWM', 'iShares Russell 2000 ETF', 'ETF', 'Exchange Traded Fund'),
    ('DIA', 'SPDR Dow Jones Industrial Average ETF', 'ETF', 'Exchange Traded Fund'),
    ('VTI', 'Vanguard Total Stock Market ETF', 'ETF', 'Exchange Traded Fund'),
    ('AAPL', 'Apple Inc.', 'Technology', 'Consumer Electronics'),
    ('MSFT', 'Microsoft Corporation', 'Technology', 'Software'),
    ('GOOGL', 'Alphabet Inc.', 'Technology', 'Internet Services'),
    ('TSLA', 'Tesla Inc.', 'Automotive', 'Electric Vehicles'),
    ('AMZN', 'Amazon.com Inc.', 'Technology', 'E-commerce')
ON CONFLICT (symbol) DO UPDATE SET
    name = EXCLUDED.name,
    sector = EXCLUDED.sector,
    industry = EXCLUDED.industry,
    updated_at = CURRENT_TIMESTAMP;

-- Create a function to sync current prices from price_daily to portfolio_holdings
CREATE OR REPLACE FUNCTION sync_portfolio_prices()
RETURNS void AS $$
BEGIN
    UPDATE portfolio_holdings ph
    SET current_price = pd.close
    FROM (
        SELECT DISTINCT ON (symbol) 
            symbol, close
        FROM price_daily 
        ORDER BY symbol, date DESC
    ) pd
    WHERE ph.symbol = pd.symbol
    AND pd.close IS NOT NULL;
END;
$$ LANGUAGE plpgsql;

-- Create a trigger to automatically update portfolio holdings when price_daily is updated
-- This ensures current_price is always in sync
CREATE OR REPLACE FUNCTION update_portfolio_current_prices()
RETURNS TRIGGER AS $$
BEGIN
    UPDATE portfolio_holdings 
    SET current_price = NEW.close
    WHERE symbol = NEW.symbol 
    AND NEW.close IS NOT NULL;
    RETURN NEW;
END;
$$ LANGUAGE plpgsql;

-- Drop existing trigger if it exists, then create new one
DROP TRIGGER IF EXISTS price_daily_update_trigger ON price_daily;
CREATE TRIGGER price_daily_update_trigger
    AFTER INSERT OR UPDATE ON price_daily
    FOR EACH ROW
    EXECUTE FUNCTION update_portfolio_current_prices();

COMMENT ON TABLE portfolio_holdings IS 'User portfolio holdings with calculated market values and P&L';
COMMENT ON TABLE portfolio_performance IS 'Daily portfolio performance tracking';
COMMENT ON TABLE trading_alerts IS 'User trading alerts and notifications';
COMMENT ON TABLE economic_data IS 'Economic indicators and market data';
COMMENT ON TABLE stocks IS 'Stock metadata including sectors and basic information';