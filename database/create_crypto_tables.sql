-- Cryptocurrency Database Schema
-- Created: 2025-07-17
-- Purpose: Store cryptocurrency market data, portfolio information, and related metrics

-- Drop existing tables if they exist (for clean recreation)
DROP TABLE IF EXISTS crypto_portfolio CASCADE;
DROP TABLE IF EXISTS crypto_price_history CASCADE;
DROP TABLE IF EXISTS crypto_technical_indicators CASCADE;
DROP TABLE IF EXISTS crypto_news CASCADE;
DROP TABLE IF EXISTS crypto_symbols CASCADE;
DROP TABLE IF EXISTS defi_protocols CASCADE;
DROP TABLE IF EXISTS crypto_market_data CASCADE;

-- Cryptocurrency symbols and metadata
CREATE TABLE crypto_symbols (
    id SERIAL PRIMARY KEY,
    symbol VARCHAR(20) NOT NULL UNIQUE,
    name VARCHAR(100) NOT NULL,
    full_name VARCHAR(200),
    description TEXT,
    website VARCHAR(255),
    category VARCHAR(50),
    rank INTEGER,
    market_cap_rank INTEGER,
    is_active BOOLEAN DEFAULT true,
    total_supply BIGINT,
    max_supply BIGINT,
    created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
    updated_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP
);

-- Real-time cryptocurrency market data
CREATE TABLE crypto_market_data (
    id SERIAL PRIMARY KEY,
    symbol VARCHAR(20) NOT NULL REFERENCES crypto_symbols(symbol),
    price_usd DECIMAL(20, 8) NOT NULL,
    market_cap_usd BIGINT,
    volume_24h_usd BIGINT,
    circulating_supply BIGINT,
    price_change_24h DECIMAL(20, 8),
    price_change_percentage_24h DECIMAL(10, 4),
    price_change_7d DECIMAL(20, 8),
    price_change_percentage_7d DECIMAL(10, 4),
    price_change_30d DECIMAL(20, 8),
    price_change_percentage_30d DECIMAL(10, 4),
    high_24h DECIMAL(20, 8),
    low_24h DECIMAL(20, 8),
    ath DECIMAL(20, 8),
    ath_date TIMESTAMP,
    atl DECIMAL(20, 8),
    atl_date TIMESTAMP,
    last_updated TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
    
    -- Indexes for performance
    INDEX idx_crypto_market_symbol (symbol),
    INDEX idx_crypto_market_updated (last_updated),
    INDEX idx_crypto_market_cap (market_cap_usd),
    INDEX idx_crypto_market_volume (volume_24h_usd)
);

-- Historical price data for charts and analysis
CREATE TABLE crypto_price_history (
    id SERIAL PRIMARY KEY,
    symbol VARCHAR(20) NOT NULL REFERENCES crypto_symbols(symbol),
    timestamp TIMESTAMP NOT NULL,
    price_usd DECIMAL(20, 8) NOT NULL,
    volume_usd BIGINT,
    market_cap_usd BIGINT,
    timeframe VARCHAR(10) NOT NULL, -- '1m', '5m', '1h', '1d', '1w', '1M'
    
    -- Composite index for efficient queries
    UNIQUE(symbol, timestamp, timeframe),
    INDEX idx_crypto_price_symbol_time (symbol, timestamp),
    INDEX idx_crypto_price_timeframe (timeframe),
    INDEX idx_crypto_price_timestamp (timestamp)
);

-- Technical indicators for cryptocurrency analysis
CREATE TABLE crypto_technical_indicators (
    id SERIAL PRIMARY KEY,
    symbol VARCHAR(20) NOT NULL REFERENCES crypto_symbols(symbol),
    timestamp TIMESTAMP NOT NULL,
    timeframe VARCHAR(10) NOT NULL, -- '1h', '4h', '1d', '1w'
    rsi DECIMAL(10, 4),
    macd DECIMAL(20, 8),
    macd_signal DECIMAL(20, 8),
    macd_histogram DECIMAL(20, 8),
    sma_20 DECIMAL(20, 8),
    sma_50 DECIMAL(20, 8),
    sma_200 DECIMAL(20, 8),
    ema_20 DECIMAL(20, 8),
    ema_50 DECIMAL(20, 8),
    bollinger_upper DECIMAL(20, 8),
    bollinger_middle DECIMAL(20, 8),
    bollinger_lower DECIMAL(20, 8),
    volume_sma DECIMAL(20, 8),
    stochastic_k DECIMAL(10, 4),
    stochastic_d DECIMAL(10, 4),
    williams_r DECIMAL(10, 4),
    atr DECIMAL(20, 8),
    
    -- Composite index for efficient queries
    UNIQUE(symbol, timestamp, timeframe),
    INDEX idx_crypto_tech_symbol_time (symbol, timestamp),
    INDEX idx_crypto_tech_timeframe (timeframe)
);

