-- Migration 065: Add sector-first index on company_profile for sector trend queries
-- The existing idx_company_profile_ticker_sector has ticker first, which can't filter
-- by sector efficiently. The sectors/trends-batch query filters WHERE cp.sector IN (...)
-- and needs a sector-leading index so the planner can lookup tickers by sector,
-- then join to price_daily — instead of scanning all price_daily rows for 90 days.

CREATE INDEX IF NOT EXISTS idx_company_profile_sector_ticker
ON company_profile (sector, ticker)
WHERE sector IS NOT NULL;

ANALYZE company_profile;
