-- Initialize Required Database Tables
-- Creates all tables required for core functionality

-- Enable necessary extensions
CREATE EXTENSION IF NOT EXISTS "uuid-ossp";
CREATE EXTENSION IF NOT EXISTS "pgcrypto";

-- Users table (referenced by other tables)
CREATE TABLE IF NOT EXISTS users (
    user_id SERIAL PRIMARY KEY,
    uuid UUID DEFAULT uuid_generate_v4() UNIQUE,
    email VARCHAR(255) UNIQUE NOT NULL,
    first_name VARCHAR(100),
    last_name VARCHAR(100),
    created_at TIMESTAMP WITH TIME ZONE DEFAULT CURRENT_TIMESTAMP,
    updated_at TIMESTAMP WITH TIME ZONE DEFAULT CURRENT_TIMESTAMP,
    is_active BOOLEAN DEFAULT true
);

-- User API Keys table - for secure API key storage
CREATE TABLE IF NOT EXISTS user_api_keys (
    id SERIAL PRIMARY KEY,
    user_id VARCHAR(255) NOT NULL,
    provider VARCHAR(50) NOT NULL DEFAULT 'alpaca',
    broker_name VARCHAR(50), -- legacy field compatibility
    api_key_encrypted TEXT NOT NULL,
    secret_encrypted TEXT,
    encrypted_api_key TEXT, -- legacy field compatibility
    encrypted_api_secret TEXT, -- legacy field compatibility
    masked_api_key VARCHAR(50),
    key_iv VARCHAR(32),
    key_auth_tag VARCHAR(32),
    secret_iv VARCHAR(32),
    secret_auth_tag VARCHAR(32),
    is_sandbox BOOLEAN DEFAULT true,
    is_active BOOLEAN DEFAULT true,
    validation_status VARCHAR(20) DEFAULT 'pending',
    created_at TIMESTAMP WITH TIME ZONE DEFAULT CURRENT_TIMESTAMP,
    updated_at TIMESTAMP WITH TIME ZONE DEFAULT CURRENT_TIMESTAMP,
    last_used TIMESTAMP WITH TIME ZONE,
    api_key_id INTEGER, -- API key reference
    UNIQUE(user_id, provider),
    UNIQUE(user_id, broker_name) -- legacy compatibility
);

-- Portfolio Holdings Table - stores current portfolio positions
CREATE TABLE IF NOT EXISTS portfolio_holdings (
    holding_id SERIAL PRIMARY KEY,
    user_id VARCHAR(255) NOT NULL,
    api_key_id INTEGER REFERENCES user_api_keys(id) ON DELETE CASCADE,
    symbol VARCHAR(10) NOT NULL,
    quantity DECIMAL(15, 6) NOT NULL CHECK (quantity >= 0),
    shares DECIMAL(15, 6), -- legacy field compatibility
    avg_cost DECIMAL(10, 2) NOT NULL CHECK (avg_cost >= 0),
    current_price DECIMAL(10, 2),
    market_value DECIMAL(15, 2),
    unrealized_pl DECIMAL(15, 2),
    unrealized_plpc DECIMAL(5, 4),
    side VARCHAR(10) DEFAULT 'long',
    account_type VARCHAR(20) DEFAULT 'paper',
    broker VARCHAR(50) DEFAULT 'alpaca',
    exchange VARCHAR(10),
    sector VARCHAR(100),
    industry VARCHAR(100),
    company VARCHAR(200),
    created_at TIMESTAMP WITH TIME ZONE DEFAULT CURRENT_TIMESTAMP,
    updated_at TIMESTAMP WITH TIME ZONE DEFAULT CURRENT_TIMESTAMP,
    UNIQUE(user_id, api_key_id, symbol)
);

