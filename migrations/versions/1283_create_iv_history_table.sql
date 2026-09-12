-- Migration 1283: Create iv_history table.
--
-- This table has never existed in the local/dev database even though migration 091
-- (2026-08-17) already ran `ALTER TABLE IF EXISTS iv_history ADD COLUMN ...` against it -
-- a silent no-op against a nonexistent table. signal_options.py's iv_rank_signal() has
-- therefore always returned data_unavailable in this environment. Root cause: the loader
-- that was supposed to populate this table (loaders/load_options_chains.py) was deleted
-- 2026-07-11 (commit 7896f85a9) a month before migration 091, as "unfinished" - its
-- _insert_iv_history() queried this exact table for 252 days of prior history BEFORE ever
-- inserting a row, so it could never bootstrap itself from empty. scripts/options_data_loader.py
-- (goal session 2026-09-12, options POC data pipeline) fixes that by inserting first and
-- computing the 52w range from whatever history exists so far, so this table now has a
-- real writer that can actually accumulate data from a cold start.
CREATE TABLE IF NOT EXISTS iv_history (
    id SERIAL PRIMARY KEY,
    symbol VARCHAR(20) NOT NULL,
    date DATE NOT NULL,
    current_iv DECIMAL(8, 4) NOT NULL,
    iv_52w_high DECIMAL(8, 4) NOT NULL,
    iv_52w_low DECIMAL(8, 4) NOT NULL,
    created_at TIMESTAMP WITHOUT TIME ZONE NOT NULL DEFAULT CURRENT_TIMESTAMP,
    UNIQUE (symbol, date)
);

CREATE INDEX IF NOT EXISTS idx_iv_history_symbol_date ON iv_history(symbol, date DESC);
