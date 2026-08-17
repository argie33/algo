-- Migration 1203: Replace positioning_metrics.short_interest_trend (3-bucket text enum:
-- 'increasing'/'decreasing'/'stable', classified from a +/-5% relative-change threshold)
-- with short_interest_pct_change (the underlying continuous month-over-month % change
-- itself, e.g. -12.34 meaning short interest fell 12.34% vs the prior FINRA settlement).
--
-- WHY: the enum was scored in loaders/load_stock_scores.py::_score_positioning via a
-- 3-tier lookup (increasing=10, stable=55, decreasing=100) - every symbol whose relative
-- change was, say, +4.9% or +49% scored identically at 10, discarding real signal the
-- loader had already computed (loaders/load_positioning_metrics.py's
-- _compute_short_interest_pct_change, formerly _compute_short_interest_trend, always
-- computed the exact relative_change float before bucketing it down to a string). This
-- table is dedicated scoring input for stock_scores (see load_positioning_metrics.py's
-- module docstring), so the numeric value replaces the enum outright rather than
-- living alongside it.

ALTER TABLE positioning_metrics
    ADD COLUMN IF NOT EXISTS short_interest_pct_change NUMERIC(10, 4),
    ADD COLUMN IF NOT EXISTS short_interest_pct_change_unavailable_reason VARCHAR(255);

ALTER TABLE positioning_metrics
    DROP COLUMN IF EXISTS short_interest_trend,
    DROP COLUMN IF EXISTS short_interest_trend_unavailable_reason;
