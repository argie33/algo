-- Migration 1189: Add interest_expense to annual_income_statement
--
-- ISSUE: same untracked-drift class as migrations 1181-1187. quarterly_income_statement
-- already has interest_expense (used for interest_coverage) but annual_income_statement
-- never got the column - loaders/load_value_quality_growth_metrics.py's quality_row query
-- reads ais.interest_expense from annual_income_statement directly; on a database missing
-- it this raised UndefinedColumn, caught by that loader's broad `except Exception` and
-- silently marking value_metrics/quality_metrics/growth_metrics unavailable for every
-- symbol - masquerading as a missing-SEC-data gap rather than the real missing-column bug
-- it was. loaders/load_financial_statements.py's field_mapping already fetches and maps
-- InterestExpense/InterestExpenseNonoperating/InterestExpenseDebt concepts for annual too
-- (same field_mapping dict as quarterly) - only the annual table's own DDL was missing it.

ALTER TABLE annual_income_statement ADD COLUMN IF NOT EXISTS interest_expense NUMERIC(20, 2);

COMMENT ON COLUMN annual_income_statement.interest_expense IS
    'Real SEC XBRL InterestExpense-family concept - same field_mapping as quarterly_income_statement.interest_expense. Used for interest_coverage ratio.';
