-- Initialize test database with required tables

-- Create stocks table if it doesn't exist
CREATE TABLE IF NOT EXISTS stocks (
    id SERIAL PRIMARY KEY,
    symbol VARCHAR(10) NOT NULL UNIQUE,
    name VARCHAR(255) NOT NULL,
    market VARCHAR(50),
    created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
    updated_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP
);

-- Create stock_symbols table (used by loadstocksymbols_test)
CREATE TABLE IF NOT EXISTS stock_symbols (
    symbol VARCHAR(50),
    exchange VARCHAR(100),
    security_name TEXT,
    cqs_symbol VARCHAR(50),
    market_category VARCHAR(50),
    test_issue CHAR(1),
    financial_status VARCHAR(50),
    round_lot_size INT,
    etf CHAR(1),
    secondary_symbol VARCHAR(50)
);

-- Create etf_symbols table (used by loadstocksymbols_test)
CREATE TABLE IF NOT EXISTS etf_symbols (
    symbol VARCHAR(50),
    exchange VARCHAR(100),
    security_name TEXT,
    cqs_symbol VARCHAR(50),
    market_category VARCHAR(50),
    test_issue CHAR(1),
    financial_status VARCHAR(50),
    round_lot_size INT,
    etf CHAR(1),
    secondary_symbol VARCHAR(50)
);

-- Create price_weekly table (used by loadpriceweekly)
CREATE TABLE IF NOT EXISTS price_weekly (
    id SERIAL PRIMARY KEY,
    symbol VARCHAR(50) NOT NULL,
    date DATE NOT NULL,
    open DECIMAL(12,4),
    high DECIMAL(12,4),
    low DECIMAL(12,4),
    close DECIMAL(12,4),
    adj_close DECIMAL(12,4),
    volume BIGINT,
    dividends DECIMAL(10,4),
    stock_splits DECIMAL(10,4),
    created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
    UNIQUE(symbol, date)
);

-- Create technicals_weekly table (used by loadtechnicalsweekly)
CREATE TABLE IF NOT EXISTS technicals_weekly (
    id SERIAL PRIMARY KEY,
    symbol VARCHAR(50) NOT NULL,
    date DATE NOT NULL,
    
    -- Moving averages
    sma_20 DECIMAL(12,4),
    sma_50 DECIMAL(12,4),
    sma_200 DECIMAL(12,4),
    ema_12 DECIMAL(12,4),
    ema_26 DECIMAL(12,4),
    
    -- MACD
    macd DECIMAL(12,4),
    macd_signal DECIMAL(12,4),
    macd_histogram DECIMAL(12,4),
    
    -- RSI
    rsi_14 DECIMAL(8,4),
    
    -- Bollinger Bands
    bb_upper DECIMAL(12,4),
    bb_middle DECIMAL(12,4),
    bb_lower DECIMAL(12,4),
    
    -- Volume
    volume_sma_20 BIGINT,
    
    -- Pivot points
    pivot_high DECIMAL(12,4),
    pivot_low DECIMAL(12,4),
    
    -- Other indicators
    td_sequential INTEGER,
    td_combo INTEGER,
    marketwatch_signal VARCHAR(10),
    
    created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
    UNIQUE(symbol, date)
);

-- Create last_updated table
CREATE TABLE IF NOT EXISTS last_updated (
    script_name VARCHAR(255) PRIMARY KEY,
    last_run TIMESTAMP WITH TIME ZONE
);

-- Create index on symbol for faster lookups
CREATE INDEX IF NOT EXISTS idx_stocks_symbol ON stocks(symbol);
CREATE INDEX IF NOT EXISTS idx_stock_symbols_symbol ON stock_symbols(symbol);
CREATE INDEX IF NOT EXISTS idx_etf_symbols_symbol ON etf_symbols(symbol);
CREATE INDEX IF NOT EXISTS idx_price_weekly_symbol_date ON price_weekly(symbol, date);
CREATE INDEX IF NOT EXISTS idx_technicals_weekly_symbol_date ON technicals_weekly(symbol, date);

-- Insert some test data
INSERT INTO stocks (symbol, name, market) VALUES 
    ('AAPL', 'Apple Inc.', 'NASDAQ'),
    ('GOOGL', 'Alphabet Inc.', 'NASDAQ'),
    ('MSFT', 'Microsoft Corporation', 'NASDAQ')
ON CONFLICT (symbol) DO NOTHING;

-- Create a table for earnings data (example)
CREATE TABLE IF NOT EXISTS earnings (
    id SERIAL PRIMARY KEY,
    symbol VARCHAR(10) NOT NULL,
    fiscal_date_ending DATE,
    reported_eps DECIMAL(10,4),
    estimated_eps DECIMAL(10,4),
    surprise DECIMAL(10,4),
    surprise_percentage DECIMAL(8,4),
    created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP
);

-- Create a table for price data (example)
CREATE TABLE IF NOT EXISTS prices (
    id SERIAL PRIMARY KEY,
    symbol VARCHAR(10) NOT NULL,
    date DATE NOT NULL,
    open_price DECIMAL(12,4),
    high_price DECIMAL(12,4),
    low_price DECIMAL(12,4),
    close_price DECIMAL(12,4),
    volume BIGINT,
    created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
    UNIQUE(symbol, date)
);

-- Create indexes for better performance
CREATE INDEX IF NOT EXISTS idx_earnings_symbol ON earnings(symbol);
CREATE INDEX IF NOT EXISTS idx_prices_symbol_date ON prices(symbol, date);

-- Print confirmation
SELECT 'Database initialized successfully' as status;
