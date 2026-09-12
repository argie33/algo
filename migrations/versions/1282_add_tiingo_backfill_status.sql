-- Migration 1282: Add tiingo_backfill_status - tracks per-symbol attempts to backfill
-- historical delisted-security prices from Tiingo, for scripts/tiingo_delisted_price_backfill.py.
--
-- Goal session 2026-09-12 (continuation): the user has no budget for a paid survivorship-bias
-- data vendor (Norgate ~$500-700/yr). Tiingo's FREE tier was verified live (see memory
-- tiingo_free_tier_verified_but_too_limited_20260912) to carry real delisted-company history
-- (SIVB/SBNY both confirmed) but is capped at 25 requests/day - far too slow for one run to
-- cover the 540-row inactive/delisted set, but genuinely workable as a slow daily drip, the
-- same "accumulate coverage across many runs" pattern this repo already uses for
-- xbrl_yfinance_crosscheck.py/xbrl_calculation_linkbase_check.py under their own free-tier/
-- rate-limit constraints.
--
-- Without a persistent record of which symbols were already attempted, a daily run would keep
-- re-spending its tiny budget re-discovering the same already-resolved or already-exhausted
-- symbols instead of making forward progress. One row per symbol, written once resolved either
-- way (data found and loaded, or confirmed absent at the vendor too).

CREATE TABLE IF NOT EXISTS tiingo_backfill_status (
    symbol VARCHAR(20) PRIMARY KEY,
    status VARCHAR(20) NOT NULL CHECK (status IN ('backfilled', 'no_data_at_vendor', 'error')),
    rows_inserted INTEGER NOT NULL DEFAULT 0,
    last_attempt_at TIMESTAMP WITH TIME ZONE NOT NULL DEFAULT CURRENT_TIMESTAMP,
    detail VARCHAR(500)
);
