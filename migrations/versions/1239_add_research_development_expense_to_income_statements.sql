-- Migration 1239: Add research_development_expense to annual/quarterly income statements
--
-- Closes the gap documented (incorrectly, as "permanently blocked") in
-- growth_missing_metrics_swept_20260827: R&D intensity and Mohanram G-Score were marked
-- unbuildable on the premise that no research_development column exists anywhere in this
-- pipeline. Live-verified via real SEC EDGAR companyfacts JSON (AAPL/MSFT/NVDA, 51 annual
-- entries each, values matching known public R&D figures) that us-gaap:ResearchAndDevelopmentExpense
-- is a real, populated, standard concept - just never extracted. Wired into
-- utils/external/sec_statements.py's get_income_statement() concepts list and
-- loaders/load_financial_statements.py's _INCOME_FIELD_MAPPING/schema_cols, same pattern as
-- every other concept addition in this file (e.g. CostOfGoodsAndServicesSold, InterestExpenseDebt).
--
-- Naturally sparse/NULL for non-R&D sectors (banks, REITs, utilities) - expected and correct,
-- same as capex is NULL for many financials today.

ALTER TABLE annual_income_statement
    ADD COLUMN IF NOT EXISTS research_development_expense NUMERIC;

ALTER TABLE quarterly_income_statement
    ADD COLUMN IF NOT EXISTS research_development_expense NUMERIC;
