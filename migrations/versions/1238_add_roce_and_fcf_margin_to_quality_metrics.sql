-- Migration 1238: Add roce_pct and fcf_margin to quality_metrics.
--
-- Quality pillar exhaustive-input review (2026-08-26, user-directed): both newly wired into
-- quality_score's composite in loaders/load_value_quality_growth_metrics.py.
--
-- roce_pct (Return on Capital Employed = EBIT / (Equity + Debt), no cash netting) replaces
-- roic_pct in the composite - roic_pct's cash subtraction makes invested_capital go negative
-- for well-capitalized, profitable companies (~31% of all roic_pct missing_sec_data cases).
-- FM-validated: t=2.10 univariate/1.91 multivariate (151 months, 2014-2026), stable across a
-- half-split robustness check (t=1.50/1.50 exactly) - more reliable than roic_pct's own
-- t=0.45/sign-flipping (1.84/-0.79) half-split result. Panel coverage 70.8% vs roic_pct's 38.9%.
--
-- fcf_margin (free_cash_flow / revenue) replaces accruals_ratio in the composite - cash-
-- conversion efficiency net of capex, distinct from accruals_ratio (never nets out capex;
-- correlation between the two in the FM panel was only 0.13). FM-validated: t=2.03 univariate/
-- 1.93 multivariate, stable across a half-split check (t=1.32/1.53).
--
-- Precision matches roic_pct/payout_ratio (NUMERIC(10,2)) - both are percentage-of-capital or
-- percentage-of-revenue ratios of the same order of magnitude, not raw dollar amounts.

ALTER TABLE quality_metrics ADD COLUMN IF NOT EXISTS roce_pct NUMERIC(10, 2);
ALTER TABLE quality_metrics ADD COLUMN IF NOT EXISTS roce_pct_unavailable_reason VARCHAR(255);
ALTER TABLE quality_metrics ADD COLUMN IF NOT EXISTS fcf_margin NUMERIC(10, 2);
ALTER TABLE quality_metrics ADD COLUMN IF NOT EXISTS fcf_margin_unavailable_reason VARCHAR(255);

COMMENT ON COLUMN quality_metrics.roce_pct IS
    'Return on Capital Employed: EBIT / (Stockholders Equity + Debt), pct, no cash netting (unlike roic_pct). Scored in quality_score composite, 18% weight, replaces roic_pct.';
COMMENT ON COLUMN quality_metrics.fcf_margin IS
    'Free Cash Flow / Revenue, pct. Scored in quality_score composite, 15% weight, replaces accruals_ratio.';