-- User cryptocurrency portfolio positions
CREATE TABLE crypto_portfolio (
    id SERIAL PRIMARY KEY,
    user_id UUID NOT NULL, -- References users table from auth system
    symbol VARCHAR(20) NOT NULL REFERENCES crypto_symbols(symbol),
    quantity DECIMAL(30, 18) NOT NULL, -- High precision for crypto quantities
    purchase_price DECIMAL(20, 8) NOT NULL,
    purchase_date TIMESTAMP NOT NULL,
    purchase_value DECIMAL(20, 8) GENERATED ALWAYS AS (quantity * purchase_price) STORED,
    notes TEXT,
    is_active BOOLEAN DEFAULT true,
    created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
    updated_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
    
    -- Indexes for performance
    INDEX idx_crypto_portfolio_user (user_id),
    INDEX idx_crypto_portfolio_symbol (symbol),
    INDEX idx_crypto_portfolio_user_symbol (user_id, symbol),
    INDEX idx_crypto_portfolio_active (is_active),
    INDEX idx_crypto_portfolio_date (purchase_date)
);

-- Cryptocurrency news and sentiment data
CREATE TABLE crypto_news (
    id SERIAL PRIMARY KEY,
    title VARCHAR(500) NOT NULL,
    content TEXT,
    summary TEXT,
    source VARCHAR(100) NOT NULL,
    author VARCHAR(100),
    url VARCHAR(1000) UNIQUE,
    published_at TIMESTAMP NOT NULL,
    category VARCHAR(50), -- 'defi', 'nft', 'regulation', 'adoption', 'technical'
    related_symbols VARCHAR(200)[], -- Array of related crypto symbols
    sentiment_score DECIMAL(10, 4), -- -1.0 to 1.0
    sentiment_label VARCHAR(20), -- 'positive', 'negative', 'neutral'
    sentiment_confidence DECIMAL(10, 4), -- 0.0 to 1.0
    impact_score DECIMAL(10, 4), -- 0.0 to 100.0
    relevance_score DECIMAL(10, 4), -- 0.0 to 100.0
    keywords VARCHAR(100)[],
    is_breaking BOOLEAN DEFAULT false,
    view_count INTEGER DEFAULT 0,
    created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
    
    -- Indexes for performance
    INDEX idx_crypto_news_published (published_at),
    INDEX idx_crypto_news_source (source),
    INDEX idx_crypto_news_category (category),
    INDEX idx_crypto_news_sentiment (sentiment_label),
    INDEX idx_crypto_news_symbols (related_symbols),
    INDEX idx_crypto_news_impact (impact_score),
    INDEX idx_crypto_news_breaking (is_breaking)
);

-- DeFi protocols and metrics
CREATE TABLE defi_protocols (
    id SERIAL PRIMARY KEY,
    name VARCHAR(100) NOT NULL UNIQUE,
    symbol VARCHAR(20),
    category VARCHAR(50) NOT NULL, -- 'dex', 'lending', 'yield', 'derivatives', 'insurance'
    description TEXT,
    website VARCHAR(255),
    twitter VARCHAR(100),
    discord VARCHAR(255),
    telegram VARCHAR(255),
    tvl_usd BIGINT, -- Total Value Locked
    tvl_change_24h DECIMAL(10, 4),
    tvl_change_7d DECIMAL(10, 4),
    volume_24h BIGINT,
    volume_change_24h DECIMAL(10, 4),
    users_24h INTEGER,
    transactions_24h INTEGER,
    fees_24h BIGINT,
    revenue_24h BIGINT,
    token_price DECIMAL(20, 8),
    token_supply BIGINT,
    token_market_cap BIGINT,
    apy_min DECIMAL(10, 4),
    apy_max DECIMAL(10, 4),
    is_active BOOLEAN DEFAULT true,
    risk_score DECIMAL(10, 4), -- 0.0 to 100.0
    audit_status VARCHAR(50), -- 'audited', 'unaudited', 'partially_audited'
    last_updated TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
    created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
    
    -- Indexes for performance
    INDEX idx_defi_category (category),
    INDEX idx_defi_tvl (tvl_usd),
    INDEX idx_defi_volume (volume_24h),
    INDEX idx_defi_active (is_active),
    INDEX idx_defi_updated (last_updated)
);

