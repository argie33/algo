-- Fix sector_ranking table schema - momentum_score numeric overflow
-- The NUMERIC(8,2) field only allows values up to 999999.99
-- When multiple stocks in a sector have large returns, the sum exceeds this limit

-- Backup the table first
ALTER TABLE sector_ranking RENAME TO sector_ranking_backup;

-- Recreate the table with correct schema
CREATE TABLE sector_ranking (
    id SERIAL PRIMARY KEY,
    sector VARCHAR(255) NOT NULL,
    date DATE NOT NULL,
    current_rank INT,
    rank_1w_ago INT,
    rank_4w_ago INT,
    rank_12w_ago INT,
    momentum_score NUMERIC(15,4),  -- Changed from NUMERIC(8,2) to allow larger values
    trend VARCHAR(50),
    created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
    updated_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
    UNIQUE(sector, date)
);

-- Restore data from backup (if any exists)
INSERT INTO sector_ranking (sector, date, current_rank, rank_1w_ago, rank_4w_ago, rank_12w_ago, momentum_score, trend)
SELECT sector, date, current_rank, rank_1w_ago, rank_4w_ago, rank_12w_ago, momentum_score, trend
FROM sector_ranking_backup
ON CONFLICT (sector, date) DO NOTHING;

-- Drop the backup table
DROP TABLE sector_ranking_backup;

-- Also fix industry_ranking table with the same issue
ALTER TABLE industry_ranking RENAME TO industry_ranking_backup;

CREATE TABLE industry_ranking (
    id SERIAL PRIMARY KEY,
    industry VARCHAR(255) NOT NULL,
    date DATE NOT NULL,
    current_rank INT,
    rank_1w_ago INT,
    rank_4w_ago INT,
    rank_12w_ago INT,
    momentum_score NUMERIC(15,4),  -- Changed from NUMERIC(8,2) to allow larger values
    stock_count INT,
    trend VARCHAR(50),
    created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
    updated_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
    UNIQUE(industry, date)
);

INSERT INTO industry_ranking (industry, date, current_rank, rank_1w_ago, rank_4w_ago, rank_12w_ago, momentum_score, stock_count, trend)
SELECT industry, date, current_rank, rank_1w_ago, rank_4w_ago, rank_12w_ago, momentum_score, stock_count, trend
FROM industry_ranking_backup
ON CONFLICT (industry, date) DO NOTHING;

DROP TABLE industry_ranking_backup;

-- Create indexes for performance
CREATE INDEX idx_sector_ranking_date ON sector_ranking(date);
CREATE INDEX idx_sector_ranking_sector ON sector_ranking(sector);
CREATE INDEX idx_sector_ranking_sector_date ON sector_ranking(sector, date);

CREATE INDEX idx_industry_ranking_date ON industry_ranking(date);
CREATE INDEX idx_industry_ranking_industry ON industry_ranking(industry);
CREATE INDEX idx_industry_ranking_industry_date ON industry_ranking(industry, date);
