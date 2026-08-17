-- Migration 1207: Add source_tracking to positioning_metrics
--
-- Continuation of the loader-review goal's SEC-vs-yfinance data audit (2026-08-17).
--
-- load_positioning_metrics.py has always computed a per-field source_tracking dict
-- (which of short_interest/institutional/insider came from FINRA Reg SHO / SEC 13F /
-- SEC Form 4, vs "unavailable") on every single row, but positioning_metrics never had
-- a matching column - the dict was silently dropped on 100% of writes by
-- bulk_insert_manager's schema-filter (logged as a routine WARNING, not raised, since
-- "source_tracking" doesn't match the governance-marker name patterns that escalate to
-- a hard failure), producing log spam with zero persisted value. The existing
-- `data_source`/`reason` columns only capture the single primary source (data_source) or
-- all three sources but ONLY when the row is fully unavailable (reason) - source_tracking
-- is the only place per-field provenance for a row with real data would be visible,
-- which is exactly the kind of SEC-vs-yfinance sourcing audit trail this goal is about.

ALTER TABLE positioning_metrics ADD COLUMN IF NOT EXISTS source_tracking JSONB;

COMMENT ON COLUMN positioning_metrics.source_tracking IS
    'Per-field data provenance: {"short_interest": ..., "institutional": ..., "insider": ...}, each one of "finra"/"sec_13f"/"sec_form4"/"unavailable". Always populated regardless of whether the row overall is available, unlike `reason` (which is only set when ALL fields are unavailable) or `data_source` (which only names the single primary source).';
