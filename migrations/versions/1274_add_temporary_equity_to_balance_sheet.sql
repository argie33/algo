-- Migration 1274: Add temporary_equity to annual/quarterly balance sheet
--
-- Root-caused via tie_out.py's check_balance_sheet_identity own 2026-09-06/07 NOTEs: after
-- migration 1265 (noncontrolling_interest) collapsed the dominant XOM/CVX/KKR-style NCI
-- population, a remaining "PROK/ATTO/FAC/LTGO/SCTX-style" population was explicitly left
-- unfixed - modest assets/liabilities with huge negative stockholders_equity, no
-- noncontrolling_interest/MinorityInterest tagged either, described then as "a real
-- temporary/mezzanine equity balance-sheet component... this schema has no column for at all".
--
-- Live-confirmed 2026-09-09 via real SEC companyfacts JSON for all 4 named filers:
--   OBAI (Our Bond Inc, CIK 0001756064): FY2025 assets=$2,501,000, liabilities=$13,775,000,
--     stockholders_equity=-$22,663,000 (residual $11,389,000) - directly-tagged
--     TemporaryEquityCarryingAmountAttributableToParent = $11,389,000 for the SAME period,
--     closing the gap exactly.
--   LTGO (Latigo Biotherapeutics): TemporaryEquityCarryingAmountAttributableToParent =
--     $288,582,000, exactly matching this check's own flagged residual.
--   SCTX (Scribe Therapeutics): TemporaryEquityCarryingAmountAttributableToParent =
--     $120,356,000, exactly matching this check's own flagged residual.
--   PROK (ProKidney Corp, Up-C structure): carries RedeemableNoncontrollingInterestEquity
--     OtherCarryingAmount (a sibling concept, not fetched by this migration - PROK's gap is
--     redeemable-NCI-shaped rather than parent-mezzanine-shaped, tracked separately, not
--     expected to fully close from this column alone).
--
-- Same table scope as noncontrolling_interest (migration 1265): annual + quarterly only.
-- Not used in any scoring/quality-pillar logic - book value/ROE/P-B correctly keep using
-- stockholders_equity alone (mezzanine equity is deliberately excluded from permanent common
-- equity under GAAP, so scoring is already right; only this tie-out check's identity needed
-- the missing term).

ALTER TABLE annual_balance_sheet ADD COLUMN IF NOT EXISTS temporary_equity NUMERIC(20, 2);
ALTER TABLE quarterly_balance_sheet ADD COLUMN IF NOT EXISTS temporary_equity NUMERIC(20, 2);

COMMENT ON COLUMN annual_balance_sheet.temporary_equity IS
    'Real SEC XBRL TemporaryEquityCarryingAmountAttributableToParent concept - mezzanine equity (redeemable preferred, Up-C pre-IPO units, etc.) presented between liabilities and permanent stockholders equity. Used by check_balance_sheet_identity to complete assets = liabilities + temporary_equity + stockholders_equity + noncontrolling_interest. Deliberately NOT used in any scoring/quality-pillar logic (book value/ROE correctly exclude mezzanine equity from common equity).';
COMMENT ON COLUMN quarterly_balance_sheet.temporary_equity IS
    'Real SEC XBRL TemporaryEquityCarryingAmountAttributableToParent concept - mezzanine equity between liabilities and permanent stockholders equity. Not used in any scoring/quality-pillar logic.';
