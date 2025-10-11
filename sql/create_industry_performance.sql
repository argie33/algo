-- Industry Performance Tracking Table
-- Stores daily performance metrics for industries within sectors
-- Similar to IBD industry group rankings

CREATE TABLE IF NOT EXISTS industry_performance (
    id SERIAL PRIMARY KEY,
    sector VARCHAR(100) NOT NULL,
    industry VARCHAR(200) NOT NULL,
    industry_key VARCHAR(100),

    -- Stock composition
    stock_count INTEGER DEFAULT 0,
    stock_symbols TEXT[], -- Array of symbols in this industry

    -- Price performance metrics
    avg_price_change DECIMAL(10, 4) DEFAULT 0,
    avg_change_percent DECIMAL(10, 4) DEFAULT 0,
    median_change_percent DECIMAL(10, 4) DEFAULT 0,

    -- Volume metrics
    total_volume BIGINT DEFAULT 0,
    avg_volume BIGINT DEFAULT 0,

    -- Trend analysis (IBD-style)
    performance_1d DECIMAL(10, 4) DEFAULT 0,  -- 1-day performance
    performance_5d DECIMAL(10, 4) DEFAULT 0,  -- 5-day performance
    performance_20d DECIMAL(10, 4) DEFAULT 0, -- 20-day performance (1 month)

    -- Relative strength
    rs_rating INTEGER,  -- 1-99 rating vs market (IBD-style)
    rs_vs_spy DECIMAL(10, 4), -- Relative strength vs S&P 500

    -- Momentum indicators
    momentum VARCHAR(20), -- 'Strong', 'Moderate', 'Weak'
    trend VARCHAR(20),    -- 'Uptrend', 'Downtrend', 'Sideways'

    -- Ranking
    sector_rank INTEGER,  -- Rank within sector (1 = best)
    overall_rank INTEGER, -- Rank across all industries

    -- Market cap
    total_market_cap BIGINT,
    avg_market_cap BIGINT,

    -- Timestamps
    fetched_at TIMESTAMP DEFAULT NOW(),
    updated_at TIMESTAMP DEFAULT NOW()
);

-- Indexes for performance
CREATE INDEX IF NOT EXISTS idx_industry_perf_sector ON industry_performance(sector);
CREATE INDEX IF NOT EXISTS idx_industry_perf_industry ON industry_performance(industry);
CREATE INDEX IF NOT EXISTS idx_industry_perf_date ON industry_performance(fetched_at DESC);
CREATE INDEX IF NOT EXISTS idx_industry_perf_1d ON industry_performance(performance_1d DESC);
CREATE INDEX IF NOT EXISTS idx_industry_perf_sector_rank ON industry_performance(sector, sector_rank);
CREATE INDEX IF NOT EXISTS idx_industry_overall_rank ON industry_performance(overall_rank);

-- Comments
COMMENT ON TABLE industry_performance IS 'Daily performance metrics for industry groups within sectors, with IBD-style rankings';
COMMENT ON COLUMN industry_performance.rs_rating IS 'Relative Strength rating 1-99 (IBD-style), higher is better';
COMMENT ON COLUMN industry_performance.sector_rank IS 'Rank within sector, 1 is best performing';
COMMENT ON COLUMN industry_performance.overall_rank IS 'Overall rank across all industries';
