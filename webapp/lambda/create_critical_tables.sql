-- Create critical missing tables

-- Trading alerts table
CREATE TABLE IF NOT EXISTS trading_alerts (
    id SERIAL PRIMARY KEY,
    user_id VARCHAR(255) NOT NULL,
    symbol VARCHAR(10) NOT NULL,
    alert_type VARCHAR(50) NOT NULL,
    title VARCHAR(255),
    description TEXT,
    trigger_price DECIMAL(12,4),
    current_price DECIMAL(12,4),
    trigger_condition VARCHAR(20),
    is_active BOOLEAN DEFAULT true,
    created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
    triggered_at TIMESTAMP NULL,
    expires_at TIMESTAMP NULL,
    acknowledged_at TIMESTAMP NULL
);

-- Price daily table for stock price data
CREATE TABLE IF NOT EXISTS price_daily (
    id SERIAL PRIMARY KEY,
    symbol VARCHAR(10) NOT NULL,
    date DATE NOT NULL,
    open_price DECIMAL(12,4),
    high_price DECIMAL(12,4),
    low_price DECIMAL(12,4),
    close_price DECIMAL(12,4),
    volume BIGINT,
    adjusted_close DECIMAL(12,4),
    created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
    UNIQUE(symbol, date)
);

-- User API keys table
CREATE TABLE IF NOT EXISTS user_api_keys (
    id SERIAL PRIMARY KEY,
    user_id VARCHAR(255) NOT NULL,
    provider VARCHAR(50) NOT NULL,
    api_key_encrypted TEXT,
    api_secret_encrypted TEXT,
    is_active BOOLEAN DEFAULT true,
    created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
    updated_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
    last_used TIMESTAMP NULL,
    UNIQUE(user_id, provider)
);

-- Market data realtime table
CREATE TABLE IF NOT EXISTS market_data_realtime (
    id SERIAL PRIMARY KEY,
    symbol VARCHAR(10) NOT NULL,
    current_price DECIMAL(12,4),
    change_amount DECIMAL(12,4),
    change_percent DECIMAL(6,4),
    volume BIGINT,
    market_cap DECIMAL(20,2),
    timestamp TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
    UNIQUE(symbol)
);

-- Social traders table (already exists but ensure it's there)
CREATE TABLE IF NOT EXISTS social_traders (
    id SERIAL PRIMARY KEY,
    username VARCHAR(100) NOT NULL UNIQUE,
    display_name VARCHAR(150),
    avatar VARCHAR(255),
    verified BOOLEAN DEFAULT false,
    followers INTEGER DEFAULT 0,
    following INTEGER DEFAULT 0,
    total_return DECIMAL(10,4) DEFAULT 0.0,
    win_rate DECIMAL(6,4) DEFAULT 0.0,
    total_trades INTEGER DEFAULT 0,
    profit_loss_ratio DECIMAL(10,4) DEFAULT 0.0,
    risk_score DECIMAL(4,2) DEFAULT 0.0,
    is_active BOOLEAN DEFAULT true,
    created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
    updated_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP
);

-- Insert sample data
INSERT INTO trading_alerts (user_id, symbol, alert_type, title, description, trigger_price, current_price, trigger_condition)
VALUES 
    ('dev-user-bypass', 'AAPL', 'price_above', 'AAPL Price Alert', 'Alert when AAPL goes above $200', 200.00, 190.50, 'above'),
    ('dev-user-bypass', 'TSLA', 'price_below', 'TSLA Price Alert', 'Alert when TSLA drops below $300', 300.00, 320.75, 'below')
ON CONFLICT DO NOTHING;

INSERT INTO price_daily (symbol, date, open_price, high_price, low_price, close_price, volume, adjusted_close)
VALUES 
    ('AAPL', CURRENT_DATE, 190.00, 192.50, 189.75, 191.25, 50000000, 191.25),
    ('TSLA', CURRENT_DATE, 320.00, 325.80, 318.50, 322.45, 35000000, 322.45),
    ('MSFT', CURRENT_DATE, 420.00, 425.30, 418.90, 423.15, 25000000, 423.15)
ON CONFLICT (symbol, date) DO UPDATE SET
    open_price = EXCLUDED.open_price,
    high_price = EXCLUDED.high_price,
    low_price = EXCLUDED.low_price,
    close_price = EXCLUDED.close_price,
    volume = EXCLUDED.volume,
    adjusted_close = EXCLUDED.adjusted_close;

INSERT INTO user_api_keys (user_id, provider, api_key_encrypted, api_secret_encrypted)
VALUES 
    ('dev-user-bypass', 'alpaca', 'encrypted_dev_key', 'encrypted_dev_secret'),
    ('test-user', 'alpaca', 'encrypted_test_key', 'encrypted_test_secret')
ON CONFLICT (user_id, provider) DO NOTHING;

INSERT INTO market_data_realtime (symbol, current_price, change_amount, change_percent, volume, market_cap)
VALUES 
    ('AAPL', 191.25, 1.25, 0.66, 50000000, 2950000000000),
    ('TSLA', 322.45, -2.55, -0.78, 35000000, 1020000000000),
    ('MSFT', 423.15, 3.15, 0.75, 25000000, 3150000000000)
ON CONFLICT (symbol) DO UPDATE SET
    current_price = EXCLUDED.current_price,
    change_amount = EXCLUDED.change_amount,
    change_percent = EXCLUDED.change_percent,
    volume = EXCLUDED.volume,
    market_cap = EXCLUDED.market_cap,
    timestamp = CURRENT_TIMESTAMP;