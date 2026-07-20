-- Migration 1141: Add stock_count/avg_score to sector_performance, sector_ranking, industry_ranking
-- Date: 2026-07-20
--
-- ROOT CAUSE: loaders/load_sector_industry_daily.py computes stock_count (breadth - how many
-- symbols back this sector/industry's number) in every one of its 3 aggregate CTEs
-- (sector_weighted_avg, sector_stats, industry_stats), and avg_score (the raw average
-- composite_score the ranking's RANK() is computed from) in the latter two - but none of
-- these columns existed on any of the 3 target tables, so the values were computed in SQL
-- and then discarded at the final INSERT...SELECT with no column to land in. stock_count in
-- particular is a meaningful confidence signal for a ranking - "#1 of 3 stocks" and "#1 of
-- 200 stocks" are very different claims and were previously indistinguishable downstream.

BEGIN;

ALTER TABLE sector_performance ADD COLUMN IF NOT EXISTS stock_count INTEGER;
ALTER TABLE sector_ranking ADD COLUMN IF NOT EXISTS stock_count INTEGER;
ALTER TABLE sector_ranking ADD COLUMN IF NOT EXISTS avg_score NUMERIC(6, 2);
ALTER TABLE industry_ranking ADD COLUMN IF NOT EXISTS stock_count INTEGER;
ALTER TABLE industry_ranking ADD COLUMN IF NOT EXISTS avg_score NUMERIC(6, 2);

COMMENT ON COLUMN sector_performance.stock_count IS
    'Number of distinct symbols contributing to this sector''s return_pct. Column was missing entirely before migration 1141 - the loader computed this in its CTE but had nowhere to put it.';
COMMENT ON COLUMN sector_ranking.stock_count IS
    'Number of distinct scored symbols in this sector - breadth/confidence signal for current_rank. Column was missing entirely before migration 1141.';
COMMENT ON COLUMN sector_ranking.avg_score IS
    'Average composite_score across this sector''s scored symbols - the raw value current_rank is ranked by. Column was missing entirely before migration 1141.';
COMMENT ON COLUMN industry_ranking.stock_count IS
    'Number of distinct scored symbols in this industry - breadth/confidence signal for current_rank. Column was missing entirely before migration 1141.';
COMMENT ON COLUMN industry_ranking.avg_score IS
    'Average composite_score across this industry''s scored symbols - the raw value current_rank is ranked by. Column was missing entirely before migration 1141.';

COMMIT;
