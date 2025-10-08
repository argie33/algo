-- Performance optimization: Add indexes to analyst_upgrade_downgrade table
-- These indexes significantly improve query performance on AWS RDS db.t3.micro

-- Index for date-based queries (most common query pattern)
CREATE INDEX IF NOT EXISTS idx_analyst_upgrade_downgrade_date
ON analyst_upgrade_downgrade (date DESC);

-- Index for symbol-based lookups
CREATE INDEX IF NOT EXISTS idx_analyst_upgrade_downgrade_symbol
ON analyst_upgrade_downgrade (symbol);

-- Composite index for symbol + date queries
CREATE INDEX IF NOT EXISTS idx_analyst_upgrade_downgrade_symbol_date
ON analyst_upgrade_downgrade (symbol, date DESC);

-- Analyze table to update statistics
ANALYZE analyst_upgrade_downgrade;
