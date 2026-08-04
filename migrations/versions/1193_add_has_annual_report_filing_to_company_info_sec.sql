-- Migration 1193: Add has_annual_report_filing to company_info_sec
--
-- ISSUE: The scores page's "No SEC data" indicator (see lambda/api/routes/scores.py's
-- where_clause) previously only excluded SPAC shells/rights/warrants (via security_name
-- regex) and, as of the SIC-code follow-up in this same file, blank-check SPACs (SIC 6770),
-- oil/gas royalty trusts (SIC 6792), and structured-note certificates (SIC 6189). The
-- largest remaining bucket - closed-end funds/investment trusts (~60+ symbols, BlackRock/
-- Eaton Vance/Gabelli/Invesco/Franklin families etc.) - has no usable SIC signal: live-
-- verified against real SEC EDGAR submissions JSON that CEFs return a BLANK sic/sicDescription,
-- identical to real operating companies (e.g. Bank OZK) already known to be a false-positive
-- risk for name-based filtering.
--
-- FIX: a different, more direct signal - whether the entity has EVER filed a 10-K/10-K-A
-- (domestic annual report) or 20-F/20-F-A (foreign private issuer annual report), the two
-- filing types this pipeline's loaders actually parse for annual_income_statement/
-- annual_balance_sheet data. Live-verified: CEFs (BGT, GAB) file neither - only fund-specific
-- forms (N-Q, NPORT-P, 40-17G, N-30B-2, DEF 14A) - while real operating companies (AAPL,
-- FNWB) have 10-K and foreign filers (IBN/ICICI Bank) have 20-F. This directly answers "can
-- this pipeline structurally ever have annual financial statement data for this symbol",
-- independent of WHY (CEF, royalty trust, SPAC, or any other non-10-K/20-F filer type),
-- without needing a name-based or SIC-based classification at all.

ALTER TABLE company_info_sec ADD COLUMN IF NOT EXISTS has_annual_report_filing BOOLEAN;

COMMENT ON COLUMN company_info_sec.has_annual_report_filing IS
    'Whether SEC EDGAR submissions.filings.recent.form ever includes 10-K/10-K-A or 20-F/20-F-A for this symbol - i.e. whether this pipeline can structurally ever produce annual_income_statement/annual_balance_sheet data for it. NULL = not yet checked (predates this migration, or company_info_sec has no row for the symbol).';
