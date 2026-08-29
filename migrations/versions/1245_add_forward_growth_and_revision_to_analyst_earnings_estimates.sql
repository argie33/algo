-- Migration 1245: Add forward growth + estimate-revision columns to analyst_earnings_estimates.
--
-- GOAL: user directive (2026-08-28, same Growth-pillar-audit session as migration 1244) - we
-- were only capturing forward_eps (migration 1179) from yf.Ticker.earnings_estimate, but
-- yfinance's analyst-estimate API surface has more real data on it that this repo was never
-- pulling: earnings_estimate/revenue_estimate both ship a pre-computed `growth` column per
-- period, and eps_trend shows how the consensus estimate has moved over the trailing
-- 7/30/60/90 days - a genuine, distinct "estimate revision momentum" signal (Givoly &
-- Lakonishok 1979; a well-established input at institutional factor shops, distinct from
-- realized growth). Live-verified against AAPL (2026-08-28):
--   earnings_estimate: 0y growth=0.1813, +1y growth=0.0816 (current-FY / next-FY consensus
--     EPS growth, pre-computed by yfinance from the same DataFrame fetch_forward_eps already
--     uses - no new API call, just unused columns on a response already being fetched).
--   revenue_estimate: +1y growth=0.0991 (next-FY consensus revenue growth) - a NEW yfinance
--     endpoint (Ticker.revenue_estimate) this repo has never called before.
--   eps_trend: current=1.97656 vs 90daysAgo=2.00767 for AAPL's current quarter - a real
--     revision trend, NOT the same thing as growth (a stock can have positive forward growth
--     while analysts are simultaneously revising it DOWN, which is itself informative).
--
-- SCOPE NOTE: this is a snapshot-per-day table (same as migration 1179) - it has NO ability to
-- backfill historical point-in-time estimates (yfinance only exposes today's consensus), so
-- these new columns start accumulating real history from whenever this migration + the
-- updated loader first run, same constraint forward_eps already has. User directive: capture
-- the values now regardless of the backtesting gap ("forget the historical... as long as we
-- can get the values we need for now") - these are NOT wired into growth_score or any scored
-- pillar (no history exists yet to validate predictive power against), display/collection only
-- until enough real history accumulates to test.

ALTER TABLE analyst_earnings_estimates ADD COLUMN IF NOT EXISTS forward_eps_growth_current_fy NUMERIC(10, 4);
ALTER TABLE analyst_earnings_estimates ADD COLUMN IF NOT EXISTS forward_eps_growth_next_fy NUMERIC(10, 4);
ALTER TABLE analyst_earnings_estimates ADD COLUMN IF NOT EXISTS forward_revenue_growth_next_fy NUMERIC(10, 4);
ALTER TABLE analyst_earnings_estimates ADD COLUMN IF NOT EXISTS eps_estimate_revision_90d_pct NUMERIC(10, 4);

COMMENT ON COLUMN analyst_earnings_estimates.forward_eps_growth_current_fy IS
    'Consensus current-fiscal-year EPS growth estimate (yf.Ticker.earnings_estimate, period "0y", growth column) - forward-looking, not realized growth.';
COMMENT ON COLUMN analyst_earnings_estimates.forward_eps_growth_next_fy IS
    'Consensus next-fiscal-year EPS growth estimate (yf.Ticker.earnings_estimate, period "+1y", growth column) - forward-looking, not realized growth.';
COMMENT ON COLUMN analyst_earnings_estimates.forward_revenue_growth_next_fy IS
    'Consensus next-fiscal-year revenue growth estimate (yf.Ticker.revenue_estimate, period "+1y", growth column).';
COMMENT ON COLUMN analyst_earnings_estimates.eps_estimate_revision_90d_pct IS
    '% change in the consensus current-fiscal-year EPS estimate over the trailing 90 days (yf.Ticker.eps_trend, period "0y": (current - 90daysAgo) / |90daysAgo| * 100) - an estimate-revision-momentum signal, distinct from growth (analysts can be revising estimates down even while forward growth is positive).';
