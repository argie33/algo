-- Migration 1176: Add ev_revenue_unavailable_reason column to value_metrics table
-- Tracks when enterprise value to revenue ratio (EV/Revenue) cannot be calculated
-- Populated by load_value_quality_growth_metrics.py

BEGIN;

ALTER TABLE value_metrics
ADD COLUMN IF NOT EXISTS ev_revenue_unavailable_reason VARCHAR(255);

COMMENT ON COLUMN value_metrics.ev_revenue_unavailable_reason IS
    'Reason why ev_revenue metric is unavailable. Examples: "missing_sec_data", "insufficient_data". Populated by load_value_quality_growth_metrics.py. Null when ev_revenue value is available.';

COMMIT;