-- Portfolio Metadata Table - stores account-level information
CREATE TABLE IF NOT EXISTS portfolio_metadata (
    metadata_id SERIAL PRIMARY KEY,
    user_id VARCHAR(255) NOT NULL UNIQUE,
    api_key_id INTEGER REFERENCES user_api_keys(id) ON DELETE CASCADE,
    account_id VARCHAR(50),
    account_type VARCHAR(20) DEFAULT 'paper',
    total_equity DECIMAL(15, 2),
    total_market_value DECIMAL(15, 2),
    buying_power DECIMAL(15, 2),
    cash DECIMAL(15, 2),
    day_trade_count INTEGER DEFAULT 0,
    last_sync_at TIMESTAMP WITH TIME ZONE,
    sync_status VARCHAR(20) DEFAULT 'pending',
    broker VARCHAR(50) DEFAULT 'alpaca',
    created_at TIMESTAMP WITH TIME ZONE DEFAULT CURRENT_TIMESTAMP,
    updated_at TIMESTAMP WITH TIME ZONE DEFAULT CURRENT_TIMESTAMP
);

-- Market Data table (optional but commonly referenced)
CREATE TABLE IF NOT EXISTS market_data (
    id SERIAL PRIMARY KEY,
    symbol VARCHAR(10) NOT NULL,
    price DECIMAL(10, 2) NOT NULL,
    volume BIGINT,
    market_cap BIGINT,
    pe_ratio DECIMAL(8, 2),
    dividend_yield DECIMAL(5, 4),
    beta DECIMAL(5, 3),
    fifty_two_week_high DECIMAL(10, 2),
    fifty_two_week_low DECIMAL(10, 2),
    sector VARCHAR(100),
    industry VARCHAR(100),
    exchange VARCHAR(10),
    updated_at TIMESTAMP WITH TIME ZONE DEFAULT CURRENT_TIMESTAMP,
    UNIQUE(symbol)
);

-- Stock Symbols table (optional but commonly referenced)
CREATE TABLE IF NOT EXISTS stock_symbols (
    id SERIAL PRIMARY KEY,
    symbol VARCHAR(10) NOT NULL UNIQUE,
    company_name VARCHAR(200),
    sector VARCHAR(100),
    industry VARCHAR(100),
    exchange VARCHAR(10),
    market_cap BIGINT,
    is_active BOOLEAN DEFAULT true,
    created_at TIMESTAMP WITH TIME ZONE DEFAULT CURRENT_TIMESTAMP,
    updated_at TIMESTAMP WITH TIME ZONE DEFAULT CURRENT_TIMESTAMP
);

-- Symbols table (legacy compatibility)
CREATE TABLE IF NOT EXISTS symbols (
    id SERIAL PRIMARY KEY,
    symbol VARCHAR(10) NOT NULL UNIQUE,
    company VARCHAR(200),
    sector VARCHAR(100),
    industry VARCHAR(100),
    exchange VARCHAR(10),
    market_cap BIGINT,
    is_active BOOLEAN DEFAULT true,
    created_at TIMESTAMP WITH TIME ZONE DEFAULT CURRENT_TIMESTAMP,
    updated_at TIMESTAMP WITH TIME ZONE DEFAULT CURRENT_TIMESTAMP
);

-- Create indexes for performance
CREATE INDEX IF NOT EXISTS idx_user_api_keys_user_id ON user_api_keys(user_id);
CREATE INDEX IF NOT EXISTS idx_user_api_keys_provider ON user_api_keys(provider);
CREATE INDEX IF NOT EXISTS idx_user_api_keys_broker ON user_api_keys(broker_name);
CREATE INDEX IF NOT EXISTS idx_user_api_keys_active ON user_api_keys(is_active);
CREATE INDEX IF NOT EXISTS idx_user_api_keys_last_used ON user_api_keys(last_used DESC);

CREATE INDEX IF NOT EXISTS idx_portfolio_holdings_user_id ON portfolio_holdings(user_id);
CREATE INDEX IF NOT EXISTS idx_portfolio_holdings_symbol ON portfolio_holdings(symbol);
CREATE INDEX IF NOT EXISTS idx_portfolio_holdings_api_key ON portfolio_holdings(api_key_id);
CREATE INDEX IF NOT EXISTS idx_portfolio_holdings_account_type ON portfolio_holdings(account_type);
CREATE INDEX IF NOT EXISTS idx_portfolio_holdings_updated_at ON portfolio_holdings(updated_at);

