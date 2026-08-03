-- Migration 1178: Add income_tax_expense/pretax_income to annual/quarterly income statement
--
-- ISSUE: quality_metrics.roic_pct has been permanently unavailable for 99.8% of symbols
-- (5605/5671 rows carry "missing_sec_data") because load_value_quality_growth_metrics.py's
-- ROIC calculation was never implemented - a hardcoded 25% effective tax rate assumption was
-- correctly rejected as synthetic data (real effective tax rates vary 5-35%+ by jurisdiction/
-- structure), but no fallback to the real reported tax figure was ever wired up either.
--
-- FIX: sec_statements.py's get_income_statement() now fetches the real GAAP concepts
-- IncomeTaxExpenseBenefit (the actual tax provision) and pretax income (taxonomy migrated
-- from IncomeLossFromContinuingOperationsBeforeIncomeTaxesMinorityInterestAndIncomeLossFrom
-- EquityMethodInvestments to ...ExtraordinaryItemsNoncontrollingInterest - both fetched,
-- live-confirmed present for AAPL/MSFT). load_value_quality_growth_metrics.py now computes
-- a real effective_tax_rate = income_tax_expense / pretax_income and applies it to EBIT for
-- NOPAT, instead of leaving the field permanently unavailable.

ALTER TABLE annual_income_statement ADD COLUMN IF NOT EXISTS income_tax_expense NUMERIC;
ALTER TABLE annual_income_statement ADD COLUMN IF NOT EXISTS pretax_income NUMERIC;
ALTER TABLE quarterly_income_statement ADD COLUMN IF NOT EXISTS income_tax_expense NUMERIC;
ALTER TABLE quarterly_income_statement ADD COLUMN IF NOT EXISTS pretax_income NUMERIC;

COMMENT ON COLUMN annual_income_statement.income_tax_expense IS
    'Real SEC XBRL IncomeTaxExpenseBenefit concept - the reported income tax provision for the fiscal year, used to derive a real effective tax rate for roic_pct (no synthetic assumption).';
COMMENT ON COLUMN annual_income_statement.pretax_income IS
    'Real SEC XBRL pretax income concept (IncomeLossFromContinuingOperationsBeforeIncomeTaxes* family) - denominator for the real effective tax rate used by roic_pct.';
COMMENT ON COLUMN quarterly_income_statement.income_tax_expense IS
    'Real SEC XBRL IncomeTaxExpenseBenefit concept - the reported income tax provision for the fiscal quarter.';
COMMENT ON COLUMN quarterly_income_statement.pretax_income IS
    'Real SEC XBRL pretax income concept (IncomeLossFromContinuingOperationsBeforeIncomeTaxes* family) for the fiscal quarter.';
