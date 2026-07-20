-- Migration 1146: Add dividends_paid (cash flow) and dividend_yield (sec_valuations)
-- Date: 2026-07-20
-- (Numbered 1146, not 1143/1144 - those were claimed concurrently by another session's
-- migration for an unrelated config fix; renumbered to avoid collision.)
--
-- ROOT CAUSE: value_metrics.dividend_yield has an 8%-weight slot in load_stock_scores.py's
-- _score_value, but has been hardcoded to None since the Session 271 "SEC-only, no
-- yfinance" migration (load_value_quality_growth_metrics.py: "Not available from SEC;
-- skipped per governance") - confirmed 2026-07-20: 0/4951 rows filled, an 8%-weight bucket
-- dead for the entire universe. Before that migration, dividend data came from yfinance's
-- `info.dividendYield` (removed for governance/reliability reasons, not replaced).
--
-- Fix: SEC EDGAR does have dividend data via the "PaymentsOfDividends" us-gaap concept
-- (total cash dividends paid, annual/quarterly). Adds dividends_paid to both cash flow
-- tables and dividend_yield to sec_valuations (dividend_yield = dividends_paid /
-- market_cap, computed alongside the other valuation ratios in load_sec_valuations.py).

BEGIN;

ALTER TABLE annual_cash_flow ADD COLUMN IF NOT EXISTS dividends_paid NUMERIC;
ALTER TABLE quarterly_cash_flow ADD COLUMN IF NOT EXISTS dividends_paid NUMERIC;
ALTER TABLE sec_valuations ADD COLUMN IF NOT EXISTS dividend_yield NUMERIC;

COMMENT ON COLUMN annual_cash_flow.dividends_paid IS
    'SEC us-gaap:PaymentsOfDividends for the fiscal year (total cash dividends paid, all classes). Feeds sec_valuations.dividend_yield.';
COMMENT ON COLUMN quarterly_cash_flow.dividends_paid IS
    'SEC us-gaap:PaymentsOfDividends for the fiscal quarter. See annual_cash_flow.dividends_paid for usage.';
COMMENT ON COLUMN sec_valuations.dividend_yield IS
    'dividends_paid / market_cap, sourced from annual_cash_flow.dividends_paid. NULL for non-dividend-payers and foreign filers reporting under IFRS (no IFRS alias mapped - see utils/external/sec_statements.py).';

COMMIT;
