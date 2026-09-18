-- Migration 1308: drop the 6 market-cap-tilted display weight columns migration 1294 added
-- to stock_scores.
--
-- REVERSES migration 1294's "compute once in a batch pass, store the result" approach.
-- User directive 2026-09-17: a display-only derived weight (market_cap * MSCI Tilt Index
-- score, renormalized) shouldn't be persisted as its own column sitting next to the real
-- pillar/composite scores - it read as a duplicate, parallel set of "scores" for the same
-- 6 things stock_scores already has real scores for.
--
-- The formula itself is NOT removed - it's centralized as the single shared implementation
-- in algo/signals/market_cap_tilt.py's compute_tilted_weights(), imported by every API
-- endpoint that displays a tilted weight (lambda/api/routes/algo_handlers/dashboard/scores.py,
-- lambda/api/routes/scores_handlers/stock_scores.py) and computed at request time over the
-- same eligible population each of those endpoints already queries, rather than 6 stored
-- columns nothing but display ever read (composite_score/pillar scores continue to drive
-- live Phase 7/8 trading logic, unaffected either way - these were always DISPLAY-only).

ALTER TABLE stock_scores DROP COLUMN IF EXISTS composite_tilted_weight;
ALTER TABLE stock_scores DROP COLUMN IF EXISTS momentum_tilted_weight;
ALTER TABLE stock_scores DROP COLUMN IF EXISTS quality_tilted_weight;
ALTER TABLE stock_scores DROP COLUMN IF EXISTS value_tilted_weight;
ALTER TABLE stock_scores DROP COLUMN IF EXISTS growth_tilted_weight;
ALTER TABLE stock_scores DROP COLUMN IF EXISTS risk_tilted_weight;
