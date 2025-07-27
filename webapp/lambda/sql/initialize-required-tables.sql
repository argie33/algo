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

-- ============================================================================
-- CRYPTOCURRENCY TABLES
-- ============================================================================

-- Crypto Assets (Master List)
CREATE TABLE IF NOT EXISTS crypto_assets (
    id SERIAL PRIMARY KEY,
    symbol VARCHAR(20) NOT NULL UNIQUE,
    name VARCHAR(255) NOT NULL,
    coingecko_id VARCHAR(100),
    contract_address VARCHAR(255),
    blockchain VARCHAR(50),
    market_cap DECIMAL(20,2),
    circulating_supply DECIMAL(20,8),
    total_supply DECIMAL(20,8),
    max_supply DECIMAL(20,8),
    launch_date DATE,
    website VARCHAR(255),
    is_active BOOLEAN DEFAULT true,
    created_at TIMESTAMP WITH TIME ZONE DEFAULT CURRENT_TIMESTAMP,
    updated_at TIMESTAMP WITH TIME ZONE DEFAULT CURRENT_TIMESTAMP
);

-- Crypto Market Metrics (Global market data)
CREATE TABLE IF NOT EXISTS crypto_market_metrics (
    id SERIAL PRIMARY KEY,
    total_market_cap DECIMAL(20,2),
    total_volume_24h DECIMAL(20,2),
    btc_dominance DECIMAL(5,2),
    eth_dominance DECIMAL(5,2),
    active_cryptocurrencies INTEGER,
    market_cap_change_24h DECIMAL(5,2),
    timestamp TIMESTAMP WITH TIME ZONE DEFAULT CURRENT_TIMESTAMP
);

-- Crypto Fear & Greed Index
CREATE TABLE IF NOT EXISTS crypto_fear_greed (
    id SERIAL PRIMARY KEY,
    value INTEGER NOT NULL CHECK (value >= 0 AND value <= 100),
    value_classification VARCHAR(50) NOT NULL,
    timestamp TIMESTAMP WITH TIME ZONE DEFAULT CURRENT_TIMESTAMP
);

-- Crypto Price Data (Real-time and historical)
CREATE TABLE IF NOT EXISTS crypto_prices (
    id SERIAL PRIMARY KEY,
    symbol VARCHAR(20) NOT NULL,
    timestamp TIMESTAMP WITH TIME ZONE NOT NULL,
    price DECIMAL(15,8) NOT NULL,
    market_cap DECIMAL(20,2),
    volume_24h DECIMAL(20,2),
    price_change_24h DECIMAL(5,2),
    price_change_7d DECIMAL(5,2),
    price_change_30d DECIMAL(5,2),
    high_24h DECIMAL(15,8),
    low_24h DECIMAL(15,8),
    created_at TIMESTAMP WITH TIME ZONE DEFAULT CURRENT_TIMESTAMP,
    UNIQUE(symbol, timestamp)
);

-- Crypto Historical Prices (For charting)
CREATE TABLE IF NOT EXISTS crypto_historical_prices (
    id SERIAL PRIMARY KEY,
    symbol VARCHAR(20) NOT NULL,
    timestamp TIMESTAMP WITH TIME ZONE NOT NULL,
    price DECIMAL(15,8) NOT NULL,
    market_cap DECIMAL(20,2),
    volume_24h DECIMAL(20,2),
    price_change_24h DECIMAL(5,2),
    high_24h DECIMAL(15,8),
    low_24h DECIMAL(15,8),
    created_at TIMESTAMP WITH TIME ZONE DEFAULT CURRENT_TIMESTAMP,
    UNIQUE(symbol, timestamp)
);

-- Crypto Top Movers (Gainers and Losers)
CREATE TABLE IF NOT EXISTS crypto_movers (
    id SERIAL PRIMARY KEY,
    symbol VARCHAR(20) NOT NULL,
    name VARCHAR(255),
    price DECIMAL(15,8) NOT NULL,
    price_change_24h DECIMAL(5,2) NOT NULL,
    volume_24h DECIMAL(20,2),
    market_cap DECIMAL(20,2),
    mover_type VARCHAR(10) NOT NULL CHECK (mover_type IN ('gainer', 'loser')),
    rank_position INTEGER,
    timestamp TIMESTAMP WITH TIME ZONE DEFAULT CURRENT_TIMESTAMP
);

