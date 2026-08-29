-- Migration 1246: Add forward-looking growth/revision columns to growth_metrics.
--
-- GOAL: user directive (2026-08-28, same session as migration 1245) - migration 1245 added
-- forward_eps_growth_current_fy/forward_eps_growth_next_fy/forward_revenue_growth_next_fy/
-- eps_estimate_revision_90d_pct to analyst_earnings_estimates; this migration surfaces them on
-- growth_metrics too (same join pattern value_metrics.forward_pe already uses from that same
-- table - see load_value_quality_growth_metrics.py's _get_analyst_forward_eps), so the scores
-- API's growth_inputs field and the frontend Growth tab can show them.
--
-- NOT wired into growth_score (loaders/load_stock_scores.py's _score_growth) - no historical
-- depth exists yet to validate predictive power (analyst_earnings_estimates is a
-- snapshot-per-day table with no backfill capability, same constraint forward_eps already
-- has). Informational-only until enough real history accumulates to test, same treatment as
-- every other unscored Growth field.

ALTER TABLE growth_metrics ADD COLUMN IF NOT EXISTS forward_eps_growth_current_fy NUMERIC(10, 4);
ALTER TABLE growth_metrics ADD COLUMN IF NOT EXISTS forward_eps_growth_current_fy_unavailable_reason VARCHAR(255);
ALTER TABLE growth_metrics ADD COLUMN IF NOT EXISTS forward_eps_growth_next_fy NUMERIC(10, 4);
ALTER TABLE growth_metrics ADD COLUMN IF NOT EXISTS forward_eps_growth_next_fy_unavailable_reason VARCHAR(255);
ALTER TABLE growth_metrics ADD COLUMN IF NOT EXISTS forward_revenue_growth_next_fy NUMERIC(10, 4);
ALTER TABLE growth_metrics ADD COLUMN IF NOT EXISTS forward_revenue_growth_next_fy_unavailable_reason VARCHAR(255);
ALTER TABLE growth_metrics ADD COLUMN IF NOT EXISTS eps_estimate_revision_90d_pct NUMERIC(10, 4);
ALTER TABLE growth_metrics ADD COLUMN IF NOT EXISTS eps_estimate_revision_90d_pct_unavailable_reason VARCHAR(255);

COMMENT ON COLUMN growth_metrics.forward_eps_growth_current_fy IS
    'Consensus current-FY EPS growth estimate, joined from analyst_earnings_estimates. Informational only - not scored (no history to validate yet).';
COMMENT ON COLUMN growth_metrics.forward_eps_growth_next_fy IS
    'Consensus next-FY EPS growth estimate, joined from analyst_earnings_estimates. Informational only - not scored (no history to validate yet).';
COMMENT ON COLUMN growth_metrics.forward_revenue_growth_next_fy IS
    'Consensus next-FY revenue growth estimate, joined from analyst_earnings_estimates. Informational only - not scored (no history to validate yet).';
COMMENT ON COLUMN growth_metrics.eps_estimate_revision_90d_pct IS
    '90-day change in the consensus current-FY EPS estimate, joined from analyst_earnings_estimates. Informational only - not scored (no history to validate yet).';
