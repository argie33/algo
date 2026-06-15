-- Migration 071: Add standalone date indexes to speed up MAX(date) health checks
-- swing_trader_scores and sector_ranking only have composite (symbol/sector, date)
-- indexes. SELECT MAX(date) must scan the full composite index, which times out
-- at 10s for large tables. A standalone date index lets Postgres find MAX(date)
-- in O(log n) via a single backward index scan.

CREATE INDEX CONCURRENTLY IF NOT EXISTS idx_swing_trader_scores_date
    ON swing_trader_scores(date);

CREATE INDEX CONCURRENTLY IF NOT EXISTS idx_sector_ranking_date
    ON sector_ranking(date);
