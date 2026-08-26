-- Migration 1236: Add gross_profitability, operating_profitability, accruals_ratio, and
-- margin_volatility to quality_metrics.
--
-- These 4 factors (Novy-Marx 2013, Fama-French RMW 2015, Sloan 1996, QMJ 2013 Safety leg) were
-- added to quality_score's composite weighting in loaders/load_value_quality_growth_metrics.py
-- on 2026-08-26 (Quality pillar literature audit) but computed only as local variables inside
-- _compute_quality_metrics, never persisted - the composite score changed based on these
-- inputs while the inputs themselves stayed invisible everywhere else (API, frontend, this
-- table). Same "computed but invisible" bug class already fixed before for
-- vol_managed_multiplier/mom_12_1 (see phase7_signal_generation.py's _derive_mom_12_1
-- docstring) and payout_ratio itself, which already has this exact column+reason pattern.
--
-- Precision matches roic_pct/payout_ratio (NUMERIC(10,2)) - these are percentage-of-assets or
-- percentage-of-equity ratios of the same order of magnitude, not raw dollar amounts.

ALTER TABLE quality_metrics ADD COLUMN IF NOT EXISTS gross_profitability NUMERIC(10, 2);
ALTER TABLE quality_metrics ADD COLUMN IF NOT EXISTS gross_profitability_unavailable_reason VARCHAR(255);
ALTER TABLE quality_metrics ADD COLUMN IF NOT EXISTS operating_profitability NUMERIC(10, 2);
ALTER TABLE quality_metrics ADD COLUMN IF NOT EXISTS operating_profitability_unavailable_reason VARCHAR(255);
ALTER TABLE quality_metrics ADD COLUMN IF NOT EXISTS accruals_ratio NUMERIC(10, 2);
ALTER TABLE quality_metrics ADD COLUMN IF NOT EXISTS accruals_ratio_unavailable_reason VARCHAR(255);
ALTER TABLE quality_metrics ADD COLUMN IF NOT EXISTS margin_volatility NUMERIC(10, 2);
ALTER TABLE quality_metrics ADD COLUMN IF NOT EXISTS margin_volatility_unavailable_reason VARCHAR(255);

COMMENT ON COLUMN quality_metrics.gross_profitability IS
    '(Revenue - COGS) / Total Assets, pct. Novy-Marx 2013. Scored in quality_score composite.';
COMMENT ON COLUMN quality_metrics.operating_profitability IS
    '(Operating Income - Interest Expense) / Stockholders Equity, pct. Fama-French RMW (2015) proxy. Scored in quality_score composite.';
COMMENT ON COLUMN quality_metrics.accruals_ratio IS
    '(Net Income - Operating Cash Flow) / Total Assets, pct. Sloan 1996. Scored in quality_score composite (inverted: lower is better).';
COMMENT ON COLUMN quality_metrics.margin_volatility IS
    'Trailing-3-fiscal-year stdev of net_margin, pct points. QMJ (2013) Safety leg proxy. Scored in quality_score composite (inverted: lower is better).';
