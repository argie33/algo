-- Migration 1263: Add accounts_payable to annual/quarterly balance sheet
--
-- Found via scripts/xbrl_concept_coverage_scan.py (systematic missing-concept scan, see
-- CLAUDE.md's "Finding missing XBRL concepts systematically" section): us-gaap:AccountsPayableCurrent
-- is tagged by 3,392 real filers but was never in this loader's concept allowlist at all - no
-- accounts_payable-shaped column existed anywhere in the schema. Live-confirmed via real SEC
-- companyfacts JSON: WMT FY2026 (period end 2026-01-31) = $63,061,000,000, TGT FY2026 (period
-- end 2026-01-31) = $12,622,000,000 - both sane, material working-capital figures.
--
-- Same table scope as short_term_debt (migration 1204): annual + quarterly only, matching
-- accounts_receivable/inventory/ppe_net (ttm_balance_sheet only carries the 5 core aggregate
-- fields and has never carried any of the detailed line items). This migration only adds the
-- column and wires extraction/field-mapping in the same commit; no scoring/quality-pillar use
-- yet (data availability first, matching the net_change_cash precedent).

ALTER TABLE annual_balance_sheet ADD COLUMN IF NOT EXISTS accounts_payable NUMERIC(20, 2);
ALTER TABLE quarterly_balance_sheet ADD COLUMN IF NOT EXISTS accounts_payable NUMERIC(20, 2);

COMMENT ON COLUMN annual_balance_sheet.accounts_payable IS
    'Real SEC XBRL AccountsPayableCurrent concept - trade payables owed to suppliers. Not yet used in any scoring/quality-pillar logic.';
COMMENT ON COLUMN quarterly_balance_sheet.accounts_payable IS
    'Real SEC XBRL AccountsPayableCurrent concept - trade payables owed to suppliers. Not yet used in any scoring/quality-pillar logic.';
