-- Migration 1145: Add interest_expense to annual/quarterly income statements
-- Date: 2026-07-20
-- (Numbered 1145, not 1143/1144 - those were claimed concurrently by another session's
-- migration for an unrelated config fix; renumbered to avoid collision.)
--
-- ROOT CAUSE: quality_metrics.interest_coverage (and its companion
-- interest_coverage_unavailable_reason column) has existed since an earlier migration and
-- is already exposed by lambda/api/routes/scores.py (qm.interest_coverage AS
-- interest_coverage_val) and rendered by webapp/frontend's StockScoreAccordion.jsx, but no
-- loader has ever computed a value for it (confirmed 2026-07-20: 0/4772 rows filled) -
-- annual_income_statement/quarterly_income_statement never fetched InterestExpense from SEC
-- EDGAR in the first place, so load_value_quality_growth_metrics.py had no input to compute
-- Interest Coverage = Operating Income / Interest Expense from.
--
-- Fix: add interest_expense to both tables. utils/external/sec_statements.py now requests
-- the "InterestExpense" us-gaap concept; load_financial_statements.py maps it straight
-- through (interest_expense -> interest_expense); load_value_quality_growth_metrics.py
-- computes interest_coverage from it and folds it into quality_score.

BEGIN;

ALTER TABLE annual_income_statement ADD COLUMN IF NOT EXISTS interest_expense NUMERIC;
ALTER TABLE quarterly_income_statement ADD COLUMN IF NOT EXISTS interest_expense NUMERIC;

COMMENT ON COLUMN annual_income_statement.interest_expense IS
    'SEC us-gaap:InterestExpense for the fiscal year. Feeds quality_metrics.interest_coverage = operating_income / interest_expense. No IFRS alias (IFRS FinanceCosts is a broader concept) - foreign filers correctly get NULL rather than an overstated value.';
COMMENT ON COLUMN quarterly_income_statement.interest_expense IS
    'SEC us-gaap:InterestExpense for the fiscal quarter. See annual_income_statement.interest_expense for usage.';

COMMIT;
