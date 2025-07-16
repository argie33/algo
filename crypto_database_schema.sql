-- Cryptocurrency Analytics Database Schema
-- Institutional-grade crypto data structure

-- Core cryptocurrency assets table
CREATE TABLE IF NOT EXISTS crypto_assets (
    id SERIAL PRIMARY KEY,
    symbol VARCHAR(20) UNIQUE NOT NULL,
    name VARCHAR(255) NOT NULL,
    coingecko_id VARCHAR(255),
    coinmarketcap_id INTEGER,
    contract_address VARCHAR(255),
    blockchain VARCHAR(50),
    asset_type VARCHAR(50) DEFAULT 'cryptocurrency', -- cryptocurrency, defi_token, stablecoin, nft
    market_cap BIGINT,
    circulating_supply DECIMAL(30, 8),
    total_supply DECIMAL(30, 8),
    max_supply DECIMAL(30, 8),
    launch_date DATE,
    website VARCHAR(255),
    whitepaper_url VARCHAR(255),
    is_active BOOLEAN DEFAULT TRUE,
    created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
    updated_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP
);

-- Real-time price data (OHLCV)
CREATE TABLE IF NOT EXISTS crypto_prices (
    id SERIAL PRIMARY KEY,
    symbol VARCHAR(20) NOT NULL,
    timestamp TIMESTAMP NOT NULL,
    open_price DECIMAL(20, 8) NOT NULL,
    high_price DECIMAL(20, 8) NOT NULL,
    low_price DECIMAL(20, 8) NOT NULL,
    close_price DECIMAL(20, 8) NOT NULL,
    volume DECIMAL(30, 8) NOT NULL,
    volume_usd DECIMAL(30, 2),
    market_cap BIGINT,
    interval_type VARCHAR(10) DEFAULT '1h', -- 1m, 5m, 15m, 1h, 4h, 1d
    exchange VARCHAR(50) DEFAULT 'aggregate',
    created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
    UNIQUE(symbol, timestamp, interval_type, exchange)
);

-- Exchange-specific order book data
CREATE TABLE IF NOT EXISTS crypto_order_books (
    id SERIAL PRIMARY KEY,
    exchange VARCHAR(50) NOT NULL,
    symbol VARCHAR(20) NOT NULL,
    timestamp TIMESTAMP NOT NULL,
    bid_price DECIMAL(20, 8) NOT NULL,
    bid_size DECIMAL(30, 8) NOT NULL,
    ask_price DECIMAL(20, 8) NOT NULL,
    ask_size DECIMAL(30, 8) NOT NULL,
    spread_bps INTEGER, -- basis points
    depth_1pct DECIMAL(30, 2), -- liquidity within 1% of mid price
    created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP
);

-- Futures funding rates
CREATE TABLE IF NOT EXISTS crypto_funding_rates (
    id SERIAL PRIMARY KEY,
    exchange VARCHAR(50) NOT NULL,
    symbol VARCHAR(20) NOT NULL,
    timestamp TIMESTAMP NOT NULL,
    funding_rate DECIMAL(10, 8) NOT NULL,
    predicted_rate DECIMAL(10, 8),
    open_interest DECIMAL(30, 8),
    mark_price DECIMAL(20, 8),
    index_price DECIMAL(20, 8),
    created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
    UNIQUE(exchange, symbol, timestamp)
);

-- On-chain blockchain metrics
CREATE TABLE IF NOT EXISTS blockchain_metrics (
    id SERIAL PRIMARY KEY,
    blockchain VARCHAR(50) NOT NULL,
    timestamp TIMESTAMP NOT NULL,
    block_height BIGINT,
    hash_rate DECIMAL(30, 2), -- for PoW chains
    difficulty DECIMAL(30, 2),
    active_addresses INTEGER,
    new_addresses INTEGER,
    transaction_count INTEGER,
    transaction_volume DECIMAL(30, 8),
    average_tx_fee DECIMAL(20, 8),
    mempool_size INTEGER,
    network_utilization DECIMAL(5, 4), -- percentage
    created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
    UNIQUE(blockchain, timestamp)
);

