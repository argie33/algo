-- Migration 1205: Add operating/finance lease liability to annual/quarterly balance sheet
--
-- Continuation of migration 1204's total_debt fix (same "loader-review goal" audit,
-- 2026-08-17). Post-ASC 842 (effective 2019), both operating and finance leases are
-- capitalized on the balance sheet as real liabilities (ROU asset / lease liability), but
-- sec_valuations.total_debt (used for enterprise_value/ev_ebitda/ev_revenue and, via
-- debt_for_roic in load_value_quality_growth_metrics.py, ROIC's invested_capital) never
-- fetched either concept - understating EV and overstating ROIC for lease-heavy sectors
-- (retail, restaurants, airlines) even after 1204's fix.
--
-- Live-confirmed against AAPL's real SEC companyfacts JSON (FY2025): "OperatingLeaseLiability"
-- = $12.49B (Current $1.579B + Noncurrent $10.911B, exact match - the combined tag really is
-- the total, not a duplicate/dimensional fact), "FinanceLeaseLiability" = $1.23B (Current
-- $538M + Noncurrent $692M, also exact match). Both are real, separate liabilities from
-- long_term_debt/short_term_debt (migration 1204) - AAPL's LongTermDebt does not include
-- either lease figure.
--
-- Finance leases are unambiguously debt (financed ownership of the underlying asset - same
-- economic substance as a term loan). Operating leases are the S&P/Moody's "adjusted debt"
-- convention (both rating agencies capitalize operating leases into adjusted debt for credit
-- analysis) - included here per explicit user direction to capture this the way credit
-- analysts do, not omit it. total_debt (load_sec_valuations.py, same commit) now sums
-- long_term_debt + short_term_debt + operating_lease_liability + finance_lease_liability.
--
-- This migration only adds the two new columns; load_sec_valuations.py is fixed in the same
-- commit to read and sum them. Existing long_term_debt/short_term_debt data is unaffected;
-- this is additive only.

ALTER TABLE annual_balance_sheet ADD COLUMN IF NOT EXISTS operating_lease_liability NUMERIC;
ALTER TABLE annual_balance_sheet ADD COLUMN IF NOT EXISTS finance_lease_liability NUMERIC;
ALTER TABLE quarterly_balance_sheet ADD COLUMN IF NOT EXISTS operating_lease_liability NUMERIC;
ALTER TABLE quarterly_balance_sheet ADD COLUMN IF NOT EXISTS finance_lease_liability NUMERIC;

COMMENT ON COLUMN annual_balance_sheet.operating_lease_liability IS
    'Real SEC XBRL total operating lease liability (us-gaap:OperatingLeaseLiability, current+noncurrent combined tag) - post-ASC 842 capitalized operating leases. Included in sec_valuations.total_debt per the S&P/Moody''s adjusted-debt convention.';
COMMENT ON COLUMN annual_balance_sheet.finance_lease_liability IS
    'Real SEC XBRL total finance lease liability (us-gaap:FinanceLeaseLiability, current+noncurrent combined tag) - unambiguously debt (financed asset ownership). Included in sec_valuations.total_debt.';
COMMENT ON COLUMN quarterly_balance_sheet.operating_lease_liability IS
    'Real SEC XBRL total operating lease liability (us-gaap:OperatingLeaseLiability, current+noncurrent combined tag) - post-ASC 842 capitalized operating leases. Included in sec_valuations.total_debt per the S&P/Moody''s adjusted-debt convention.';
COMMENT ON COLUMN quarterly_balance_sheet.finance_lease_liability IS
    'Real SEC XBRL total finance lease liability (us-gaap:FinanceLeaseLiability, current+noncurrent combined tag) - unambiguously debt (financed asset ownership). Included in sec_valuations.total_debt.';
