-- Migration 1264: Add operating_expenses (SG&A) to annual/quarterly income statement
--
-- Found via scripts/xbrl_concept_coverage_scan.py (systematic missing-concept scan, see
-- CLAUDE.md's "Finding missing XBRL concepts systematically" section): us-gaap:
-- SellingGeneralAndAdministrativeExpense is tagged by 2,820+ real filers but was never
-- fetched anywhere - no operating_expenses/SG&A-shaped column existed in the schema. Note
-- this is a DIFFERENT concept from the existing "OperatingExpenses" tag already fetched in
-- utils/external/sec_income_statement.py (see that file's comment on it) - "OperatingExpenses"
-- is a narrower, filer-specific non-COGS-opex remainder only usable as one term of a 4-value
-- operating-income derivation, explicitly NOT a standalone SG&A figure. Selling
-- GeneralAndAdministrativeExpense is the standard, single-concept, universally-comparable SG&A
-- tag most filers use directly.
--
-- Live-confirmed via real SEC companyfacts JSON: WMT FY2026 (period end 2026-01-31) =
-- $147,943,000,000 (~21.7% of revenue, sane for a retailer), TGT FY2026 = $21,535,000,000,
-- AAR CORP FY2026 = $349,300,000, Abbott Labs FY2025 = $12,332,000,000 (~27.8% of revenue,
-- sane for pharma) - all single, real, sane SG&A figures.
--
-- Same table scope as accounts_payable (migration 1263): annual + quarterly only.
-- ttm_income_statement's schema_cols intentionally excludes other detailed line items
-- (research_development_expense, interest_expense, depreciation_expense) already, so
-- operating_expenses follows the same "ttm carries only core aggregate fields" convention.
-- This migration only adds the column and wires extraction/field-mapping in the same commit;
-- no scoring/quality-pillar use yet, and does not wire the previously-rejected
-- operating_income=gross_profit-operating_expenses tie-out check (infeasible until this
-- reloads - see growth_pillar_fresh_sweep_and_tieout_gap_check_20260907 in memory).

ALTER TABLE annual_income_statement ADD COLUMN IF NOT EXISTS operating_expenses NUMERIC(20, 2);
ALTER TABLE quarterly_income_statement ADD COLUMN IF NOT EXISTS operating_expenses NUMERIC(20, 2);

COMMENT ON COLUMN annual_income_statement.operating_expenses IS
    'Real SEC XBRL SellingGeneralAndAdministrativeExpense concept - SG&A. Not yet used in any scoring/quality-pillar logic.';
COMMENT ON COLUMN quarterly_income_statement.operating_expenses IS
    'Real SEC XBRL SellingGeneralAndAdministrativeExpense concept - SG&A. Not yet used in any scoring/quality-pillar logic.';