-- Whale transaction tracking
CREATE TABLE IF NOT EXISTS whale_transactions (
    id SERIAL PRIMARY KEY,
    blockchain VARCHAR(50) NOT NULL,
    tx_hash VARCHAR(255) UNIQUE NOT NULL,
    from_address VARCHAR(255) NOT NULL,
    to_address VARCHAR(255) NOT NULL,
    amount DECIMAL(30, 8) NOT NULL,
    amount_usd DECIMAL(30, 2),
    symbol VARCHAR(20) NOT NULL,
    timestamp TIMESTAMP NOT NULL,
    block_number BIGINT,
    is_exchange_related BOOLEAN DEFAULT FALSE,
    exchange_name VARCHAR(50),
    direction VARCHAR(10), -- inflow, outflow, transfer
    whale_category VARCHAR(50), -- institution, individual, exchange, unknown
    created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP
);

-- Exchange flow analysis
CREATE TABLE IF NOT EXISTS exchange_flows (
    id SERIAL PRIMARY KEY,
    exchange VARCHAR(50) NOT NULL,
    symbol VARCHAR(20) NOT NULL,
    timestamp TIMESTAMP NOT NULL,
    inflow DECIMAL(30, 8) DEFAULT 0,
    outflow DECIMAL(30, 8) DEFAULT 0,
    net_flow DECIMAL(30, 8) DEFAULT 0,
    inflow_usd DECIMAL(30, 2) DEFAULT 0,
    outflow_usd DECIMAL(30, 2) DEFAULT 0,
    net_flow_usd DECIMAL(30, 2) DEFAULT 0,
    large_tx_count INTEGER DEFAULT 0, -- transactions > $1M
    created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
    UNIQUE(exchange, symbol, timestamp)
);

-- DeFi protocol metrics
CREATE TABLE IF NOT EXISTS defi_protocols (
    id SERIAL PRIMARY KEY,
    protocol_name VARCHAR(100) NOT NULL,
    blockchain VARCHAR(50) NOT NULL,
    category VARCHAR(50) NOT NULL, -- dex, lending, staking, derivatives
    tvl DECIMAL(30, 2) NOT NULL,
    tvl_change_24h DECIMAL(10, 4),
    volume_24h DECIMAL(30, 2),
    revenue_24h DECIMAL(30, 2),
    token_symbol VARCHAR(20),
    token_price DECIMAL(20, 8),
    token_market_cap BIGINT,
    treasury_value DECIMAL(30, 2),
    active_users_24h INTEGER,
    timestamp TIMESTAMP NOT NULL,
    created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP
);

-- DeFi liquidity pools
CREATE TABLE IF NOT EXISTS liquidity_pools (
    id SERIAL PRIMARY KEY,
    protocol VARCHAR(100) NOT NULL,
    pool_address VARCHAR(255) NOT NULL,
    pair_name VARCHAR(50) NOT NULL, -- e.g., ETH/USDC
    token0_symbol VARCHAR(20) NOT NULL,
    token1_symbol VARCHAR(20) NOT NULL,
    tvl DECIMAL(30, 2) NOT NULL,
    apy DECIMAL(8, 4), -- percentage
    volume_24h DECIMAL(30, 2),
    fees_24h DECIMAL(30, 2),
    impermanent_loss_risk VARCHAR(20), -- low, medium, high
    liquidity_utilization DECIMAL(5, 4),
    timestamp TIMESTAMP NOT NULL,
    created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
    UNIQUE(protocol, pool_address, timestamp)
);

-- Exchange metrics and health
CREATE TABLE IF NOT EXISTS exchange_metrics (
    id SERIAL PRIMARY KEY,
    exchange VARCHAR(50) NOT NULL,
    timestamp TIMESTAMP NOT NULL,
    volume_24h DECIMAL(30, 2) NOT NULL,
    volume_7d DECIMAL(30, 2),
    open_interest DECIMAL(30, 2),
    liquidations_24h DECIMAL(30, 2),
    liquidations_long DECIMAL(30, 2),
    liquidations_short DECIMAL(30, 2),
    trading_pairs_count INTEGER,
    active_traders_24h INTEGER,
    market_share DECIMAL(5, 4), -- percentage
    trust_score DECIMAL(3, 1), -- 1-10 scale
    api_uptime DECIMAL(5, 4), -- percentage
    withdrawal_delays INTEGER, -- minutes
    created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
    UNIQUE(exchange, timestamp)
);

