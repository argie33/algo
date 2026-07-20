-- Migration 1130: Add cost_of_revenue to quarterly_income_statement.
--
-- ROOT CAUSE: loaders/load_financial_statements.py's quarterly income-statement schema_cols
-- (get_income_statement_config, period="quarterly") has always listed "cost_of_revenue" as a
-- valid target column and mapped SEC's CostOfRevenue/CostsAndExpenses concepts to it, but
-- quarterly_income_statement never actually had that column (only annual_income_statement
-- does) - every quarterly write for this field was silently dropped at the schema-validation
-- step in loaders/helpers/sec_base.py::transform(). Confirmed live 2026-07-20: 0 of ~82K
-- quarterly_income_statement rows have cost_of_revenue populated. No downstream code reads
-- this column yet, so this is a data-completeness fix, not an active-consumer bugfix - but it
-- brings quarterly in line with the annual table's real structure.

ALTER TABLE quarterly_income_statement ADD COLUMN IF NOT EXISTS cost_of_revenue NUMERIC(20, 2);
