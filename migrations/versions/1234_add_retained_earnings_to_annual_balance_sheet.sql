-- Migration 1234: Add retained_earnings to annual_balance_sheet
--
-- Quality pillar literature audit (2026-08-26): Altman Z''-Score needs Retained Earnings/
-- Total Assets, the one of its four terms not derivable from concepts already fetched
-- (Working Capital, EBIT, and Market Equity/Liabilities all already computable from existing
-- columns). RetainedEarningsAccumulatedDeficit is now fetched in
-- utils/external/sec_statements.py's get_balance_sheet() and mapped in
-- loaders/load_financial_statements.py's _BALANCE_FIELD_MAPPING - only this table's own DDL
-- was missing the column, same drift class as migration 1189 (interest_expense).

ALTER TABLE annual_balance_sheet ADD COLUMN IF NOT EXISTS retained_earnings NUMERIC(20, 2);

COMMENT ON COLUMN annual_balance_sheet.retained_earnings IS
    'Real SEC XBRL RetainedEarningsAccumulatedDeficit concept. Used for Altman Z''-Score (Quality pillar) Retained Earnings/Total Assets term.';