-- Insert sample cryptocurrency data
INSERT INTO crypto_symbols (symbol, name, full_name, category, rank, market_cap_rank) VALUES
('BTC', 'Bitcoin', 'Bitcoin (BTC)', 'cryptocurrency', 1, 1),
('ETH', 'Ethereum', 'Ethereum (ETH)', 'smart-contract', 2, 2),
('BNB', 'BNB', 'BNB (BNB)', 'exchange-token', 3, 3),
('XRP', 'XRP', 'XRP (XRP)', 'payment', 4, 4),
('SOL', 'Solana', 'Solana (SOL)', 'smart-contract', 5, 5),
('USDT', 'Tether', 'Tether USD (USDT)', 'stablecoin', 6, 6),
('USDC', 'USD Coin', 'USD Coin (USDC)', 'stablecoin', 7, 7),
('ADA', 'Cardano', 'Cardano (ADA)', 'smart-contract', 8, 8),
('AVAX', 'Avalanche', 'Avalanche (AVAX)', 'smart-contract', 9, 9),
('DOGE', 'Dogecoin', 'Dogecoin (DOGE)', 'meme', 10, 10),
('MATIC', 'Polygon', 'Polygon (MATIC)', 'layer2', 11, 11),
('DOT', 'Polkadot', 'Polkadot (DOT)', 'interoperability', 12, 12),
('LINK', 'Chainlink', 'Chainlink (LINK)', 'oracle', 13, 13),
('UNI', 'Uniswap', 'Uniswap (UNI)', 'dex', 14, 14),
('AAVE', 'Aave', 'Aave (AAVE)', 'defi', 15, 15),
('CRV', 'Curve', 'Curve DAO Token (CRV)', 'dex', 16, 16),
('MKR', 'Maker', 'Maker (MKR)', 'defi', 17, 17),
('COMP', 'Compound', 'Compound (COMP)', 'defi', 18, 18),
('YFI', 'Yearn Finance', 'yearn.finance (YFI)', 'yield', 19, 19),
('SUSHI', 'SushiSwap', 'SushiSwap (SUSHI)', 'dex', 20, 20);

-- Insert sample DeFi protocols
INSERT INTO defi_protocols (name, symbol, category, description, tvl_usd, volume_24h, apy_min, apy_max) VALUES
('Uniswap', 'UNI', 'dex', 'Leading decentralized exchange protocol', 4250000000, 1250000000, 2.5, 15.7),
('Aave', 'AAVE', 'lending', 'Decentralized lending and borrowing protocol', 8900000000, 450000000, 1.2, 12.8),
('Compound', 'COMP', 'lending', 'Algorithmic money market protocol', 3100000000, 180000000, 0.8, 8.5),
('Curve', 'CRV', 'dex', 'Decentralized exchange for stable assets', 2800000000, 320000000, 3.2, 18.9),
('MakerDAO', 'MKR', 'lending', 'Decentralized autonomous organization', 5200000000, 85000000, 4.5, 6.2),
('Yearn Finance', 'YFI', 'yield', 'Yield optimization protocol', 890000000, 45000000, 5.8, 25.4),
('SushiSwap', 'SUSHI', 'dex', 'Community-driven decentralized exchange', 1200000000, 280000000, 2.1, 14.3),
('Synthetix', 'SNX', 'derivatives', 'Synthetic asset protocol', 680000000, 35000000, 8.2, 22.7),
('1inch', '1INCH', 'dex', 'DEX aggregator protocol', 420000000, 190000000, 1.5, 9.8),
('Balancer', 'BAL', 'dex', 'Automated portfolio manager and trading platform', 780000000, 95000000, 3.7, 16.2);

-- Create views for common queries

-- View for current crypto market overview
CREATE VIEW crypto_market_overview AS
SELECT 
    COUNT(*) as total_cryptocurrencies,
    SUM(market_cap_usd) as total_market_cap,
    SUM(volume_24h_usd) as total_volume_24h,
    AVG(price_change_percentage_24h) as avg_price_change_24h,
    (SELECT market_cap_usd FROM crypto_market_data WHERE symbol = 'BTC') as btc_market_cap,
    (SELECT market_cap_usd FROM crypto_market_data WHERE symbol = 'BTC') / SUM(market_cap_usd) * 100 as btc_dominance,
    (SELECT market_cap_usd FROM crypto_market_data WHERE symbol = 'ETH') / SUM(market_cap_usd) * 100 as eth_dominance
