-- Migration 1221: Add stock_scores_history for tracking score/rank movement over time
--
-- stock_scores (schema.sql) is a symbol-keyed snapshot table: every loader run
-- (load_stock_scores.py) overwrites each symbol's row in place via BulkInsertManager's
-- ON CONFLICT (symbol) DO UPDATE. There has never been anywhere to see how a stock's
-- composite score or rank has moved day over day - only "what is it right now".
--
-- This table adds a (symbol, score_date) snapshot written once per trading day by
-- load_stock_scores.py's post_run() (after RS percentiles are finalized, so the ranking
-- is on the same completed run's data), keyed to survive daily reruns idempotently
-- (ON CONFLICT DO UPDATE, not a pure append) instead of growing duplicate/noisy rows.
--
-- composite_rank is computed once here (RANK() OVER composite_score DESC) rather than
-- recomputed on every read, so historical rank reflects the universe as scored that day,
-- not today's universe.

CREATE TABLE IF NOT EXISTS stock_scores_history (
    symbol VARCHAR(20) NOT NULL,
    score_date DATE NOT NULL,
    composite_score NUMERIC(5, 2),
    composite_rank INTEGER,
    momentum_score NUMERIC(5, 2),
    quality_score NUMERIC(5, 2),
    growth_score NUMERIC(5, 2),
    value_score NUMERIC(5, 2),
    positioning_score NUMERIC(5, 2),
    stability_score NUMERIC(5, 2),
    rs_percentile NUMERIC(5, 2),
    data_completeness NUMERIC(5, 2),
    updated_at TIMESTAMP WITH TIME ZONE DEFAULT CURRENT_TIMESTAMP,
    PRIMARY KEY (symbol, score_date)
);

CREATE INDEX IF NOT EXISTS idx_stock_scores_history_symbol_date
    ON stock_scores_history(symbol, score_date DESC);
CREATE INDEX IF NOT EXISTS idx_stock_scores_history_date_rank
    ON stock_scores_history(score_date, composite_rank);
