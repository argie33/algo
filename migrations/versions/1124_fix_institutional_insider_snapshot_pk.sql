-- Migration 1124: Fix unbounded row growth in institutional_holdings_13f / insider_holdings_sec
--
-- Both tables were created with PRIMARY KEY (symbol, filing_date), but both loaders
-- write filing_date = today's date on EVERY run regardless of whether a real SEC
-- filing was found (both sources are currently always data_unavailable=True - 13F is
-- blocked on the CUSIP->ticker crosswalk, Form 4/5 parsing isn't implemented yet).
-- Since filing_date changes every day, ON CONFLICT (symbol, filing_date) never matches
-- the previous day's row, so every loader run INSERTs a fresh duplicate "unavailable"
-- row per symbol instead of updating one in place. institutional_holdings_13f grew
-- from 11,115 to 11,381 rows (4,759 distinct symbols) DURING this audit session alone.
--
-- These tables are conceptually a current-snapshot-per-symbol (same as
-- positioning_metrics, sec_valuations, risk_metrics_daily), not a real historical
-- time series like short_interest_finra (whose filing_date IS a genuine distinct
-- FINRA-published settlement cycle, not "today"). Fix: dedupe to one row per symbol
-- (keep the most recently written), then change the primary key to (symbol) so
-- future runs upsert in place. filing_date remains a normal column, still useful
-- once real Form 13F/4 data lands.
--
-- Also purges 1,979 stale positioning_metrics rows with data_source='yfinance',
-- written before the yfinance-removal commits landed. Confirmed (this session) these
-- belong to symbols no longer in stock_symbols at all (delisted/removed) and are not
-- read by any active/tradeable stock_scores row - pure leftover clutter inflating raw
-- "available" counts for anyone querying the table directly.

BEGIN;

-- Dedupe institutional_holdings_13f: keep one row per symbol (latest filing_date,
-- tiebreak by created_at)
DELETE FROM institutional_holdings_13f
WHERE ctid NOT IN (
    SELECT DISTINCT ON (symbol) ctid
    FROM institutional_holdings_13f
    ORDER BY symbol, filing_date DESC, created_at DESC
);

ALTER TABLE institutional_holdings_13f DROP CONSTRAINT institutional_holdings_13f_pkey;
ALTER TABLE institutional_holdings_13f ADD PRIMARY KEY (symbol);

-- Dedupe insider_holdings_sec: same shape
DELETE FROM insider_holdings_sec
WHERE ctid NOT IN (
    SELECT DISTINCT ON (symbol) ctid
    FROM insider_holdings_sec
    ORDER BY symbol, filing_date DESC, created_at DESC
);

ALTER TABLE insider_holdings_sec DROP CONSTRAINT insider_holdings_sec_pkey;
ALTER TABLE insider_holdings_sec ADD PRIMARY KEY (symbol);

-- Purge stale pre-removal yfinance rows from positioning_metrics
DELETE FROM positioning_metrics WHERE data_source = 'yfinance';

COMMIT;
