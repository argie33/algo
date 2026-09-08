-- Migration 1271: Add goodwill_impairment_loss to annual/quarterly income statement
--
-- Found via scripts/xbrl_concept_coverage_scan.py (systematic missing-concept scan, see
-- CLAUDE.md's "Finding missing XBRL concepts systematically" section): us-gaap:
-- GoodwillImpairmentLoss is tagged by 2,567 real filers but was never fetched anywhere - no
-- goodwill_impairment_loss-shaped column existed in the schema. This is a P&L (income-
-- statement) concept: the period impairment CHARGE taken against goodwill, distinct from
-- annual_balance_sheet.goodwill (the balance-sheet carrying amount, already extracted) and
-- from the existing _reject_implausible_goodwill sanity check on that balance-sheet figure -
-- unrelated to this new column.
--
-- Live-confirmed via real SEC companyfacts JSON: Kraft Heinz Co FY2025 (period end
-- 2025-12-27) = $6,734,000,000, CVS Health Corporation FY2025 (period end 2025-12-31) =
-- $5,725,000,000, Centene Corporation FY2025 (period end 2025-09-30) = $6,723,000,000 - all
-- real, material impairment charges consistent with each company's well-known recent
-- goodwill write-downs.
--
-- Same table scope as accounts_payable (migration 1263) / operating_expenses (migration
-- 1264): annual + quarterly only. ttm_income_statement's schema_cols intentionally excludes
-- detailed line items already (same "ttm carries only core aggregate fields" convention).
-- This migration only adds the column and wires extraction/field-mapping in the same
-- commit; no scoring/quality-pillar use yet, data-availability only. Naturally sparse/NULL
-- for the vast majority of company-years (goodwill impairment is an episodic, not
-- recurring, charge) - expected and correct, not a bug to chase.

ALTER TABLE annual_income_statement ADD COLUMN IF NOT EXISTS goodwill_impairment_loss NUMERIC(20, 2);
ALTER TABLE quarterly_income_statement ADD COLUMN IF NOT EXISTS goodwill_impairment_loss NUMERIC(20, 2);

COMMENT ON COLUMN annual_income_statement.goodwill_impairment_loss IS
    'Real SEC XBRL GoodwillImpairmentLoss concept - period impairment charge against goodwill. Not the balance-sheet carrying amount (see annual_balance_sheet.goodwill). Not yet used in any scoring/quality-pillar logic.';
COMMENT ON COLUMN quarterly_income_statement.goodwill_impairment_loss IS
    'Real SEC XBRL GoodwillImpairmentLoss concept - period impairment charge against goodwill. Not the balance-sheet carrying amount (see quarterly_balance_sheet.goodwill). Not yet used in any scoring/quality-pillar logic.';
