-- Migration 1138: Add missing reason column to aaii_sentiment
-- Date: 2026-07-20
--
-- ROOT CAUSE: loaders/load_aaii_sentiment.py computes a "reason" string (network error,
-- data format error, or unexpected error detail) on every fetch failure and includes it
-- alongside "data_unavailable": True in the marker dict it hands to BulkInsertManager
-- (lines 328/342/354) - but aaii_sentiment never had a reason column at all (only
-- data_unavailable). utils/bulk_insert_manager.py silently filters any key not present in
-- the target table's schema (logging only a WARNING, easy to miss), so this diagnostic
-- reason has been computed and discarded on every failed fetch since the loader was built.
-- Fifth confirmed instance of this exact silent-drop mechanism (see migrations 1135/1136/1137
-- for the first four: price_daily.data_source, quarterly financial statements, and
-- signal_quality_scores completeness columns).
--
-- GOVERNANCE (steering/GOVERNANCE.md "Data Quality"): "When data_unavailable=TRUE, include
-- reason field explaining why (VARCHAR 255)" - this table violated that rule with zero
-- visible trace until this migration.

BEGIN;

ALTER TABLE aaii_sentiment ADD COLUMN IF NOT EXISTS reason VARCHAR(255);

COMMENT ON COLUMN aaii_sentiment.reason IS
    'Why data_unavailable=TRUE for this row (network/parse/unexpected error detail). Column was missing entirely before migration 1138 - loader computed this but bulk_insert_manager silently dropped it.';

COMMIT;
