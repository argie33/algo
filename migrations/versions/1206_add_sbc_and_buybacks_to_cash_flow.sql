-- Migration 1206: Add stock_based_compensation and common_stock_repurchased to cash flow
--
-- Continuation of the loader-review goal's SEC data audit (2026-08-17, same session as
-- migrations 1204/1205). Two real, well-populated SEC XBRL concepts our program's quality/
-- capital-allocation metrics could use were never fetched at all:
--
-- Live-confirmed against AAPL's and MSFT's real companyfacts JSON:
-- - "ShareBasedCompensation": AAPL 180 real entries, MSFT 133 real entries. Non-cash
--   compensation expense added back in the operating section of the cash flow statement -
--   material for quality-of-earnings analysis (GAAP free_cash_flow/operating_cash_flow
--   don't subtract it, so a heavy-SBC company's reported FCF/OCF can overstate real economic
--   cash generation available to shareholders without diluting them).
-- - "PaymentsForRepurchaseOfCommonStock": AAPL 126 real entries, MSFT 230 real entries. The
--   standard cash-flow-statement buyback tag (financing-activities outflow), the natural
--   counterpart to the already-captured "dividends_paid" - together they're the two
--   components of total shareholder return/capital return via cash.
--
-- Additive only: this migration adds the columns; load_sec_valuations.py's existing
-- total_debt/EV formulas and quality_metrics' existing payout_ratio/FCF formulas are
-- unchanged - these two new columns are raw SEC data, not yet wired into any derived
-- score/ratio. A future pass can decide how (e.g. SBC-adjusted FCF, shareholder yield =
-- (dividends_paid + common_stock_repurchased) / market_cap) without needing another SEC
-- fetch.

ALTER TABLE annual_cash_flow ADD COLUMN IF NOT EXISTS stock_based_compensation NUMERIC;
ALTER TABLE annual_cash_flow ADD COLUMN IF NOT EXISTS common_stock_repurchased NUMERIC;
ALTER TABLE quarterly_cash_flow ADD COLUMN IF NOT EXISTS stock_based_compensation NUMERIC;
ALTER TABLE quarterly_cash_flow ADD COLUMN IF NOT EXISTS common_stock_repurchased NUMERIC;

COMMENT ON COLUMN annual_cash_flow.stock_based_compensation IS
    'Real SEC XBRL non-cash stock-based compensation expense (us-gaap:ShareBasedCompensation), added back in the operating section of the cash flow statement. Not yet subtracted from free_cash_flow/operating_cash_flow - raw data only.';
COMMENT ON COLUMN annual_cash_flow.common_stock_repurchased IS
    'Real SEC XBRL common stock buybacks (us-gaap:PaymentsForRepurchaseOfCommonStock), a financing-activities cash outflow. Counterpart to dividends_paid - together the two cash components of shareholder return.';
COMMENT ON COLUMN quarterly_cash_flow.stock_based_compensation IS
    'Real SEC XBRL non-cash stock-based compensation expense (us-gaap:ShareBasedCompensation), added back in the operating section of the cash flow statement. Not yet subtracted from free_cash_flow/operating_cash_flow - raw data only.';
COMMENT ON COLUMN quarterly_cash_flow.common_stock_repurchased IS
    'Real SEC XBRL common stock buybacks (us-gaap:PaymentsForRepurchaseOfCommonStock), a financing-activities cash outflow. Counterpart to dividends_paid - together the two cash components of shareholder return.';
