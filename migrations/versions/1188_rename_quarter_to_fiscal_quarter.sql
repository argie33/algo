-- Migration 1188: Rename quarter -> fiscal_quarter on the 3 quarterly statement tables
--
-- ISSUE: real, active bug (not just local-dev drift) - loaders/load_financial_statements.py's
-- quarterly configs consistently use "fiscal_quarter" throughout (primary_key=("symbol",
-- "fiscal_year", "fiscal_quarter"), _QUARTERLY_EXTRA maps SEC's fiscal_period concept to
-- "fiscal_quarter", schema_cols lists "fiscal_quarter") and utils/bulk_insert_manager.py's
-- _ensure_unique_constraint() tries to create a UNIQUE constraint on (symbol, fiscal_year,
-- fiscal_quarter) - but all 3 quarterly tables actually have a column named "quarter", not
-- "fiscal_quarter". Confirmed live: this crashes the constraint-creation step with
-- `UndefinedColumn: column "fiscal_quarter" named in key does not exist`, which poisons the
-- shared "all mode" transaction (all 6 statement/period combos share one SEC companyfacts
-- fetch + connection) and silently blocks the REMAINING combos in the same batch from
-- writing anything at all, including annual_balance_sheet/annual_cash_flow which have no
-- fiscal_quarter concept whatsoever - a working annual load was being taken down by an
-- unrelated quarterly config bug purely by transaction-sharing proximity.
--
-- FIX: rename the column to match what every other part of the codebase already expects,
-- rather than changing the loader (which would require touching primary_key tuples,
-- _QUARTERLY_EXTRA, and 3 schema_cols frozensets all in sync - renaming the column is the
-- single, lower-risk change).

ALTER TABLE quarterly_income_statement RENAME COLUMN quarter TO fiscal_quarter;
ALTER TABLE quarterly_balance_sheet RENAME COLUMN quarter TO fiscal_quarter;
ALTER TABLE quarterly_cash_flow RENAME COLUMN quarter TO fiscal_quarter;
