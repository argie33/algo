-- ════════════════════════════════════════════════════════════════════════════
-- Schema Migration: Bring existing databases in sync with current runtime code
-- ════════════════════════════════════════════════════════════════════════════
-- This script adds all columns that the runtime code tries to insert/query
-- but are missing from the DDL. Run this ONCE on any existing database.
-- Generated: 2026-05-09

-- ════════════════════════════════════════════════════════════════════════════
-- MIGRATION 1: algo_trades table — add all missing columns
-- ════════════════════════════════════════════════════════════════════════════

ALTER TABLE algo_trades
    ADD COLUMN IF NOT EXISTS signal_quality_score INTEGER,
    ADD COLUMN IF NOT EXISTS trend_template_score DECIMAL(8, 4),
    ADD COLUMN IF NOT EXISTS swing_score DECIMAL(8, 4),
    ADD COLUMN IF NOT EXISTS swing_grade VARCHAR(20),
    ADD COLUMN IF NOT EXISTS base_type VARCHAR(50),
    ADD COLUMN IF NOT EXISTS base_quality VARCHAR(50),
    ADD COLUMN IF NOT EXISTS stage_phase INTEGER,
    ADD COLUMN IF NOT EXISTS sector VARCHAR(50),
    ADD COLUMN IF NOT EXISTS industry VARCHAR(100),
    ADD COLUMN IF NOT EXISTS rs_percentile DECIMAL(8, 4),
    ADD COLUMN IF NOT EXISTS market_exposure_at_entry DECIMAL(8, 4),
    ADD COLUMN IF NOT EXISTS exposure_tier_at_entry VARCHAR(30),
    ADD COLUMN IF NOT EXISTS stop_method VARCHAR(50),
    ADD COLUMN IF NOT EXISTS stop_reasoning TEXT,
    ADD COLUMN IF NOT EXISTS swing_components JSONB,
    ADD COLUMN IF NOT EXISTS advanced_components JSONB,
    ADD COLUMN IF NOT EXISTS bracket_order BOOLEAN DEFAULT FALSE,
    ADD COLUMN IF NOT EXISTS reentry_count INTEGER DEFAULT 0,
    ADD COLUMN IF NOT EXISTS prior_trade_id VARCHAR(100),
    ADD COLUMN IF NOT EXISTS partial_exits_log JSONB,
    ADD COLUMN IF NOT EXISTS partial_exit_count INTEGER DEFAULT 0,
    ADD COLUMN IF NOT EXISTS last_partial_exit_date DATE;

-- ════════════════════════════════════════════════════════════════════════════
-- MIGRATION 2: data_patrol_log table — fix column names and add missing columns
-- ════════════════════════════════════════════════════════════════════════════

-- Rename or add patrol_run_id if it doesn't exist
ALTER TABLE data_patrol_log
    ADD COLUMN IF NOT EXISTS patrol_run_id VARCHAR(100),
    ADD COLUMN IF NOT EXISTS message TEXT,
    ADD COLUMN IF NOT EXISTS target_table VARCHAR(80);

-- Rename table_name to target_table if needed (this is idempotent because we just added target_table)
-- If table_name exists and target_table doesn't, copy the data
UPDATE data_patrol_log
SET target_table = table_name
WHERE target_table IS NULL AND table_name IS NOT NULL;

-- Convert details to JSONB if it's TEXT
ALTER TABLE data_patrol_log
    ALTER COLUMN details TYPE JSONB USING CASE
        WHEN details::text ~ '^\{' THEN details::jsonb
        ELSE jsonb_build_object('raw_text', details)
    END;

-- Add patrol_date if missing
ALTER TABLE data_patrol_log
    ADD COLUMN IF NOT EXISTS patrol_date DATE;

-- Set patrol_date to created_at for existing rows without a patrol_date
UPDATE data_patrol_log
SET patrol_date = DATE(created_at)
WHERE patrol_date IS NULL;

-- ════════════════════════════════════════════════════════════════════════════
-- Verification: Check that all tables have required columns
-- ════════════════════════════════════════════════════════════════════════════

-- List all columns in algo_trades (should show 22 new columns added)
-- \d algo_trades

-- List all columns in data_patrol_log (should show patrol_run_id, message, target_table)
-- \d data_patrol_log
