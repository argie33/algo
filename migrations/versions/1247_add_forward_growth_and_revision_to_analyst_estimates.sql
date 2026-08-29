-- Migration 1247: Add forward growth + estimate-revision fields to analyst_earnings_estimates
-- and growth_metrics.
--
-- These 8 columns (4 value + 4 reason, per table) were previously added directly against the
-- shared local DB from a separate in-flight worktree session without a corresponding migration
-- file ever landing on main - this migration exists to bring main's migration history in line
-- with what's already live, using IF NOT EXISTS so it is a no-op there and only actually creates
-- the columns on a fresh database build.
--
-- forward_eps_growth_current_fy / forward_eps_growth_next_fy: yfinance Ticker.earnings_estimate's
-- own pre-computed 'growth' column (periods '0y'/'+1y') - consensus EPS growth vs the prior
-- fiscal year, genuinely forward-looking (distinct from growth_metrics' existing realized-growth
-- fields).
-- forward_revenue_growth_next_fy: yfinance Ticker.revenue_estimate's 'growth' column (period
-- '+1y').
-- eps_estimate_revision_90d_pct: how much the consensus current-FY EPS estimate has moved over
-- the trailing 90 days (Ticker.eps_trend, 'current' vs '90daysAgo').
--
-- Informational only on growth_metrics - these do NOT feed growth_score (no historical depth
-- yet to validate predictive power; analyst_earnings_estimates is a snapshot-per-day table with
-- no backfill capability).

ALTER TABLE analyst_earnings_estimates ADD COLUMN IF NOT EXISTS forward_eps_growth_current_fy NUMERIC(10, 4);
ALTER TABLE analyst_earnings_estimates ADD COLUMN IF NOT EXISTS forward_eps_growth_next_fy NUMERIC(10, 4);
ALTER TABLE analyst_earnings_estimates ADD COLUMN IF NOT EXISTS forward_revenue_growth_next_fy NUMERIC(10, 4);
ALTER TABLE analyst_earnings_estimates ADD COLUMN IF NOT EXISTS eps_estimate_revision_90d_pct NUMERIC(10, 4);

ALTER TABLE growth_metrics ADD COLUMN IF NOT EXISTS forward_eps_growth_current_fy NUMERIC(10, 4);
ALTER TABLE growth_metrics ADD COLUMN IF NOT EXISTS forward_eps_growth_current_fy_unavailable_reason VARCHAR(255);
ALTER TABLE growth_metrics ADD COLUMN IF NOT EXISTS forward_eps_growth_next_fy NUMERIC(10, 4);
ALTER TABLE growth_metrics ADD COLUMN IF NOT EXISTS forward_eps_growth_next_fy_unavailable_reason VARCHAR(255);
ALTER TABLE growth_metrics ADD COLUMN IF NOT EXISTS forward_revenue_growth_next_fy NUMERIC(10, 4);
ALTER TABLE growth_metrics ADD COLUMN IF NOT EXISTS forward_revenue_growth_next_fy_unavailable_reason VARCHAR(255);
ALTER TABLE growth_metrics ADD COLUMN IF NOT EXISTS eps_estimate_revision_90d_pct NUMERIC(10, 4);
ALTER TABLE growth_metrics ADD COLUMN IF NOT EXISTS eps_estimate_revision_90d_pct_unavailable_reason VARCHAR(255);

COMMENT ON COLUMN analyst_earnings_estimates.forward_eps_growth_current_fy IS
    'Consensus current-FY EPS growth estimate (yfinance earnings_estimate, period 0y, growth column).';
COMMENT ON COLUMN analyst_earnings_estimates.forward_eps_growth_next_fy IS
    'Consensus next-FY EPS growth estimate (yfinance earnings_estimate, period +1y, growth column).';
COMMENT ON COLUMN analyst_earnings_estimates.forward_revenue_growth_next_fy IS
    'Consensus next-FY revenue growth estimate (yfinance revenue_estimate, period +1y, growth column).';
COMMENT ON COLUMN analyst_earnings_estimates.eps_estimate_revision_90d_pct IS
    'Percent change in consensus current-FY EPS estimate over the trailing 90 days (yfinance eps_trend, 0y period, current vs 90daysAgo).';

COMMENT ON COLUMN growth_metrics.forward_eps_growth_current_fy IS
    'Copied from analyst_earnings_estimates - informational only, does not feed growth_score.';
COMMENT ON COLUMN growth_metrics.forward_eps_growth_next_fy IS
    'Copied from analyst_earnings_estimates - informational only, does not feed growth_score.';
COMMENT ON COLUMN growth_metrics.forward_revenue_growth_next_fy IS
    'Copied from analyst_earnings_estimates - informational only, does not feed growth_score.';
COMMENT ON COLUMN growth_metrics.eps_estimate_revision_90d_pct IS
    'Copied from analyst_earnings_estimates - informational only, does not feed growth_score.';