-- Arbitrage opportunities
CREATE TABLE IF NOT EXISTS arbitrage_opportunities (
    id SERIAL PRIMARY KEY,
    opportunity_type VARCHAR(50) NOT NULL, -- spot, futures_basis, funding_rate
    symbol VARCHAR(20) NOT NULL,
    exchange_buy VARCHAR(50) NOT NULL,
    exchange_sell VARCHAR(50) NOT NULL,
    price_buy DECIMAL(20, 8) NOT NULL,
    price_sell DECIMAL(20, 8) NOT NULL,
    spread_percentage DECIMAL(8, 4) NOT NULL,
    estimated_profit_bps INTEGER,
    volume_opportunity DECIMAL(30, 2),
    risk_score DECIMAL(3, 1), -- 1-10 scale
    execution_complexity VARCHAR(20), -- simple, moderate, complex
    timestamp TIMESTAMP NOT NULL,
    expires_at TIMESTAMP,
    is_active BOOLEAN DEFAULT TRUE,
    created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP
);

-- Market sentiment indicators
CREATE TABLE IF NOT EXISTS crypto_sentiment (
    id SERIAL PRIMARY KEY,
    symbol VARCHAR(20) NOT NULL,
    timestamp TIMESTAMP NOT NULL,
    fear_greed_index INTEGER, -- 0-100
    social_volume INTEGER,
    social_sentiment DECIMAL(3, 2), -- -1 to 1
    google_trends_score INTEGER, -- 0-100
    github_commits INTEGER,
    reddit_mentions INTEGER,
    twitter_mentions INTEGER,
    news_sentiment DECIMAL(3, 2), -- -1 to 1
    analyst_rating VARCHAR(20), -- strong_buy, buy, hold, sell, strong_sell
    created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
    UNIQUE(symbol, timestamp)
);

-- Institutional flow tracking
CREATE TABLE IF NOT EXISTS institutional_flows (
    id SERIAL PRIMARY KEY,
    institution_type VARCHAR(50) NOT NULL, -- etf, fund, corporation, treasury
    institution_name VARCHAR(100),
    symbol VARCHAR(20) NOT NULL,
    flow_type VARCHAR(20) NOT NULL, -- inflow, outflow
    amount DECIMAL(30, 8) NOT NULL,
    amount_usd DECIMAL(30, 2) NOT NULL,
    price_at_flow DECIMAL(20, 8),
    announcement_date DATE,
    execution_date DATE,
    filing_url VARCHAR(500),
    notes TEXT,
    created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP
);

-- Stablecoin metrics
CREATE TABLE IF NOT EXISTS stablecoin_metrics (
    id SERIAL PRIMARY KEY,
    symbol VARCHAR(20) NOT NULL,
    timestamp TIMESTAMP NOT NULL,
    price DECIMAL(10, 8) NOT NULL,
    peg_deviation DECIMAL(8, 6), -- deviation from $1.00
    market_cap BIGINT NOT NULL,
    supply_change_24h DECIMAL(30, 8),
    reserve_ratio DECIMAL(5, 4), -- if applicable
    audit_status VARCHAR(50),
    redemption_volume_24h DECIMAL(30, 2),
    risk_score DECIMAL(3, 1), -- 1-10 scale
    created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
    UNIQUE(symbol, timestamp)
);

-- Create indexes for performance
CREATE INDEX IF NOT EXISTS idx_crypto_prices_symbol_timestamp ON crypto_prices(symbol, timestamp DESC);
CREATE INDEX IF NOT EXISTS idx_crypto_prices_timestamp ON crypto_prices(timestamp DESC);
CREATE INDEX IF NOT EXISTS idx_whale_transactions_timestamp ON whale_transactions(timestamp DESC);
CREATE INDEX IF NOT EXISTS idx_whale_transactions_amount_usd ON whale_transactions(amount_usd DESC);
CREATE INDEX IF NOT EXISTS idx_exchange_flows_timestamp ON exchange_flows(timestamp DESC);
CREATE INDEX IF NOT EXISTS idx_defi_protocols_tvl ON defi_protocols(tvl DESC);
CREATE INDEX IF NOT EXISTS idx_arbitrage_opportunities_spread ON arbitrage_opportunities(spread_percentage DESC);
CREATE INDEX IF NOT EXISTS idx_blockchain_metrics_timestamp ON blockchain_metrics(timestamp DESC);

-- Create update trigger function for updated_at columns
CREATE OR REPLACE FUNCTION update_crypto_updated_at_column()
RETURNS TRIGGER AS $$
BEGIN
    NEW.updated_at = CURRENT_TIMESTAMP;
    RETURN NEW;
END;
$$ language 'plpgsql';

-- Create triggers
CREATE TRIGGER update_crypto_assets_updated_at BEFORE UPDATE ON crypto_assets FOR EACH ROW EXECUTE FUNCTION update_crypto_updated_at_column();