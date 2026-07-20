-- Migration 1132: Drop orphaned algo_signals_evaluated table
-- Date: 2026-07-20
--
-- ISSUE: The algo_signals_evaluated table was meant to be an audit trail showing which filter
-- tiers passed/failed for each signal, but its only writer (algo_filter_pipeline.py::_persist_signal_evaluation)
-- was accidentally deleted as a side effect of commit c45211720 [2026-05-31] during a refactoring.
--
-- IMPACT:
-- - No code has written to this table since 2026-06-03 (47+ days)
-- - No code reads from this table (all queries updated to use algo_signals)
-- - data_loader_status shows status='COMPLETED' but age=None (dead data)
-- - Table consumes storage for 1M+ rows with no value
--
-- CLEANUP:
-- - Remove from API handler reference lists
-- - Update daily_report.py to document the historical context
-- - Drop the table and indexes

BEGIN;

-- Drop indexes first
DROP INDEX IF EXISTS idx_algo_signals_evaluated_date;
DROP INDEX IF EXISTS idx_algo_signals_evaluated_symbol;
DROP INDEX IF EXISTS algo_signals_evaluated_signal_date_symbol_source_timeframe_key;
DROP INDEX IF EXISTS algo_signals_evaluated_pkey;

-- Drop the table
DROP TABLE IF EXISTS algo_signals_evaluated CASCADE;

-- Remove from data_loader_status tracking
DELETE FROM data_loader_status WHERE table_name = 'algo_signals_evaluated';

COMMIT;
