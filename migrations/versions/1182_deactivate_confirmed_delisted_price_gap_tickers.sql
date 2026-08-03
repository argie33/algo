-- Migration 1182: deactivate symbols confirmed delisted/no-longer-trading, found while
-- root-causing price_daily's chronic ~4% "missing symbol" completion gap (companion to
-- migration 1181's rights/when-issued/depositary-share cleanup).
--
-- Unlike migration 1181 (an instrument-type/text-pattern exclusion), these are plain
-- common-stock tickers with no distinguishing name pattern - they were real, actively
-- traded companies that appear to have been delisted/acquired/gone private recently.
-- Live-verified 2026-08-03:
--   - yf.download() for every symbol below returns "possibly delisted; no price data
--     found" from Yahoo Finance right now (a live, current check, not a cached/stale
--     result).
--   - Each has a clean, non-degrading price_daily history that simply stops within the
--     last 1-3 weeks (dates below), not a long-stale gradual drift - consistent with a
--     recent real-world delisting/corporate event, not a data-quality artifact:
--       AMPGR  last 2026-07-20 (198 rows since 2025-09-09)
--       AVNS   last 2026-07-24 (1291 rows since 2021-05-18)
--       EOSER  last 2026-07-17 (1 row only - 2026-07-17)
--       FGMCR  last 2026-07-17 (21 rows since 2026-06-04)
--       KORE   last 2026-07-23 (1227 rows since 2021-05-18)
--       NSA    last 2026-07-22 (8 rows since 2026-07-13)
--       PCSC   last 2026-07-20 (299 rows since 2024-06-12)
--       PMI    last 2026-07-30 (124 rows since 2025-09-02)
--       SVA    last 2026-07-16 (90 rows since 2026-02-24)
--       TMHC   last 2026-07-23 (1300 rows since 2021-05-19)
--
-- Live-verified before this migration: zero of these 10 symbols have any row in
-- algo_positions or algo_trades (no open positions, no trade history at risk). 5 have
-- historical buy_sell_daily signal rows (AVNS 4, KORE 6, PCSC 17, PMI 10, TMHC 3) but
-- none were ever actually traded - same acceptable pattern as BHFAL in migration 1172.
--
-- Uses the existing `active` column (get_active_symbols() already filters
-- `WHERE active = true` - utils/loaders/helpers.py) rather than a hard delete, so this is
-- reversible and preserves any historical rows in other tables keyed by these symbols.
--
-- NOTE: unlike migration 1181, there is no code-level pattern change here - these are
-- one-off real-world delistings, not a systematic text-matching gap. A future
-- improvement would be an automated housekeeping job that deactivates a symbol after N
-- consecutive "possibly delisted" fetch results, so this class of drift doesn't need a
-- manual migration each time. Not built here - out of scope for this cleanup.

BEGIN;

UPDATE stock_symbols
SET active = false
WHERE symbol IN (
    'AMPGR', 'AVNS', 'EOSER', 'FGMCR', 'KORE', 'NSA', 'PCSC', 'PMI', 'SVA', 'TMHC'
)
AND active = true;

COMMIT;
