-- Migration 1265: Add noncontrolling_interest to annual/quarterly balance sheet
--
-- Root-caused via tie_out.py's check_balance_sheet_identity: 761/5,078 (15%) of the annual
-- universe fails assets == liabilities + stockholders_equity beyond 1% tolerance - not an
-- extraction bug. Our schema's stockholders_equity column stores the narrower parent-only
-- concept, but any filer with a material noncontrolling/minority interest (JVs, consolidated
-- funds, partial subsidiaries) has a real identity of
-- assets == liabilities + stockholders_equity + noncontrolling_interest instead. Affects
-- large, well-covered names: XOM, CVX, KKR, APO, CB, RTX, BLK, NEE, D, ENB, VOYA, FNF, IBKR.
--
-- Live-confirmed via real SEC companyfacts JSON: XOM directly tags us-gaap:MinorityInterest
-- (not the combined StockholdersEquityIncludingPortionAttributableToNoncontrollingInterest
-- variant) - FY2009 (period end 2009-12-31) = $4,823,000,000, closing the exact gap between
-- XOM's assets and liabilities+stockholders_equity for that fiscal year.
--
-- Same table scope as accounts_payable (migration 1263): annual + quarterly only.

ALTER TABLE annual_balance_sheet ADD COLUMN IF NOT EXISTS noncontrolling_interest NUMERIC(20, 2);
ALTER TABLE quarterly_balance_sheet ADD COLUMN IF NOT EXISTS noncontrolling_interest NUMERIC(20, 2);

COMMENT ON COLUMN annual_balance_sheet.noncontrolling_interest IS
    'Real SEC XBRL MinorityInterest concept - equity attributable to noncontrolling/minority interests, not the parent. Used by check_balance_sheet_identity to complete assets = liabilities + stockholders_equity + noncontrolling_interest. Not yet used in any scoring/quality-pillar logic.';
COMMENT ON COLUMN quarterly_balance_sheet.noncontrolling_interest IS
    'Real SEC XBRL MinorityInterest concept - equity attributable to noncontrolling/minority interests, not the parent. Not yet used in any scoring/quality-pillar logic.';