FROM crypto_market_data 
WHERE market_cap_usd IS NOT NULL;

-- View for portfolio summary by user
CREATE VIEW crypto_portfolio_summary AS
SELECT 
    cp.user_id,
    COUNT(*) as total_positions,
    SUM(cp.purchase_value) as total_cost_basis,
    SUM(cp.quantity * COALESCE(cmd.price_usd, cp.purchase_price)) as current_value,
    SUM(cp.quantity * COALESCE(cmd.price_usd, cp.purchase_price)) - SUM(cp.purchase_value) as total_pnl,
    (SUM(cp.quantity * COALESCE(cmd.price_usd, cp.purchase_price)) - SUM(cp.purchase_value)) / SUM(cp.purchase_value) * 100 as total_pnl_percentage
FROM crypto_portfolio cp
LEFT JOIN crypto_market_data cmd ON cp.symbol = cmd.symbol
WHERE cp.is_active = true
GROUP BY cp.user_id;

-- View for trending cryptocurrencies
CREATE VIEW crypto_trending AS
SELECT 
    cmd.symbol,
    cs.name,
    cmd.price_usd,
    cmd.price_change_percentage_24h,
    cmd.volume_24h_usd,
    cmd.market_cap_usd,
    -- Calculate trending score based on volume and price change
    (ABS(cmd.price_change_percentage_24h) * 0.4 + 
     (cmd.volume_24h_usd / NULLIF(cmd.market_cap_usd, 0) * 100) * 0.6) as trending_score
FROM crypto_market_data cmd
JOIN crypto_symbols cs ON cmd.symbol = cs.symbol
WHERE cmd.volume_24h_usd > 1000000 -- Minimum volume threshold
ORDER BY trending_score DESC;

-- Create functions for common calculations

-- Function to calculate portfolio allocation percentages
CREATE OR REPLACE FUNCTION calculate_crypto_portfolio_allocation(p_user_id UUID)
RETURNS TABLE(
    symbol VARCHAR(20),
    current_value DECIMAL(20, 8),
    allocation_percentage DECIMAL(10, 4)
) AS $$
BEGIN
    RETURN QUERY
    WITH portfolio_values AS (
        SELECT 
            cp.symbol,
            cp.quantity * COALESCE(cmd.price_usd, cp.purchase_price) as position_value
        FROM crypto_portfolio cp
        LEFT JOIN crypto_market_data cmd ON cp.symbol = cmd.symbol
        WHERE cp.user_id = p_user_id AND cp.is_active = true
    ),
    total_value AS (
        SELECT SUM(position_value) as total_portfolio_value
        FROM portfolio_values
    )
    SELECT 
        pv.symbol,
        pv.position_value,
        (pv.position_value / tv.total_portfolio_value * 100)::DECIMAL(10, 4)
    FROM portfolio_values pv
    CROSS JOIN total_value tv
    ORDER BY pv.position_value DESC;
END;
$$ LANGUAGE plpgsql;

-- Function to get crypto price with technical indicators
CREATE OR REPLACE FUNCTION get_crypto_with_technicals(p_symbol VARCHAR(20), p_timeframe VARCHAR(10) DEFAULT '1d')
RETURNS TABLE(
    symbol VARCHAR(20),
    price_usd DECIMAL(20, 8),
    price_change_24h DECIMAL(10, 4),
    volume_24h_usd BIGINT,
    market_cap_usd BIGINT,
    rsi DECIMAL(10, 4),
    macd DECIMAL(20, 8),
    sma_20 DECIMAL(20, 8),
    sma_50 DECIMAL(20, 8)
) AS $$
BEGIN
    RETURN QUERY
    SELECT 
        cmd.symbol,
        cmd.price_usd,
        cmd.price_change_percentage_24h,
        cmd.volume_24h_usd,
        cmd.market_cap_usd,
        cti.rsi,
        cti.macd,
        cti.sma_20,
        cti.sma_50
    FROM crypto_market_data cmd
    LEFT JOIN crypto_technical_indicators cti ON (
        cmd.symbol = cti.symbol 
        AND cti.timeframe = p_timeframe 
        AND cti.timestamp = (
            SELECT MAX(timestamp) 
            FROM crypto_technical_indicators 
            WHERE symbol = cti.symbol AND timeframe = p_timeframe
        )
    )
    WHERE cmd.symbol = p_symbol;
