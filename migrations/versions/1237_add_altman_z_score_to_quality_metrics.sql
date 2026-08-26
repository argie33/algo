-- Migration 1237: Add altman_z_score to quality_metrics.
--
-- Altman Z''-Score (book-equity variant, Altman 1995) newly wired into quality_score's
-- composite as a real weighted component (2026-08-26, Quality pillar literature audit).
-- retained_earnings (migration 1234) had 0% DB coverage until a same-day backfill; a
-- Fama-MacBeth re-check on the full backfilled sample found t=3.49 (41 usable months,
-- 2023-03 to 2026-07, median cross-section 3006) - the single strongest-evidenced component
-- in the whole composite. See loaders/load_value_quality_growth_metrics.py's
-- _compute_quality_metrics for the formula and weighted_score's reweight comment for the
-- funding (interest_coverage 10%->5%, accruals_ratio 15%->10%, this new field 10%).

ALTER TABLE quality_metrics ADD COLUMN IF NOT EXISTS altman_z_score NUMERIC(10, 2);
ALTER TABLE quality_metrics ADD COLUMN IF NOT EXISTS altman_z_score_unavailable_reason VARCHAR(255);

COMMENT ON COLUMN quality_metrics.altman_z_score IS
    'Altman Z''-Score (1995 book-equity variant): 6.56*(WorkingCapital/Assets) + 3.26*(RetainedEarnings/Assets) + 6.72*(EBIT/Assets) + 1.05*(BookEquity/TotalLiabilities). Scored in quality_score composite, 10% weight.';
