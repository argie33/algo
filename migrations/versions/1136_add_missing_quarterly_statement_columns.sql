-- Migration 1136: Add missing data_unavailable/reason/current_assets columns to quarterly
-- financial statement tables (same silent-drop bug class as the capex mapping fix)
-- Date: 2026-07-20
--
-- ROOT CAUSE: loaders/load_financial_statements.py writes explicit data_unavailable/reason
-- markers for every quarterly statement row (schema_cols declares them, _MARKER_FIELDS lists
-- them), but quarterly_income_statement/quarterly_balance_sheet/quarterly_cash_flow never had
-- these columns - only their annual_* counterparts do. utils/bulk_insert_manager.py's
-- bulk_insert() silently filters the write to whatever columns actually exist in the target
-- table (see its "skipping columns not in DB schema" warning path), so every quarterly
-- unavailability marker the loader computes is silently discarded before the INSERT - a
-- governance violation (the flag is computed but never persisted, no different in effect from
-- the annual capex-mapping bug already fixed and documented in steering/DATA_LOADERS.md).
-- quarterly_balance_sheet was also missing current_assets (mapped from SEC's AssetsCurrent
-- concept), so quarterly current-assets/working-capital data has been silently dropped too.
--
-- No backfill: like the capex fix, existing quarterly rows were written before these columns
-- existed and their true availability/current_assets value was never recorded - NULL here
-- means "recorded before this migration", not "known available". A future full re-fetch
-- (resetting financial_statements_*_quarterly watermarks) would be needed to backfill, mirroring
-- the capex backfill already done for annual tables - left to a follow-up given quarterly SEC
-- data volume, not done unprompted here.

BEGIN;

ALTER TABLE quarterly_income_statement ADD COLUMN IF NOT EXISTS data_unavailable BOOLEAN DEFAULT FALSE;
ALTER TABLE quarterly_income_statement ADD COLUMN IF NOT EXISTS reason VARCHAR(500);

ALTER TABLE quarterly_balance_sheet ADD COLUMN IF NOT EXISTS data_unavailable BOOLEAN DEFAULT FALSE;
ALTER TABLE quarterly_balance_sheet ADD COLUMN IF NOT EXISTS reason VARCHAR(500);
ALTER TABLE quarterly_balance_sheet ADD COLUMN IF NOT EXISTS current_assets NUMERIC;

ALTER TABLE quarterly_cash_flow ADD COLUMN IF NOT EXISTS data_unavailable BOOLEAN DEFAULT FALSE;
ALTER TABLE quarterly_cash_flow ADD COLUMN IF NOT EXISTS reason VARCHAR(500);

COMMENT ON COLUMN quarterly_income_statement.data_unavailable IS
    'Whether this quarterly row is an explicit unavailability marker (see annual_income_statement for the established pattern). Column was missing entirely before migration 1136 - loader wrote this marker but bulk_insert_manager silently dropped it.';
COMMENT ON COLUMN quarterly_balance_sheet.current_assets IS
    'Mapped from SEC AssetsCurrent. Column was missing entirely before migration 1136 - loader wrote this field but bulk_insert_manager silently dropped it (same mechanism as the annual capex mapping bug).';

COMMIT;
