-- Migration 1310: Add operating_lease_right_of_use_asset to annual/quarterly balance sheet
--
-- Goal: data-issue-reduction session, 2026-09-18. ppe_net is the single largest unreviewed-
-- divergent field in xbrl_yfinance_line_item_report (746 rows at investigation time), with the
-- vast majority (~730/746) clustering at ratio 0.1-0.5 (our value consistently smaller than
-- yfinance's). Live-verified against real SEC companyfacts JSON for two unrelated filers (AAP,
-- Advance Auto Parts; AMPG, AmpliTech Group): our stored ppe_net = the filer's own
-- PropertyPlantAndEquipmentNet concept exactly, and yfinance's larger figure = that same PP&E
-- value PLUS the filer's OperatingLeaseRightOfUseAsset concept, summed (AAP FY2022:
-- 1,690,139,000 + 2,607,690,000 = 4,297,829,000, exact match to yfinance's reported figure;
-- AMPG FY2023: 2,599,448 + 3,538,798 = 6,138,246, exact match). This is the same "operating
-- lease capitalization, post-ASC 842" shape already handled for total_debt in migration 1205
-- (which added operating_lease_liability/finance_lease_liability as separate, additive columns
-- rather than folding them into long_term_debt) - following that same precedent here: this
-- column is purely additive and does NOT change ppe_net's own existing meaning/data. It exists
-- so scripts/xbrl_yfinance_crosscheck.py can add a ppe_net entry to its existing
-- _COMPOSITE_SUM_FIELDS mechanism (already used for depreciation_expense+amortization_expense)
-- and stop flagging a real, well-understood definitional difference as an unreviewed divergence.

ALTER TABLE annual_balance_sheet ADD COLUMN IF NOT EXISTS operating_lease_right_of_use_asset NUMERIC;
ALTER TABLE quarterly_balance_sheet ADD COLUMN IF NOT EXISTS operating_lease_right_of_use_asset NUMERIC;

COMMENT ON COLUMN annual_balance_sheet.operating_lease_right_of_use_asset IS
    'Real SEC XBRL us-gaap:OperatingLeaseRightOfUseAsset - post-ASC 842 capitalized operating lease right-of-use asset. Used only as a crosscheck-comparison addend for ppe_net (see scripts/xbrl_yfinance_crosscheck.py COMPOSITE_SUM_FIELDS) - ppe_net itself is unchanged and still means PropertyPlantAndEquipmentNet alone.';
COMMENT ON COLUMN quarterly_balance_sheet.operating_lease_right_of_use_asset IS
    'Real SEC XBRL us-gaap:OperatingLeaseRightOfUseAsset - post-ASC 842 capitalized operating lease right-of-use asset. Used only as a crosscheck-comparison addend for ppe_net (see scripts/xbrl_yfinance_crosscheck.py COMPOSITE_SUM_FIELDS) - ppe_net itself is unchanged and still means PropertyPlantAndEquipmentNet alone.';