-- Crypto Trending (Trending cryptocurrencies)
CREATE TABLE IF NOT EXISTS crypto_trending (
    id SERIAL PRIMARY KEY,
    symbol VARCHAR(20) NOT NULL,
    name VARCHAR(255),
    coingecko_id VARCHAR(100),
    market_cap_rank INTEGER,
    search_score DECIMAL(8,2),
    price_btc DECIMAL(15,8),
    timestamp TIMESTAMP WITH TIME ZONE DEFAULT CURRENT_TIMESTAMP
);

-- User Crypto Portfolios
CREATE TABLE IF NOT EXISTS crypto_portfolio (
    id SERIAL PRIMARY KEY,
    user_id VARCHAR(255) NOT NULL,
    symbol VARCHAR(20) NOT NULL,
    quantity DECIMAL(20,8) NOT NULL CHECK (quantity >= 0),
    average_cost DECIMAL(15,8) NOT NULL CHECK (average_cost >= 0),
    current_price DECIMAL(15,8),
    market_value DECIMAL(15,2),
    total_cost DECIMAL(15,2),
    unrealized_pnl DECIMAL(15,2),
    unrealized_pnl_percent DECIMAL(5,2),
    last_updated TIMESTAMP WITH TIME ZONE DEFAULT CURRENT_TIMESTAMP,
    created_at TIMESTAMP WITH TIME ZONE DEFAULT CURRENT_TIMESTAMP,
    UNIQUE(user_id, symbol)
);

-- Crypto Transactions (Buy/Sell history)
CREATE TABLE IF NOT EXISTS crypto_transactions (
    id SERIAL PRIMARY KEY,
    user_id VARCHAR(255) NOT NULL,
    symbol VARCHAR(20) NOT NULL,
    transaction_type VARCHAR(10) NOT NULL CHECK (transaction_type IN ('BUY', 'SELL')),
    quantity DECIMAL(20,8) NOT NULL CHECK (quantity > 0),
    price DECIMAL(15,8) NOT NULL CHECK (price > 0),
    total_amount DECIMAL(15,2) NOT NULL,
    fees DECIMAL(10,4) DEFAULT 0,
    exchange VARCHAR(50),
    transaction_id VARCHAR(255), -- External transaction ID
    notes TEXT,
    transaction_date TIMESTAMP WITH TIME ZONE NOT NULL,
    created_at TIMESTAMP WITH TIME ZONE DEFAULT CURRENT_TIMESTAMP
);

-- Crypto Price Alerts
CREATE TABLE IF NOT EXISTS crypto_alerts (
    id SERIAL PRIMARY KEY,
    user_id VARCHAR(255) NOT NULL,
    symbol VARCHAR(20) NOT NULL,
    alert_type VARCHAR(20) NOT NULL CHECK (alert_type IN ('price_above', 'price_below', 'percent_change')),
    target_value DECIMAL(15,8) NOT NULL,
    current_value DECIMAL(15,8),
    condition_met BOOLEAN DEFAULT false,
    is_active BOOLEAN DEFAULT true,
    notification_sent BOOLEAN DEFAULT false,
    notification_methods TEXT[] DEFAULT ARRAY['email'], -- Array of notification methods
    message TEXT,
    triggered_at TIMESTAMP WITH TIME ZONE,
    created_at TIMESTAMP WITH TIME ZONE DEFAULT CURRENT_TIMESTAMP,
    updated_at TIMESTAMP WITH TIME ZONE DEFAULT CURRENT_TIMESTAMP
);

-- Crypto News (For sentiment analysis)
CREATE TABLE IF NOT EXISTS crypto_news (
    id SERIAL PRIMARY KEY,
    title VARCHAR(500) NOT NULL,
    description TEXT,
    url VARCHAR(1000),
    source VARCHAR(100),
    author VARCHAR(255),
    published_at TIMESTAMP WITH TIME ZONE,
    category VARCHAR(50),
    related_symbols TEXT[], -- Array of related crypto symbols
    sentiment_score DECIMAL(3,2), -- -1 to 1 sentiment score
    importance_score INTEGER DEFAULT 5, -- 1-10 importance rating
    image_url VARCHAR(1000),
    created_at TIMESTAMP WITH TIME ZONE DEFAULT CURRENT_TIMESTAMP
);

