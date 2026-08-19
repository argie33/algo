-- Migration 1211: Add is_foreign_private_issuer to company_info_sec
--
-- Live-confirmed 2026-08-19 (goal: "no SEC data"/missing factor inputs audit): TSM (Taiwan
-- Semiconductor, 1 ADS = 5 ordinary shares) showed market_cap=$10.7 TRILLION and
-- pe_ratio=304 in sec_valuations - both ~5x too high. Root cause: TSM's 20-F correctly
-- reports revenue/net_income/EPS/shares outstanding in LOCAL ordinary-share terms (a real,
-- correctly-filed fact - TSM's own filing, not a parsing bug), but load_sec_valuations.py
-- combines these with the US ADS trading price ($413.41), a unit mismatch. Independently
-- cross-checked against yfinance's live sharesOutstanding (5,186,474,013, matching our raw
-- count divided by ~5.000) and marketCap ($2.14T)/trailingPE (30.9) - confirms the ADS
-- ratio and that the stored figures were ~5x too high, not a guess.
--
-- A same-day fix (load_company_info_sec.py) already stopped ONE source of this corruption
-- (the dei:EntityCommonStockSharesOutstanding cover-page fact, guarded to domestic forms
-- only, matching the existing guard in utils/external/sec_statements.py). But
-- load_sec_valuations.py ALSO derives shares_outstanding from net_income/EPS division as an
-- earlier-priority fallback tier - for TSM this reconstructs the exact same local-share
-- count (net_income and EPS are both filed on the same ordinary-share basis), completely
-- bypassing the company_info_sec fix. That derivation is mathematically correct in
-- isolation (it recovers exactly what the filer itself divided to compute EPS) but produces
-- the wrong UNIT the moment it's combined with an ADS-denominated price - the real problem
-- is structural to any 20-F/40-F/6-K filer's income-statement figures, not just one column.
--
-- This flag lets load_sec_valuations.py (and any other consumer) skip share-count-derived
-- calculations entirely for foreign private issuers rather than risk the same unit mismatch
-- in a fallback tier nobody has audited yet. Computed for free in load_company_info_sec.py
-- from the SEC submissions form list it already fetches for has_annual_report_filing - no
-- new API call.

ALTER TABLE company_info_sec ADD COLUMN IF NOT EXISTS is_foreign_private_issuer BOOLEAN;

COMMENT ON COLUMN company_info_sec.is_foreign_private_issuer IS
    'True if this symbol has ever filed a 20-F/20-F-A/40-F/40-F-A/6-K (foreign private issuer forms). NULL means not yet computed (pre-migration row, or company_info_sec has not run for this symbol since). Used to gate share-count-derived valuation math that assumes a domestic (10-K/10-Q), US-registered-security-denominated filing - see loaders/load_sec_valuations.py and migration 1211''s own comment for the live TSM case this exists to prevent.';
