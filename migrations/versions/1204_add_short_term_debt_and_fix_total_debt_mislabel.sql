-- Migration 1204: Add short_term_debt to annual/quarterly balance sheet
--
-- Companion fix (loaders/load_sec_valuations.py, same session): sec_valuations.total_debt
-- has NEVER been real debt - since the EV-metrics feature was first added, its SQL source
-- was "SELECT total_liabilities, cash_and_equivalents FROM annual_balance_sheet", so
-- "total_debt" was literally total_liabilities (accounts payable, deferred revenue, accrued
-- expenses, pensions, leases, everything) the entire time, not interest-bearing debt.
-- Live-confirmed against the real local DB and SEC EDGAR directly: AAPL FY2025 real
-- long_term_debt = $90.7B, but sec_valuations.total_debt = $285.5B (exactly
-- annual_balance_sheet.total_liabilities for that year) - a ~3.1x overstatement. Same pattern
-- confirmed for MSFT/GOOGL/F ($315.99B/$281.5B/$244.95B "debt" vs real long-term debt an
-- order of magnitude smaller or NULL). This silently inflated enterprise_value/ev_ebitda/
-- ev_revenue for every symbol and (via debt_for_roic in
-- loaders/load_value_quality_growth_metrics.py, which already correctly treats
-- total_debt_ev as "the real number, 81% available" and explicitly rejected a
-- total_liabilities-derived debt estimate as illegitimate) understated roic_pct the same way,
-- universe-wide.
--
-- This migration only adds the new column; load_sec_valuations.py is fixed in the same
-- commit to read long_term_debt (+ this new short_term_debt) instead of total_liabilities.
-- short_term_debt captures real short-term borrowings (commercial paper, current notes
-- payable) that LongTermDebt's concept does not cover - live-confirmed AAPL FY2025
-- CommercialPaper = $7.98B, a real, separate debt instrument. Existing long_term_debt data
-- is unaffected; this is additive only.

ALTER TABLE annual_balance_sheet ADD COLUMN IF NOT EXISTS short_term_debt NUMERIC;
ALTER TABLE quarterly_balance_sheet ADD COLUMN IF NOT EXISTS short_term_debt NUMERIC;

COMMENT ON COLUMN annual_balance_sheet.short_term_debt IS
    'Real SEC XBRL short-term interest-bearing debt (CommercialPaper / ShortTermBorrowings) - combined with long_term_debt for a real total_debt figure. NOT the same as current_liabilities (which includes non-debt items like accounts payable).';
COMMENT ON COLUMN quarterly_balance_sheet.short_term_debt IS
    'Real SEC XBRL short-term interest-bearing debt (CommercialPaper / ShortTermBorrowings) - combined with long_term_debt for a real total_debt figure. NOT the same as current_liabilities (which includes non-debt items like accounts payable).';