-- DeFi TVL (Total Value Locked) data
CREATE TABLE IF NOT EXISTS defi_tvl (
    id SERIAL PRIMARY KEY,
    protocol VARCHAR(100) NOT NULL,
    chain VARCHAR(50) NOT NULL,
    tvl_usd DECIMAL(20,2) NOT NULL,
    tvl_change_24h DECIMAL(5,2),
    tvl_change_7d DECIMAL(5,2),
    category VARCHAR(100),
    timestamp TIMESTAMP WITH TIME ZONE DEFAULT CURRENT_TIMESTAMP
);

-- Crypto Exchanges data
CREATE TABLE IF NOT EXISTS crypto_exchanges (
    id SERIAL PRIMARY KEY,
    exchange_id VARCHAR(100) NOT NULL UNIQUE,
    name VARCHAR(255) NOT NULL,
    country VARCHAR(100),
    trust_score INTEGER,
    volume_24h_btc DECIMAL(20,8),
    normalized_volume_24h_btc DECIMAL(20,8),
    is_centralized BOOLEAN DEFAULT true,
    created_at TIMESTAMP WITH TIME ZONE DEFAULT CURRENT_TIMESTAMP,
    updated_at TIMESTAMP WITH TIME ZONE DEFAULT CURRENT_TIMESTAMP
);

-- Crypto User Watchlists
CREATE TABLE IF NOT EXISTS crypto_watchlists (
    id SERIAL PRIMARY KEY,
    user_id VARCHAR(255) NOT NULL,
    name VARCHAR(255) NOT NULL,
    description TEXT,
    is_default BOOLEAN DEFAULT false,
    created_at TIMESTAMP WITH TIME ZONE DEFAULT CURRENT_TIMESTAMP,
    updated_at TIMESTAMP WITH TIME ZONE DEFAULT CURRENT_TIMESTAMP
);

-- Crypto Watchlist Items
CREATE TABLE IF NOT EXISTS crypto_watchlist_items (
    id SERIAL PRIMARY KEY,
    watchlist_id INTEGER NOT NULL REFERENCES crypto_watchlists(id) ON DELETE CASCADE,
    symbol VARCHAR(20) NOT NULL,
    added_at TIMESTAMP WITH TIME ZONE DEFAULT CURRENT_TIMESTAMP,
    UNIQUE(watchlist_id, symbol)
);

-- Crypto API Keys (For exchange integration)
CREATE TABLE IF NOT EXISTS crypto_api_keys (
    id SERIAL PRIMARY KEY,
    user_id VARCHAR(255) NOT NULL,
    exchange VARCHAR(50) NOT NULL,
    api_key_encrypted TEXT NOT NULL,
    api_secret_encrypted TEXT,
    passphrase_encrypted TEXT, -- For some exchanges like Coinbase Pro
    permissions TEXT[], -- Array of permissions (read, trade, withdraw)
    is_sandbox BOOLEAN DEFAULT true,
    is_active BOOLEAN DEFAULT true,
    last_used TIMESTAMP WITH TIME ZONE,
    created_at TIMESTAMP WITH TIME ZONE DEFAULT CURRENT_TIMESTAMP,
    updated_at TIMESTAMP WITH TIME ZONE DEFAULT CURRENT_TIMESTAMP,
    UNIQUE(user_id, exchange)
);

-- ============================================================================
-- CRYPTO INDEXES FOR PERFORMANCE
-- ============================================================================

-- Crypto assets indexes
CREATE INDEX IF NOT EXISTS idx_crypto_assets_symbol ON crypto_assets(symbol);
CREATE INDEX IF NOT EXISTS idx_crypto_assets_coingecko_id ON crypto_assets(coingecko_id);
CREATE INDEX IF NOT EXISTS idx_crypto_assets_active ON crypto_assets(is_active);

