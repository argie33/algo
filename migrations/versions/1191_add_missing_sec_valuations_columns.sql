-- Migration 1191: Add missing sec_valuations columns (EV metrics, dividend_yield, data_source, forward_pe)
--
-- ISSUE: migration 1011 (this session, replicating an untracked-drift table create for
-- sec_valuations - see that migration's own comment) only included the columns present in
-- that historical migration file's CREATE TABLE, but loaders/load_sec_valuations.py's real
-- row dict (_compute_valuation_ratios) has grown several more fields since: total_debt,
-- total_cash, enterprise_value, ebitda (EV/EBITDA inputs), dividend_yield, ev_ebitda,
-- ev_revenue, data_source, and forward_pe. All were silently dropped on every write
-- (non-marker columns, silent-drop per utils/bulk_insert_manager.py's governance-marker
-- distinction) - confirmed live: loaders/load_value_quality_growth_metrics.py's own
-- `SELECT total_debt, total_cash, ebitda FROM sec_valuations` crashes with UndefinedColumn,
-- caught by that loader's broad `except Exception` and silently marking value_metrics/
-- quality_metrics/growth_metrics unavailable for every symbol on this run.

ALTER TABLE sec_valuations
    ADD COLUMN IF NOT EXISTS data_source VARCHAR(50),
    ADD COLUMN IF NOT EXISTS total_debt NUMERIC(20, 2),
    ADD COLUMN IF NOT EXISTS total_cash NUMERIC(20, 2),
    ADD COLUMN IF NOT EXISTS enterprise_value NUMERIC(20, 2),
    ADD COLUMN IF NOT EXISTS ebitda NUMERIC(20, 2),
    ADD COLUMN IF NOT EXISTS dividend_yield NUMERIC(8, 4),
    ADD COLUMN IF NOT EXISTS ev_ebitda NUMERIC(10, 2),
    ADD COLUMN IF NOT EXISTS ev_revenue NUMERIC(10, 2),
    ADD COLUMN IF NOT EXISTS forward_pe NUMERIC(10, 2);
