-- Migration 1241: Add asset_turnover to quality_metrics.
--
-- Quality pillar missing-metrics sweep follow-up (2026-08-27) - newly wired into
-- quality_score's composite in loaders/load_value_quality_growth_metrics.py, 7 of 113
-- nominal weight (~6%).
--
-- asset_turnover (Revenue / Total Assets, x100) is the classic DuPont efficiency component -
-- never previously tested by this pillar's own candidate lists
-- (algo/research/fama_macbeth_quality_factors.py). FM-validated: t=3.03 full sample
-- (151 months, 2014-2026)/3.00 first half (<2020-06)/1.54 second half (>=2020-06) - positive,
-- moderate, more time-consistent than net_margin (which decayed to near-zero). See MEMORY.md
-- quality_asset_turnover_piotroski_tested_20260827 for the full evidence trail.
--
-- Precision matches gross_profitability/roce_pct (NUMERIC(10,2)) - same "ratio x100" storage
-- convention as that field, not a raw dollar amount.

ALTER TABLE quality_metrics ADD COLUMN IF NOT EXISTS asset_turnover NUMERIC(10, 2);
ALTER TABLE quality_metrics ADD COLUMN IF NOT EXISTS asset_turnover_unavailable_reason VARCHAR(255);

COMMENT ON COLUMN quality_metrics.asset_turnover IS
    'Revenue / Total Assets, x100 (DuPont efficiency component). Scored in quality_score composite, 7 of 113 nominal weight (~6%).';
