-- Migration 1137: Add missing data_completeness/unavailable_components columns to
-- signal_quality_scores (same silent-drop bug class as migrations 1135/1136)
-- Date: 2026-07-20
--
-- ROOT CAUSE: loaders/load_signal_quality_scores.py computes data_completeness (% of the 7
-- scoring components available, lines 792-795) and unavailable_components (which component
-- keys were None, line 792) for every row, and includes both in the dict it hands to
-- BulkInsertManager (lines 834-835) - but signal_quality_scores never had either column.
-- utils/bulk_insert_manager.py silently filters any key not present in the target table's
-- schema (logging only a WARNING, easy to miss), so this completeness/audit signal has been
-- computed and discarded on every single write since the loader was built - a governance
-- violation, same mechanism as the price_daily data_source (migration 1135) and quarterly
-- financial-statement (migration 1136) bugs fixed earlier this session.
--
-- unavailable_components is TEXT, not a Postgres array/jsonb: the loader passes a plain
-- Python list (e.g. ["vcp_pattern", "institutional_ownership"]), and BulkInsertManager's
-- COPY-CSV write path stringifies non-string values via Python's default str() (producing
-- "['vcp_pattern', 'institutional_ownership']", not valid array/JSON literal syntax) before
-- ever reaching this migration's column type - TEXT accepts that as-is with no further code
-- changes required; a typed array/jsonb column would need loader-side serialization changes,
-- which is out of scope for a schema-only fix.

BEGIN;

ALTER TABLE signal_quality_scores ADD COLUMN IF NOT EXISTS data_completeness NUMERIC(5, 2);
ALTER TABLE signal_quality_scores ADD COLUMN IF NOT EXISTS unavailable_components TEXT;

COMMENT ON COLUMN signal_quality_scores.data_completeness IS
    'Percent of the 7 scoring components that were available for this row (see load_signal_quality_scores.py). Column was missing entirely before migration 1137 - loader computed this but bulk_insert_manager silently dropped it.';
COMMENT ON COLUMN signal_quality_scores.unavailable_components IS
    'Stringified list of component names that were None for this row. Column was missing entirely before migration 1137 - loader computed this but bulk_insert_manager silently dropped it.';

COMMIT;
