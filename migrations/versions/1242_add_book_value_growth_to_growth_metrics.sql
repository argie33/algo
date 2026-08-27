-- Migration 1242: Add book_value_growth to growth_metrics.
--
-- Growth pillar recovery (2026-08-27) - a real data-hole audit found the joint-dropna sample-
-- bias bug (already fixed for Quality's margin_volatility_3y/gross_profitability) had also
-- corrupted this repo's own conclusions about several Growth candidates. book_value_growth
-- (year-over-year change in book value per share = stockholders_equity / shares_outstanding)
-- was never previously tested by this pillar's candidate lists at all. Isolated FM-validated:
-- t=-5.82 full sample (151mo)/-2.05 first half (<2020-06)/-5.93 second half (>=2020-06)
-- univariate - the strongest, most time-consistent result found anywhere in this repo's
-- Growth research. A joint multivariate test against the pillar's 3 other surviving
-- candidates (eps_growth_1y, revenue_growth_1y, asset_growth_yoy_flipped) found
-- book_value_growth is the ONLY one that stays significant and sign-consistent in all three
-- windows - it statistically dominates/subsumes the other three, which collapse to
-- insignificance or sign-flip once it's included. See MEMORY.md for the full evidence trail.
--
-- Scored inverted (lower book-value growth = higher score) - same "less balance-sheet
-- expansion is better" story as the existing asset_growth_yoy_flipped treatment
-- (Cooper/Gulen/Schill 2008 JoF asset-growth anomaly / Fama-French CMA factor), now the
-- dominant Growth pillar component.

ALTER TABLE growth_metrics ADD COLUMN IF NOT EXISTS book_value_growth NUMERIC(10, 2);
ALTER TABLE growth_metrics ADD COLUMN IF NOT EXISTS book_value_growth_unavailable_reason VARCHAR(255);

COMMENT ON COLUMN growth_metrics.book_value_growth IS
    'YoY % change in book value per share (stockholders_equity / shares_outstanding). Dominant Growth pillar component (isolated t=-5.82/-2.05/-5.93 full/1st-half/2nd-half) - scored inverted, lower is better.';
