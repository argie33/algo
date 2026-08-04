-- Migration 1194: deactivate OST, confirmed delisted/no-longer-trading.
--
-- Found while investigating remaining price_daily gaps: OST's price_daily rows show close
-- frozen at exactly 1.695 for 109 straight days (2026-04+ through 2026-07-31) with volume
-- always 0/NULL - the same signature migration 1182 used to confirm delistings, not a
-- data-quality artifact.
--
-- Live-verified 2026-08-03: yf.download('OST') returns "possibly delisted; no price data
-- found" for a recent window; yfinance's own historical data shows the identical frozen
-- 1.695/zero-volume carried-forward quote, confirming this isn't a local DB gap but OST
-- itself being delisted upstream.
--
-- Zero rows in algo_positions, algo_trades, or buy_sell_daily for OST - no open positions,
-- no trade history, nothing at risk.
--
-- Uses the existing `active` column (same pattern as migration 1182) rather than a hard
-- delete - reversible, preserves any historical rows in other tables keyed by this symbol.

BEGIN;

UPDATE stock_symbols
SET active = false
WHERE symbol = 'OST'
AND active = true;

COMMIT;
