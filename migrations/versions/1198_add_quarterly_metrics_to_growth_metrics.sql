-- Migration: Add quarterly metrics columns to growth_metrics table
-- Session 78: Load quarterly metrics (consecutive_positive_quarters, earnings_growth_4q_avg, eps_growth_stability)

BEGIN;

ALTER TABLE growth_metrics
ADD COLUMN consecutive_positive_quarters NUMERIC,
ADD COLUMN consecutive_positive_quarters_unavailable_reason VARCHAR(100),
ADD COLUMN earnings_growth_4q_avg NUMERIC,
ADD COLUMN earnings_growth_4q_avg_unavailable_reason VARCHAR(100),
ADD COLUMN eps_growth_stability NUMERIC,
ADD COLUMN eps_growth_stability_unavailable_reason VARCHAR(100);

COMMIT;
