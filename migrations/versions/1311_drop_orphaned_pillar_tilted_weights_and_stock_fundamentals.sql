-- Migration 1311: drop the 5 orphaned pillar *_tilted_weight columns from stock_scores, and
-- drop the entire orphaned stock_fundamentals table.
--
-- PILLAR TILTED-WEIGHT COLUMNS (momentum/quality/value/growth/risk_tilted_weight): live-
-- verified 2026-09-19 that nothing in the codebase writes to any of them - a repo-wide grep
-- for `UPDATE stock_scores` combined with `tilted` finds zero hits. 1309's own commit message
-- claimed "loaders/stock_scores/market_cap_tilt.py, restored the same day, computes/writes
-- them every run" - that file does not exist (it was deleted as confirmed-orphaned in commit
-- 593680e04 "FIX: scores endpoints return raw unfiltered rows..."), so that claim was stale/
-- wrong by the time this migration was written. The live, correct implementation
-- (algo/signals/market_cap_tilt.py's compute_tilted_weights()) computes tilted weight at
-- REQUEST time from stock_scores.*_score + value_metrics.market_cap and returns it in the API
-- response - it never persists to these columns. Same "one solution, then a second
-- implementation left the first one's columns behind as dead weight" pattern 1309 already
-- fixed for composite_tilted_weight; this finishes the same cleanup for its 5 pillar siblings.
--
-- STOCK_FUNDAMENTALS: NOT a table (correction after this migration first failed with
-- '"stock_fundamentals" is not a table') - it's a VIEW that already derives every score
-- column live from stock_scores (sc.composite_score/momentum_score/quality_score/value_score,
-- sc.risk_score AS stability_score, sc.composite_score AS generational_score - confirmed via
-- pg_views.definition), so it was never actually a second copy of the data, just an unused
-- read path onto the real table. Dropped anyway: zero live readers or writers anywhere in the
-- codebase - confirmed via a repo-wide grep for `FROM stock_fundamentals`/
-- `JOIN stock_fundamentals` (zero hits) and for the name generally (only a stale code comment
-- in loaders/load_signal_quality_scores.py and an entry in utils/db/sql_safety.py's
-- write-allowlist, neither a real reader/writer) - dead surface area, not dead data.

ALTER TABLE stock_scores DROP COLUMN IF EXISTS momentum_tilted_weight;
ALTER TABLE stock_scores DROP COLUMN IF EXISTS quality_tilted_weight;
ALTER TABLE stock_scores DROP COLUMN IF EXISTS value_tilted_weight;
ALTER TABLE stock_scores DROP COLUMN IF EXISTS growth_tilted_weight;
ALTER TABLE stock_scores DROP COLUMN IF EXISTS risk_tilted_weight;

DROP VIEW IF EXISTS stock_fundamentals;
