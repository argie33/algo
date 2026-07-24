-- Migration 1149: Add depreciation_expense and amortization_expense for EBITDA calculation
-- Date: 2026-07-24 (Session 398)
--
-- ROOT CAUSE: value_metrics.ev_ebitda (and associated ev_ebitda column) is 0% populated across 5,481 stocks
-- because EBITDA cannot be calculated without depreciation and amortization data from SEC filings.
--
-- Current state:
-- - EBITDA calculation exists in load_sec_valuations.py (lines 382-388) but ebitda is always NULL
-- - load_financial_statements.py was fetching DepreciationExpense from SEC but silently discarding it
--   (no field_mapping entry existed, so transform() would skip the column)
-- - annual_income_statement/quarterly_income_statement tables never had columns to store D/A data
--
-- Fix (Session 398):
-- 1. Add depreciation_expense and amortization_expense columns to both annual/quarterly income statements
-- 2. Update load_financial_statements.py field_mapping to persist D/A from SEC
-- 3. Update sec_statements.py to fetch D/A concepts (Depreciation, DepreciationAndAmortization, AmortizationOfIntangibles)
-- 4. Update load_sec_valuations.py to calculate: EBITDA = OperatingIncome + Depreciation + Amortization
-- 5. This enables value_metrics.ev_ebitda calculation for ~90%+ of stocks with SEC filings

BEGIN;

-- Add depreciation_expense to annual income statement
ALTER TABLE annual_income_statement ADD COLUMN IF NOT EXISTS depreciation_expense NUMERIC(18, 2);
COMMENT ON COLUMN annual_income_statement.depreciation_expense IS
    'SEC us-gaap:DepreciationExpense or ifrs-full:DepreciationAndAmortisation for the fiscal year. Used in EBITDA calculation = operating_income + depreciation_expense + amortization_expense. Populated via load_financial_statements.py (Session 398).';

-- Add amortization_expense to annual income statement
ALTER TABLE annual_income_statement ADD COLUMN IF NOT EXISTS amortization_expense NUMERIC(18, 2);
COMMENT ON COLUMN annual_income_statement.amortization_expense IS
    'SEC us-gaap:AmortizationOfIntangibles or alternative D&A concepts for the fiscal year. Used in EBITDA calculation. When both depreciation_expense and amortization_expense are NULL, ebitda calculation uses only operating_income. Populated via load_financial_statements.py (Session 398).';

-- Add depreciation_expense to quarterly income statement
ALTER TABLE quarterly_income_statement ADD COLUMN IF NOT EXISTS depreciation_expense NUMERIC(18, 2);
COMMENT ON COLUMN quarterly_income_statement.depreciation_expense IS
    'SEC depreciation for the fiscal quarter. See annual_income_statement.depreciation_expense for usage.';

-- Add amortization_expense to quarterly income statement
ALTER TABLE quarterly_income_statement ADD COLUMN IF NOT EXISTS amortization_expense NUMERIC(18, 2);
COMMENT ON COLUMN quarterly_income_statement.amortization_expense IS
    'SEC amortization for the fiscal quarter. See annual_income_statement.amortization_expense for usage.';

COMMIT;