-- Crypto prices indexes
CREATE INDEX IF NOT EXISTS idx_crypto_prices_symbol_timestamp ON crypto_prices(symbol, timestamp DESC);
CREATE INDEX IF NOT EXISTS idx_crypto_prices_timestamp ON crypto_prices(timestamp DESC);
CREATE INDEX IF NOT EXISTS idx_crypto_historical_prices_symbol_timestamp ON crypto_historical_prices(symbol, timestamp DESC);

-- Market data indexes
CREATE INDEX IF NOT EXISTS idx_crypto_market_metrics_timestamp ON crypto_market_metrics(timestamp DESC);
CREATE INDEX IF NOT EXISTS idx_crypto_fear_greed_timestamp ON crypto_fear_greed(timestamp DESC);

-- Movers and trending indexes
CREATE INDEX IF NOT EXISTS idx_crypto_movers_timestamp ON crypto_movers(timestamp DESC);
CREATE INDEX IF NOT EXISTS idx_crypto_movers_type_rank ON crypto_movers(mover_type, rank_position);
CREATE INDEX IF NOT EXISTS idx_crypto_trending_timestamp ON crypto_trending(timestamp DESC);
CREATE INDEX IF NOT EXISTS idx_crypto_trending_score ON crypto_trending(search_score DESC);

-- Portfolio indexes
CREATE INDEX IF NOT EXISTS idx_crypto_portfolio_user_id ON crypto_portfolio(user_id);
CREATE INDEX IF NOT EXISTS idx_crypto_portfolio_symbol ON crypto_portfolio(symbol);
CREATE INDEX IF NOT EXISTS idx_crypto_portfolio_user_symbol ON crypto_portfolio(user_id, symbol);

-- Transaction indexes
CREATE INDEX IF NOT EXISTS idx_crypto_transactions_user_id ON crypto_transactions(user_id);
CREATE INDEX IF NOT EXISTS idx_crypto_transactions_symbol ON crypto_transactions(symbol);
CREATE INDEX IF NOT EXISTS idx_crypto_transactions_date ON crypto_transactions(transaction_date DESC);
CREATE INDEX IF NOT EXISTS idx_crypto_transactions_user_date ON crypto_transactions(user_id, transaction_date DESC);

-- Alert indexes
CREATE INDEX IF NOT EXISTS idx_crypto_alerts_user_id ON crypto_alerts(user_id);
CREATE INDEX IF NOT EXISTS idx_crypto_alerts_symbol ON crypto_alerts(symbol);
CREATE INDEX IF NOT EXISTS idx_crypto_alerts_active ON crypto_alerts(is_active);
CREATE INDEX IF NOT EXISTS idx_crypto_alerts_condition_met ON crypto_alerts(condition_met);

-- News indexes
CREATE INDEX IF NOT EXISTS idx_crypto_news_published_at ON crypto_news(published_at DESC);
CREATE INDEX IF NOT EXISTS idx_crypto_news_symbols ON crypto_news USING GIN(related_symbols);
CREATE INDEX IF NOT EXISTS idx_crypto_news_category ON crypto_news(category);

-- DeFi indexes
CREATE INDEX IF NOT EXISTS idx_defi_tvl_protocol ON defi_tvl(protocol);
CREATE INDEX IF NOT EXISTS idx_defi_tvl_chain ON defi_tvl(chain);
CREATE INDEX IF NOT EXISTS idx_defi_tvl_timestamp ON defi_tvl(timestamp DESC);

-- Exchange indexes
CREATE INDEX IF NOT EXISTS idx_crypto_exchanges_exchange_id ON crypto_exchanges(exchange_id);
CREATE INDEX IF NOT EXISTS idx_crypto_exchanges_trust_score ON crypto_exchanges(trust_score DESC);

-- Watchlist indexes
CREATE INDEX IF NOT EXISTS idx_crypto_watchlists_user_id ON crypto_watchlists(user_id);
CREATE INDEX IF NOT EXISTS idx_crypto_watchlist_items_watchlist_id ON crypto_watchlist_items(watchlist_id);

-- API keys indexes
CREATE INDEX IF NOT EXISTS idx_crypto_api_keys_user_id ON crypto_api_keys(user_id);
CREATE INDEX IF NOT EXISTS idx_crypto_api_keys_exchange ON crypto_api_keys(exchange);
CREATE INDEX IF NOT EXISTS idx_crypto_api_keys_active ON crypto_api_keys(is_active);

