-- Migration 1190: Rename capital_expenditures -> capex on annual/quarterly_cash_flow
--
-- ISSUE: same untracked-drift class as migrations 1181-1189. steering/DATA_LOADERS.md
-- documents a 2026-07-20 fix ("Found 2026-07-20: this mapped to 'capital_expenditures', a
-- column that has never existed in annual_cash_flow/quarterly_cash_flow (real column is
-- 'capex') - every write silently vanished... Renamed to match the real column") -
-- loaders/load_financial_statements.py's field_mapping already targets "capex" (matching
-- that documented decision) and loaders/load_sec_valuations.py reads `capex` directly. But
-- this local database still has the OLD "capital_expenditures" column name, never renamed -
-- confirmed live: `UndefinedColumn: column "capex" does not exist` crashes
-- load_sec_valuations.py for every symbol, and load_financial_statements.py's cash-flow
-- writes have been silently dropping capex data the whole time (non-marker column,
-- silently skipped rather than raised - see utils/bulk_insert_manager.py's governance-marker
-- distinction).

ALTER TABLE annual_cash_flow RENAME COLUMN capital_expenditures TO capex;
ALTER TABLE quarterly_cash_flow RENAME COLUMN capital_expenditures TO capex;
