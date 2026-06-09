-- Migration 002: Add missing loader tracking and data staleness columns
-- These columns are written by loaders but absent from the current schema,
-- causing one warning log per row per symbol (slowing loaders significantly).
-- All columns are nullable with no default — safe to add on live tables
-- without locking or rewriting existing rows.

-- data_loader_status: execution timing and completion percentage tracking
ALTER TABLE data_loader_status
    ADD COLUMN IF NOT EXISTS execution_started TIMESTAMP NULL,
    ADD COLUMN IF NOT EXISTS execution_completed TIMESTAMP NULL,
    ADD COLUMN IF NOT EXISTS completion_pct NUMERIC NULL,
    ADD COLUMN IF NOT EXISTS symbol_count INTEGER NULL,
    ADD COLUMN IF NOT EXISTS symbols_loaded INTEGER NULL;

-- signal_quality_scores: staleness of each upstream data source per row
ALTER TABLE signal_quality_scores
    ADD COLUMN IF NOT EXISTS buy_sell_daily_age_days INTEGER NULL,
    ADD COLUMN IF NOT EXISTS technical_data_age_days INTEGER NULL,
    ADD COLUMN IF NOT EXISTS trend_template_age_days INTEGER NULL;

-- buy_sell_daily: staleness of technical data used when computing signals
ALTER TABLE buy_sell_daily
    ADD COLUMN IF NOT EXISTS technical_data_age_days INTEGER NULL;
