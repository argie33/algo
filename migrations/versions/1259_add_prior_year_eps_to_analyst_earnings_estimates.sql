-- Migration 1259: Add prior-year EPS columns to analyst_earnings_estimates.
-- Date: 2026-09-05

-- ROOT CAUSE (goal session: "missing SEC/XBRL data"/implausible-values sweep,
-- forward_eps_growth_current_fy investigation): forward_eps_growth_current_fy/next_fy store
-- ONLY yfinance's already-computed 'growth' ratio (Ticker.earnings_estimate's '0y'/'+1y' rows),
-- never the underlying yearAgoEps/avg-estimate pair that ratio was computed from. Live-confirmed
-- via PII's real yfinance data: 0y row has yearAgoEps=-0.01 (near-zero), avg=3.13694, so
-- growth=(3.13694-(-0.01))/abs(-0.01)=314.694 (31,469% as a fraction) - a mathematically correct
-- but practically meaningless ratio caused entirely by a near-zero prior-year base, the exact
-- same numerical-instability class growth_metrics' own realized-growth fields already give an
-- honest "immaterial_prior_year_base" reason (Legitimate / not applicable) instead of lumping
-- into implausible-value rejection. Without the raw yearAgoEps preserved, load_value_quality_
-- growth_metrics.py's _get_analyst_forward_growth_estimates() has no way to distinguish this
-- case from a genuinely enormous, real growth ratio after the fact - every case gets the
-- generic "garbage_metric_value_implausible_ratio" label instead, incorrectly counting a
-- near-zero-base numerical artifact as a data-quality "Implausible value" gap.

ALTER TABLE analyst_earnings_estimates ADD COLUMN IF NOT EXISTS forward_eps_growth_current_fy_prior_year_eps NUMERIC(10, 4);
ALTER TABLE analyst_earnings_estimates ADD COLUMN IF NOT EXISTS forward_eps_growth_next_fy_prior_year_eps NUMERIC(10, 4);
