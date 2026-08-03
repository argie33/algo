-- Migration 1182: Add macd, roc_20d/60d/120d/252d to technical_data_daily
--
-- ISSUE: loaders/load_technical_indicators.py writes symbol_df["macd"] and
-- roc_20d/roc_60d/roc_120d/roc_252d (rate-of-change over 20/60/120/252 trading days) into
-- technical_data_daily, and lambda/api/routes/scores.py's stock-scores query reads all 5
-- columns back out - but none of the 5 was ever added as a versioned migration (same
-- untracked-drift class as migrations 062/063/1181: a column referenced in real, active
-- loader/API code with no corresponding CREATE/ALTER anywhere in migrations/versions/).
-- technical_data_daily already has separate macd_line/macd_signal/macd_histogram columns
-- (migration 119, on momentum_metrics - a different table) - "macd" here is a distinct,
-- additional plain MACD line value the technical-indicators loader computes directly.
--
-- Confirmed live: a local dev database missing these columns 503s on GET /api/scores with
-- `UndefinedColumn: column "macd" does not exist`, and load_technical_indicators.py would
-- fail the same way on its own write.

ALTER TABLE technical_data_daily
    ADD COLUMN IF NOT EXISTS macd NUMERIC(10, 4),
    ADD COLUMN IF NOT EXISTS roc_20d NUMERIC(10, 2),
    ADD COLUMN IF NOT EXISTS roc_60d NUMERIC(10, 2),
    ADD COLUMN IF NOT EXISTS roc_120d NUMERIC(10, 2),
    ADD COLUMN IF NOT EXISTS roc_252d NUMERIC(10, 2);

COMMENT ON COLUMN technical_data_daily.macd IS
    'MACD line (12-day EMA - 26-day EMA), computed directly by loaders/load_technical_indicators.py - distinct from momentum_metrics.macd_line/macd_signal (migration 119, different table).';
COMMENT ON COLUMN technical_data_daily.roc_20d IS 'Rate of change over 20 trading days: (close/close_20d_ago - 1) * 100.';
COMMENT ON COLUMN technical_data_daily.roc_60d IS 'Rate of change over 60 trading days.';
COMMENT ON COLUMN technical_data_daily.roc_120d IS 'Rate of change over 120 trading days.';
COMMENT ON COLUMN technical_data_daily.roc_252d IS 'Rate of change over 252 trading days (~1 year).';
