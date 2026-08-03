-- Migration 1183: Add cost_of_revenue to annual_income_statement
--
-- ISSUE: migration 1130 added cost_of_revenue to quarterly_income_statement, on the stated
-- assumption ("annual already had it, no downstream reader yet so no backfill urgency" -
-- see steering/DATA_LOADERS.md's 2026-07-20 capex fix entry) that annual_income_statement
-- already had the column. That assumption was never actually true on a database bootstrapped
-- without it: lambda/api/routes/scores.py's stock-scores query computes a gross-margin
-- LATERAL from `ais.revenue`/`ais.cost_of_revenue` against annual_income_statement (ais) -
-- confirmed live: 503s the whole GET /api/scores endpoint with
-- `UndefinedColumn: column ais.cost_of_revenue does not exist` on a database missing it.
-- utils/external/sec_statements.py's get_income_statement()/field_mapping already fetches
-- and maps CostOfRevenue-family concepts for both annual and quarterly (same field_mapping
-- dict, period-agnostic) - only the annual table's own DDL was missing the column.

ALTER TABLE annual_income_statement ADD COLUMN IF NOT EXISTS cost_of_revenue NUMERIC(20, 2);

COMMENT ON COLUMN annual_income_statement.cost_of_revenue IS
    'Real SEC XBRL CostOfRevenue-family concept - same field_mapping as quarterly_income_statement.cost_of_revenue (migration 1130). Used by lambda/api/routes/scores.py to compute gross margin.';
