-- Migration 1139: Add missing reason_type column to stability_metrics
-- Date: 2026-07-20
--
-- ROOT CAUSE: loaders/load_risk_metrics_daily.py's _compute_stability_row() computes a
-- "reason_type": "loader_failed" classifier on every failure branch (lines 182/213/274),
-- but _persist_stability_metrics()'s hand-written raw INSERT statement never had a column
-- slot for it - stability_metrics has no reason_type column at all, only data_unavailable/
-- reason. Unlike the bulk_insert_manager silent-drop mechanism (migrations 1135-1138), this
-- is a hand-maintained INSERT statement with its own hardcoded column list drifting from
-- what the loader actually computes - same failure mode, different mechanism.
--
-- reason_type is an established governance column already populated for quality_metrics,
-- stock_scores, and technical_data_daily (VARCHAR(50)) - stability_metrics/momentum_metrics
-- just never got it wired up when those tables were built.
--
-- Same file's _compute_momentum_row() also computes "reason_type": "loader_failed" on its
-- failure branch, and momentum_metrics (written via the generic BulkInsertManager path, not
-- a hand-written INSERT) had no column for it either - added here too so both halves of this
-- loader's output stop silently dropping the same field.

BEGIN;

ALTER TABLE stability_metrics ADD COLUMN IF NOT EXISTS reason_type VARCHAR(50);
ALTER TABLE momentum_metrics ADD COLUMN IF NOT EXISTS reason_type VARCHAR(50);

COMMENT ON COLUMN stability_metrics.reason_type IS
    'Machine-readable failure classifier (e.g. loader_failed) paired with the human-readable reason column. Column was missing entirely before migration 1139 - loader computed this but the hand-written INSERT had no slot for it.';

COMMENT ON COLUMN momentum_metrics.reason_type IS
    'Machine-readable failure classifier (e.g. loader_failed) paired with the human-readable reason column. Column was missing entirely before migration 1139 - loader computed this but bulk_insert_manager silently dropped it.';

COMMIT;
