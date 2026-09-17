-- Migration 1301: Add MSCI's real "Earnings Variability" fundamental variable to quality_metrics.
--
-- 2026-09-16 factor-purity /goal session (user: "we do what the industry does only"). MSCI's
-- real, published Quality Indexes Methodology (May 2022, msci.com/eqb/methodology/meth_docs/
-- MSCI_Quality_Indexes_Methodology_May2022.pdf, Section 2.2 + Appendix I) defines the Quality
-- Score as a composite Z-Score of exactly THREE fundamental variables: Return on Equity,
-- Debt to Equity, and Earnings Variability ("the standard deviation of y-o-y earnings per
-- share growth over the last five fiscal years"). ROE and Debt to Equity already exist in this
-- table (quality_metrics.roe/debt_to_equity) - Earnings Variability did not, until now. See
-- loaders/helpers/quality_variability.py for the exact formula (verified, not guessed) and
-- loaders/helpers/vqg_quality_score.py's quality_components docstring for how this replaces
-- the prior 6-component AQR/MSCI blend (roe/roa/fcf_margin/debt_to_equity/margin_volatility/
-- gross_profitability) as the real, scored construction.

ALTER TABLE quality_metrics ADD COLUMN IF NOT EXISTS earnings_variability NUMERIC(10, 4);
ALTER TABLE quality_metrics ADD COLUMN IF NOT EXISTS earnings_variability_unavailable_reason VARCHAR(255);

COMMENT ON COLUMN quality_metrics.earnings_variability IS
    'MSCI Quality Index''s 3rd fundamental variable: standard deviation (percentage points) of year-over-year diluted EPS growth over the last 5 fiscal years. See loaders/helpers/quality_variability.py.';