CREATE INDEX IF NOT EXISTS idx_portfolio_metadata_user_id ON portfolio_metadata(user_id);
CREATE INDEX IF NOT EXISTS idx_portfolio_metadata_api_key ON portfolio_metadata(api_key_id);
CREATE INDEX IF NOT EXISTS idx_portfolio_metadata_sync_status ON portfolio_metadata(sync_status);

CREATE INDEX IF NOT EXISTS idx_market_data_symbol ON market_data(symbol);
CREATE INDEX IF NOT EXISTS idx_market_data_updated_at ON market_data(updated_at);

CREATE INDEX IF NOT EXISTS idx_stock_symbols_symbol ON stock_symbols(symbol);
CREATE INDEX IF NOT EXISTS idx_stock_symbols_sector ON stock_symbols(sector);
CREATE INDEX IF NOT EXISTS idx_stock_symbols_active ON stock_symbols(is_active);

CREATE INDEX IF NOT EXISTS idx_symbols_symbol ON symbols(symbol);
CREATE INDEX IF NOT EXISTS idx_symbols_sector ON symbols(sector);
CREATE INDEX IF NOT EXISTS idx_symbols_active ON symbols(is_active);

-- Add updated_at trigger function for automatic timestamp updates
CREATE OR REPLACE FUNCTION update_updated_at_column()
RETURNS TRIGGER AS $$
BEGIN
    NEW.updated_at = CURRENT_TIMESTAMP;
    RETURN NEW;
END;
$$ language 'plpgsql';

-- Apply updated_at triggers to relevant tables
DROP TRIGGER IF EXISTS update_users_updated_at ON users;
CREATE TRIGGER update_users_updated_at 
    BEFORE UPDATE ON users 
    FOR EACH ROW EXECUTE FUNCTION update_updated_at_column();

DROP TRIGGER IF EXISTS update_user_api_keys_updated_at ON user_api_keys;
CREATE TRIGGER update_user_api_keys_updated_at 
    BEFORE UPDATE ON user_api_keys 
    FOR EACH ROW EXECUTE FUNCTION update_updated_at_column();

DROP TRIGGER IF EXISTS update_portfolio_holdings_updated_at ON portfolio_holdings;
CREATE TRIGGER update_portfolio_holdings_updated_at 
    BEFORE UPDATE ON portfolio_holdings 
    FOR EACH ROW EXECUTE FUNCTION update_updated_at_column();

DROP TRIGGER IF EXISTS update_portfolio_metadata_updated_at ON portfolio_metadata;
CREATE TRIGGER update_portfolio_metadata_updated_at 
    BEFORE UPDATE ON portfolio_metadata 
    FOR EACH ROW EXECUTE FUNCTION update_updated_at_column();

DROP TRIGGER IF EXISTS update_market_data_updated_at ON market_data;
CREATE TRIGGER update_market_data_updated_at 
    BEFORE UPDATE ON market_data 
    FOR EACH ROW EXECUTE FUNCTION update_updated_at_column();

DROP TRIGGER IF EXISTS update_stock_symbols_updated_at ON stock_symbols;
CREATE TRIGGER update_stock_symbols_updated_at 
    BEFORE UPDATE ON stock_symbols 
    FOR EACH ROW EXECUTE FUNCTION update_updated_at_column();

DROP TRIGGER IF EXISTS update_symbols_updated_at ON symbols;
CREATE TRIGGER update_symbols_updated_at 
    BEFORE UPDATE ON symbols 
    FOR EACH ROW EXECUTE FUNCTION update_updated_at_column();

-- Log successful initialization
DO $$
BEGIN
    RAISE NOTICE 'Required database tables initialized successfully at %', NOW();
END
$$;