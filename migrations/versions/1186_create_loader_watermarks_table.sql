-- Migration 1186: Create loader_watermarks table
--
-- ISSUE: same untracked-drift class as migrations 1181-1185. utils/data/watermark.py's
-- WatermarkManager (get/advance/set, symbol/global/custom granularity) reads and writes
-- loader_watermarks - used by loaders/load_value_quality_growth_metrics.py's per-symbol
-- watermark tracking (a separate, newer mechanism from OptimalLoader's own simpler
-- MAX(watermark_field) self-referential approach used by most other loaders) - but no
-- migration anywhere ever created the table. Confirmed live: a local dev database missing
-- it crashes the whole loader run at the final watermark-advance step with
-- `UndefinedTable: relation "loader_watermarks" does not exist`, even though the loader's
-- actual metric-table writes (value_metrics/quality_metrics/growth_metrics) already
-- committed successfully - the runner then misreports 100% failure since the crash happens
-- before the run can report success, discarding a run that actually worked.
--
-- watermark stored as TEXT (not DATE) since granularity='symbol' watermarks are sometimes
-- an integer fiscal_year, not always a calendar date (same reasoning as
-- utils/optimal_loader.py's _to_date() int-vs-date handling for OptimalLoader's own
-- watermark column).
--
-- symbol is nullable (granularity='global' rows have symbol IS NULL, per
-- utils/data/watermark.py's own read/write queries) - a plain UNIQUE/PRIMARY KEY constraint
-- would NOT treat two NULL symbols as conflicting (Postgres default), so every 'global'
-- advance_watermark call would INSERT a new row instead of the intended UPSERT via
-- `ON CONFLICT (loader, symbol, granularity)`. NULLS NOT DISTINCT (PG15+) fixes this by
-- making NULL compare equal to NULL for this constraint's purposes.

CREATE TABLE IF NOT EXISTS loader_watermarks (
    loader VARCHAR(100) NOT NULL,
    symbol VARCHAR(20),
    granularity VARCHAR(20) NOT NULL DEFAULT 'symbol',
    watermark TEXT,
    rows_loaded INTEGER NOT NULL DEFAULT 0,
    last_run_at TIMESTAMP WITH TIME ZONE,
    last_success_at TIMESTAMP WITH TIME ZONE,
    error_count INTEGER NOT NULL DEFAULT 0,
    last_error TEXT,
    UNIQUE NULLS NOT DISTINCT (loader, symbol, granularity)
);

CREATE INDEX IF NOT EXISTS idx_loader_watermarks_loader ON loader_watermarks(loader);

COMMENT ON TABLE loader_watermarks IS
    'Per-symbol/global/custom-granularity watermark tracking for utils/data/watermark.py::WatermarkManager - a separate, newer watermark mechanism from OptimalLoader''s own MAX(watermark_field) self-referential approach used by most loaders.';
