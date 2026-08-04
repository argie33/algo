-- Migration 1195: Add shares_outstanding_dei to annual income statement
--
-- ISSUE: A batch of real operating companies with rich, complete revenue/net_income
-- history (live-confirmed: GEF/Greif 19yrs, DGICA/Donegal Group 18yrs, MC/Moelis 15yrs)
-- report ZERO usable value under any share-count concept fetched so far
-- (WeightedAverageNumberOfSharesOutstandingBasic/Diluted, CommonStockSharesOutstanding,
-- WeightedAverageNumberOfShareOutstandingBasicAndDiluted) - live-confirmed via real SEC
-- companyfacts JSON these concepts are simply absent from their us-gaap facts entirely.
-- Some of these filers (live-confirmed: PFLT, TRAD, TRAX, ORKA, KLRA) DO report the
-- share count via the universal SEC cover-page fact "EntityCommonStockSharesOutstanding",
-- which lives under the "dei" (Document and Entity Information) taxonomy, not "us-gaap" -
-- a taxonomy this loader never queried at all until now.
--
-- FIX: give the dei-sourced share count its own column (not overloading
-- shares_outstanding_basic) because dei:EntityCommonStockSharesOutstanding is reported by
-- virtually every filer regardless of accounting quality, including ones that already have
-- a real weighted-average count - sharing a column with the field_mapping "last concept
-- wins" convention would let this cruder point-in-time figure silently overwrite the better
-- weighted-average value for filers that report both. load_sec_valuations.py decides
-- explicitly when to fall back to it (only when nothing better exists for any fiscal year).

ALTER TABLE annual_income_statement ADD COLUMN IF NOT EXISTS shares_outstanding_dei NUMERIC;
ALTER TABLE quarterly_income_statement ADD COLUMN IF NOT EXISTS shares_outstanding_dei NUMERIC;

COMMENT ON COLUMN annual_income_statement.shares_outstanding_dei IS
    'Real SEC XBRL dei:EntityCommonStockSharesOutstanding concept (cover-page share count) - last-resort fallback for filers with no weighted-average or CommonStockShares* concept in us-gaap facts at all.';
COMMENT ON COLUMN quarterly_income_statement.shares_outstanding_dei IS
    'Real SEC XBRL dei:EntityCommonStockSharesOutstanding concept (cover-page share count) - last-resort fallback for filers with no weighted-average or CommonStockShares* concept in us-gaap facts at all.';
