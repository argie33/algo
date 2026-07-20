-- Migration 1125: Fix unbounded row growth in company_info_sec
--
-- Same bug class as migration 1124 (institutional_holdings_13f / insider_holdings_sec).
-- company_info_sec was created with PRIMARY KEY (symbol, filing_date), but
-- load_company_info_sec.py writes filing_date = today's date (now_et.date()) on
-- EVERY run, even though the loader's own docstring says "Update frequency: Annual
-- (company info changes rarely)". Since filing_date changes every day the loader
-- runs, ON CONFLICT (symbol, filing_date) never matches the previous row, so every
-- run INSERTs a fresh duplicate row per symbol instead of updating one in place.
-- Caught live: 2026-07-19 wrote 4,678 rows, 2026-07-18 wrote 177 rows, leaving 175
-- symbols with 2 rows each after just one extra day of runs (4,855 total rows /
-- 4,680 distinct symbols).
--
-- company_info_sec is conceptually a current-snapshot-per-symbol table (same as
-- positioning_metrics, sec_valuations, risk_metrics_daily, and now
-- institutional_holdings_13f / insider_holdings_sec) — filing_date here records
-- "when we last refreshed this symbol from SEC EDGAR," not a genuine distinct SEC
-- filing date. Fix: dedupe to one row per symbol (keep the most recently written),
-- then change the primary key to (symbol) so future runs upsert in place.
-- filing_date remains a normal column (last-refreshed timestamp).

BEGIN;

DELETE FROM company_info_sec
WHERE ctid NOT IN (
    SELECT DISTINCT ON (symbol) ctid
    FROM company_info_sec
    ORDER BY symbol, filing_date DESC, created_at DESC
);

ALTER TABLE company_info_sec DROP CONSTRAINT company_info_sec_pkey;
ALTER TABLE company_info_sec ADD PRIMARY KEY (symbol);

COMMIT;
