-- Migration 1275: Widen algo_trades/algo_positions/algo_trades_archive.exit_reason to VARCHAR(255)
--
-- Root cause of the 2026-09-08 live StringDataRightTruncation crash (see
-- algo/orchestrator/phase9_reconciliation.py's comment near the reconciliation-note repair
-- block): lambda/db-init/schema.sql has declared algo_trades.exit_reason VARCHAR(255) since
-- the table was first created (commit 9085f1ad5, 2026-07-07), but the actual deployed columns
-- were never altered to match - live-confirmed 2026-09-09 via information_schema.columns
-- against the real local dev DB (DB_NAME=stocks): algo_trades, algo_positions, and
-- algo_trades_archive.exit_reason are all VARCHAR(100), not 255. schema.sql only governs
-- fresh CREATE TABLE, so this drift was invisible to anyone reading schema.sql as the source
-- of truth. The 2026-09-08 fix only shortened the one string template that happened to
-- overflow (phase9_reconciliation.py, [:100] slice) - it did not close the drift itself, so
-- any other exit_reason-writing call site (executor_exit_handler.py, phase6/8, etc.) remained
-- exposed to the same crash class.
--
-- This migration makes the live schema match the already-intended 255-char width. Run
-- alongside this same commit's defensive [:255] truncation guard added at every exit_reason
-- write site (belt-and-suspenders: this widens the column, the code guard means a future
-- write can never crash regardless of the column's actual deployed width in any environment).

ALTER TABLE algo_trades ALTER COLUMN exit_reason TYPE VARCHAR(255);
ALTER TABLE algo_positions ALTER COLUMN exit_reason TYPE VARCHAR(255);
ALTER TABLE algo_trades_archive ALTER COLUMN exit_reason TYPE VARCHAR(255);
