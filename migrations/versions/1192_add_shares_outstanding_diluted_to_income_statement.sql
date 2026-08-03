-- Migration 1192: Add shares_outstanding_diluted to annual income statement
--
-- ISSUE: Some real, actively-traded operating companies (live-confirmed: JOUT/Johnson
-- Outdoors has 44 real 10-K entries, ERIE/Erie Indemnity, GPRO/GoPro) only report
-- "WeightedAverageNumberOfDilutedSharesOutstanding" in their SEC XBRL filings, never
-- "WeightedAverageNumberOfSharesOutstandingBasic" - common for filers with simple
-- capital structures that collapse basic/diluted reporting into a single diluted tag.
-- shares_outstanding_basic (migration 1171) stays permanently NULL for these filers,
-- and load_sec_valuations.py's shares_outstanding_unavailable fallback chain (company_info_sec,
-- net_income/eps derivation) also comes up empty for them, so PE/PB/PS/market_cap never
-- compute despite the company having complete revenue/net_income data - this is the root
-- cause behind several real operating companies (not SPACs/CEFs/trusts) showing "No SEC
-- data" on the scores page.
--
-- FIX: give the diluted share count its own column (not overloading shares_outstanding_basic,
-- to avoid changing behavior for filers that already report basic correctly) so
-- load_sec_valuations.py can use it as a last-resort fallback only when basic is
-- unavailable in every fiscal year.

ALTER TABLE annual_income_statement ADD COLUMN IF NOT EXISTS shares_outstanding_diluted NUMERIC;
ALTER TABLE quarterly_income_statement ADD COLUMN IF NOT EXISTS shares_outstanding_diluted NUMERIC;

COMMENT ON COLUMN annual_income_statement.shares_outstanding_diluted IS
    'Real SEC XBRL WeightedAverageNumberOfDilutedSharesOutstanding concept - fallback share count for filers that never report the basic variant (shares_outstanding_basic).';
COMMENT ON COLUMN quarterly_income_statement.shares_outstanding_diluted IS
    'Real SEC XBRL WeightedAverageNumberOfDilutedSharesOutstanding concept - fallback share count for filers that never report the basic variant (shares_outstanding_basic).';
