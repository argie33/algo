-- Migration 1200: Clean up dead/test rows in sector_ranking
--
-- ISSUE: sector_ranking currently carries 422 of its 1050 rows (371 of 386 distinct
-- sector_name values) that the live loader (loaders/load_sector_industry_daily.py) never
-- reads or writes:
--   1. 339 rows dated 2026-07-19, all sharing one identical microsecond created_at
--      timestamp, using SEC SIC-description names ("Adhesives & Sealants", "Air Courier
--      Services", ...) - frozen output of a pre-consolidation loader version, from before
--      the file's own comment ("Deliberately NOT the Session 279 SIC-description switch")
--      fixed sector_ranking to use company_profile.sector (GICS-style) exclusively.
--      stock_count is NULL on every one of these rows (written before migration 1141 added
--      that column) and none has been touched since.
--   2. 15 rows dated 2026-08-05 with names like AttrTest/PoolTest/StateCheckTest/
--      DebugTest2/HotfixTest - literal debug-script artifacts written directly against the
--      real local "stocks" dev DB (CLAUDE.md: algo_trading is the pytest-only DB; stocks is
--      the real one), not this loader's output at all.
--
-- IMPACT TODAY: confirmed live via direct query - neither breaks the current /api/sectors
-- dashboard endpoint (its query joins sector_ranking to company_profile.sector-derived
-- names, which these rows never match) nor algo/signals/sector_rotation.py's MAX(date)
-- lookup (the real GICS rows are already the most recent date in the table, 2026-08-21 at
-- migration time). This is a latent landmine, not a live break: if a future debug script
-- ever writes a same-day/future-day junk row again, sector_rotation.py's
-- `WHERE date = (SELECT MAX(date) FROM sector_ranking)` would silently pick that date
-- instead of the real trading day - its own required-sector fail-fast would catch that
-- specific case loudly today, but the row shouldn't be there regardless. Cleaning up now
-- rather than waiting on the existing 90-day retention DELETE (which wouldn't reach the
-- 2026-07-19 batch until ~2026-10-19) so the table stops misrepresenting "sectors tracked"
-- to anyone auditing it.
--
-- SAFE: explicitly preserves every sector_name the loader's current AND prior GICS/
-- Morningstar naming generations have ever legitimately written (including now-renamed
-- ones still needed for historical rank_4w_ago/rank_12w_ago lookback lookups: "Basic
-- Materials" -> "Materials", "Consumer Staples" -> "Consumer Defensive", "Financials" ->
-- "Financial Services", "Consumer Discretionary" -> "Consumer Cyclical" are all real
-- yfinance/GICS taxonomy generations this loader's source data has used over time, not
-- junk - live-verified each has genuine multi-day rank history, unlike the deleted rows).

DELETE FROM sector_ranking
WHERE sector_name NOT IN (
    'Basic Materials', 'Communication Services', 'Consumer Cyclical', 'Consumer Defensive',
    'Consumer Discretionary', 'Consumer Staples', 'Energy', 'Financial Services', 'Financials',
    'Healthcare', 'Industrials', 'Materials', 'Other', 'Real Estate', 'Technology', 'Unknown',
    'Utilities'
);
