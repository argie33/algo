-- Migration 1299: Add MSCI-formula growth-trend fields to growth_metrics.
--
-- 2026-09-16 factor-purity /goal session: this repo's existing revenue_growth_1y/3y/5y and
-- eps_growth_1y/3y/5y are all two-point CAGRs (latest fiscal year vs N years back). None of
-- them compute what MSCI's real Global Investable Market Value and Growth Index Methodology
-- (Feb 2021) actually means by "Long-term Historical EPS/SPS Growth Trend": an OLS regression
-- of the last 5 years' EPS/sales-per-share against time, annualized, divided by the mean
-- absolute level over that window - see loaders/helpers/growth_trend.py's own docstring for
-- the exact formula and the worked-example proof it's implemented faithfully.
--
-- eps_growth_trend_5y / sps_growth_trend_5y are the real thing, computed alongside the
-- existing (still-computed, still-useful-for-other-purposes) CAGR fields, not a replacement
-- for them at the raw-data layer - only growth_scoring.py's GROWTH_SCORE_FIELDS (a separate,
-- follow-up change) decides which fields actually feed growth_score.

ALTER TABLE growth_metrics ADD COLUMN IF NOT EXISTS eps_growth_trend_5y NUMERIC(10, 4);
ALTER TABLE growth_metrics ADD COLUMN IF NOT EXISTS eps_growth_trend_5y_unavailable_reason VARCHAR(255);
ALTER TABLE growth_metrics ADD COLUMN IF NOT EXISTS sps_growth_trend_5y NUMERIC(10, 4);
ALTER TABLE growth_metrics ADD COLUMN IF NOT EXISTS sps_growth_trend_5y_unavailable_reason VARCHAR(255);

COMMENT ON COLUMN growth_metrics.eps_growth_trend_5y IS
    'MSCI LT his EPS G: OLS regression slope of the last 5 fiscal years'' EPS against time (months), annualized, divided by mean absolute EPS over that window. See loaders/helpers/growth_trend.py.';
COMMENT ON COLUMN growth_metrics.sps_growth_trend_5y IS
    'MSCI LT his SPS G: same OLS-trend formula applied to revenue-per-share (sales per share) instead of EPS. See loaders/helpers/growth_trend.py.';
