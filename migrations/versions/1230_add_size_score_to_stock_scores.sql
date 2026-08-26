-- Migration 1230: Add size_score column to stock_scores and stock_scores_history
--
-- Size (market cap, Fama-French SMB / Banz 1981) promoted from a 20%-weighted sub-component
-- inside the Value pillar to its own top-level 7th composite pillar (2026-08-26). Evidence:
-- size_proxy tested at t=7.63 multivariate / t=4.44 univariate (110 months 2017-2026, median
-- 6,505 symbols) - more than 3x every other pillar's own coefficient, confirmed 4 separate
-- times across 2 days. See loaders/load_stock_scores.py's StockScoresLoader._score_size and
-- _compute_stock_score's "SIZE PROMOTED TO 7TH PILLAR" docstring section for the full trail.

BEGIN;

ALTER TABLE stock_scores
ADD COLUMN IF NOT EXISTS size_score NUMERIC(5, 2);

ALTER TABLE stock_scores_history
ADD COLUMN IF NOT EXISTS size_score NUMERIC(5, 2);

COMMIT;