-- ============================================================================
-- CRYPTO TRIGGERS
-- ============================================================================

-- Apply updated_at triggers to crypto tables
DROP TRIGGER IF EXISTS update_crypto_assets_updated_at ON crypto_assets;
CREATE TRIGGER update_crypto_assets_updated_at 
    BEFORE UPDATE ON crypto_assets 
    FOR EACH ROW EXECUTE FUNCTION update_updated_at_column();

DROP TRIGGER IF EXISTS update_crypto_exchanges_updated_at ON crypto_exchanges;
CREATE TRIGGER update_crypto_exchanges_updated_at 
    BEFORE UPDATE ON crypto_exchanges 
    FOR EACH ROW EXECUTE FUNCTION update_updated_at_column();

DROP TRIGGER IF EXISTS update_crypto_watchlists_updated_at ON crypto_watchlists;
CREATE TRIGGER update_crypto_watchlists_updated_at 
    BEFORE UPDATE ON crypto_watchlists 
    FOR EACH ROW EXECUTE FUNCTION update_updated_at_column();

DROP TRIGGER IF EXISTS update_crypto_api_keys_updated_at ON crypto_api_keys;
CREATE TRIGGER update_crypto_api_keys_updated_at 
    BEFORE UPDATE ON crypto_api_keys 
    FOR EACH ROW EXECUTE FUNCTION update_updated_at_column();

DROP TRIGGER IF EXISTS update_crypto_alerts_updated_at ON crypto_alerts;
CREATE TRIGGER update_crypto_alerts_updated_at 
    BEFORE UPDATE ON crypto_alerts 
    FOR EACH ROW EXECUTE FUNCTION update_updated_at_column();

-- ============================================================================
-- SAMPLE CRYPTO DATA
-- ============================================================================

-- Insert popular cryptocurrencies
INSERT INTO crypto_assets (symbol, name, coingecko_id, is_active) VALUES
    ('BTC', 'Bitcoin', 'bitcoin', true),
    ('ETH', 'Ethereum', 'ethereum', true),
    ('BNB', 'Binance Coin', 'binancecoin', true),
    ('ADA', 'Cardano', 'cardano', true),
    ('DOT', 'Polkadot', 'polkadot', true),
    ('LINK', 'Chainlink', 'chainlink', true),
    ('XRP', 'XRP', 'ripple', true),
    ('LTC', 'Litecoin', 'litecoin', true),
    ('BCH', 'Bitcoin Cash', 'bitcoin-cash', true),
    ('UNI', 'Uniswap', 'uniswap', true),
    ('DOGE', 'Dogecoin', 'dogecoin', true),
    ('AVAX', 'Avalanche', 'avalanche-2', true),
    ('MATIC', 'Polygon', 'matic-network', true),
    ('SOL', 'Solana', 'solana', true),
    ('ATOM', 'Cosmos', 'cosmos', true)
ON CONFLICT (symbol) DO NOTHING;

-- Insert sample exchanges
INSERT INTO crypto_exchanges (exchange_id, name, country, trust_score, is_centralized) VALUES
    ('binance', 'Binance', 'Malta', 10, true),
    ('coinbase-pro', 'Coinbase Pro', 'United States', 10, true),
    ('kraken', 'Kraken', 'United States', 10, true),
    ('huobi-global', 'Huobi Global', 'Singapore', 9, true),
    ('okex', 'OKEx', 'Malta', 9, true),
    ('uniswap', 'Uniswap', null, 8, false),
    ('sushiswap', 'SushiSwap', null, 7, false)
ON CONFLICT (exchange_id) DO NOTHING;

-- Log successful crypto initialization
DO $$
BEGIN
    RAISE NOTICE 'Cryptocurrency database tables initialized successfully at %', NOW();
    RAISE NOTICE 'Added tables: crypto_assets, crypto_portfolio, crypto_transactions, crypto_alerts, etc.';
END
$$;

-- Log successful initialization
DO $$
BEGIN
    RAISE NOTICE 'Required database tables initialized successfully at %', NOW();
END
$$;