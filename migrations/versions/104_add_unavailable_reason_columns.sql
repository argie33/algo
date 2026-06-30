-- Migration 104: Add missing _unavailable_reason and reason columns to metrics tables
-- quality_metrics loader returns "reason" field for data_unavailable records
-- stability_metrics loader returns "reason" field for data_unavailable records
-- value_metrics loader returns per-field unavailable_reason fields
-- These columns were missing from DB schema, causing "skipping columns not in DB schema" warnings.

-- quality_metrics: add reason column for data_unavailable context
ALTER TABLE quality_metrics
ADD COLUMN IF NOT EXISTS reason VARCHAR(500);

-- stability_metrics: add reason column for data_unavailable context
ALTER TABLE stability_metrics
ADD COLUMN IF NOT EXISTS reason VARCHAR(500);

-- value_metrics: add per-field unavailable_reason columns
ALTER TABLE value_metrics
ADD COLUMN IF NOT EXISTS market_cap_unavailable_reason VARCHAR(255);

ALTER TABLE value_metrics
ADD COLUMN IF NOT EXISTS pe_ratio_unavailable_reason VARCHAR(255);

ALTER TABLE value_metrics
ADD COLUMN IF NOT EXISTS pb_ratio_unavailable_reason VARCHAR(255);

ALTER TABLE value_metrics
ADD COLUMN IF NOT EXISTS ps_ratio_unavailable_reason VARCHAR(255);

ALTER TABLE value_metrics
ADD COLUMN IF NOT EXISTS peg_ratio_unavailable_reason VARCHAR(255);

ALTER TABLE value_metrics
ADD COLUMN IF NOT EXISTS dividend_yield_unavailable_reason VARCHAR(255);

ALTER TABLE value_metrics
ADD COLUMN IF NOT EXISTS fcf_yield_unavailable_reason VARCHAR(255);

ALTER TABLE value_metrics
ADD COLUMN IF NOT EXISTS held_percent_insiders_unavailable_reason VARCHAR(255);

ALTER TABLE value_metrics
ADD COLUMN IF NOT EXISTS held_percent_institutions_unavailable_reason VARCHAR(255);

-- Analyze tables to update planner statistics
ANALYZE quality_metrics;
ANALYZE stability_metrics;
ANALYZE value_metrics;
