-- Migration 1187: Add data_unavailable/reason governance markers to annual_income_statement
--
-- ISSUE: same untracked-drift class as migrations 1181-1186. annual_balance_sheet/
-- annual_cash_flow/quarterly_income_statement/quarterly_balance_sheet/quarterly_cash_flow
-- all have data_unavailable/reason columns (the standard "always upsert an explicit
-- unavailable marker rather than silently dropping a row" governance pattern used
-- throughout this codebase's loaders) - annual_income_statement was the one table missing
-- both. loaders/helpers/sec_base.py has an explicit fail-fast check for exactly this case
-- ("GOVERNANCE VIOLATION: ... governance marker columns do not exist on the target table")
-- rather than silently dropping the audit trail - confirmed live: a local dev database
-- missing these columns fails 10/10 symbols on annual_income_statement with that exact
-- error, blocking the entire load (annual/quarterly balance sheet and cash flow all load
-- fine since they already have both columns).

ALTER TABLE annual_income_statement
    ADD COLUMN IF NOT EXISTS data_unavailable BOOLEAN DEFAULT FALSE,
    ADD COLUMN IF NOT EXISTS reason VARCHAR(500);