END;
$$ LANGUAGE plpgsql;

-- Triggers to automatically update timestamps
CREATE OR REPLACE FUNCTION update_crypto_timestamp()
RETURNS TRIGGER AS $$
BEGIN
    NEW.updated_at = CURRENT_TIMESTAMP;
    RETURN NEW;
END;
$$ LANGUAGE plpgsql;

-- Add triggers for automatic timestamp updates
CREATE TRIGGER update_crypto_symbols_timestamp
    BEFORE UPDATE ON crypto_symbols
    FOR EACH ROW
    EXECUTE FUNCTION update_crypto_timestamp();

CREATE TRIGGER update_crypto_portfolio_timestamp
    BEFORE UPDATE ON crypto_portfolio
    FOR EACH ROW
    EXECUTE FUNCTION update_crypto_timestamp();

CREATE TRIGGER update_defi_protocols_timestamp
    BEFORE UPDATE ON defi_protocols
    FOR EACH ROW
    EXECUTE FUNCTION update_crypto_timestamp();

-- Grant necessary permissions (adjust as needed for your user roles)
-- GRANT SELECT, INSERT, UPDATE, DELETE ON ALL TABLES IN SCHEMA public TO app_user;
-- GRANT USAGE, SELECT ON ALL SEQUENCES IN SCHEMA public TO app_user;
-- GRANT EXECUTE ON ALL FUNCTIONS IN SCHEMA public TO app_user;

-- Create sample data for testing (optional)
INSERT INTO crypto_market_data (symbol, price_usd, market_cap_usd, volume_24h_usd, price_change_percentage_24h, high_24h, low_24h) VALUES
('BTC', 45234.56, 885000000000, 28500000000, 3.2, 46123.45, 44567.89),
('ETH', 2847.92, 342000000000, 15200000000, 5.1, 2895.34, 2756.78),
('SOL', 94.78, 42300000000, 2100000000, -2.8, 98.45, 92.34),
('AVAX', 38.42, 14800000000, 890000000, 7.3, 39.87, 37.12),
('MATIC', 0.847, 8500000000, 520000000, -1.2, 0.863, 0.834);

-- Create indexes for performance optimization
CREATE INDEX CONCURRENTLY IF NOT EXISTS idx_crypto_market_data_composite 
ON crypto_market_data (symbol, last_updated DESC);

CREATE INDEX CONCURRENTLY IF NOT EXISTS idx_crypto_price_history_composite 
ON crypto_price_history (symbol, timeframe, timestamp DESC);

CREATE INDEX CONCURRENTLY IF NOT EXISTS idx_crypto_portfolio_user_active 
ON crypto_portfolio (user_id, is_active) WHERE is_active = true;

CREATE INDEX CONCURRENTLY IF NOT EXISTS idx_crypto_news_published_impact 
ON crypto_news (published_at DESC, impact_score DESC);

-- Add comments for documentation
COMMENT ON TABLE crypto_symbols IS 'Master table for cryptocurrency symbols and metadata';
COMMENT ON TABLE crypto_market_data IS 'Real-time cryptocurrency market data and prices';
COMMENT ON TABLE crypto_price_history IS 'Historical price data for charting and analysis';
COMMENT ON TABLE crypto_technical_indicators IS 'Technical analysis indicators for cryptocurrencies';
COMMENT ON TABLE crypto_portfolio IS 'User cryptocurrency portfolio positions';
COMMENT ON TABLE crypto_news IS 'Cryptocurrency news articles with sentiment analysis';
COMMENT ON TABLE defi_protocols IS 'DeFi protocol data and metrics';

COMMENT ON FUNCTION calculate_crypto_portfolio_allocation IS 'Calculate portfolio allocation percentages for a user';
COMMENT ON FUNCTION get_crypto_with_technicals IS 'Get cryptocurrency price data with technical indicators';

-- Analyze tables for better query planning
ANALYZE crypto_symbols;
ANALYZE crypto_market_data;
ANALYZE crypto_price_history;
ANALYZE crypto_technical_indicators;
ANALYZE crypto_portfolio;
ANALYZE crypto_news;
ANALYZE defi_protocols;