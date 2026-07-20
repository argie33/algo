-- Migration 1140: Add days_to_cover and avg_daily_volume to short_interest_finra
-- Date: 2026-07-20
--
-- ROOT CAUSE: utils/finra_short_interest.py's FINRAShortInterestFetcher.fetch_latest()
-- returns {"short_shares", "days_to_cover", "avg_daily_volume"} per symbol from FINRA's
-- authoritative Consolidated Short Interest API, but loaders/load_short_interest_finra.py
-- only ever extracted finra_row["short_shares"] - days_to_cover and avg_daily_volume were
-- fetched and then never referenced anywhere, silently discarded (no column even existed
-- to hold them). days_to_cover is a standard short-squeeze risk metric (days of average
-- volume needed to cover all short positions) - a meaningful loss, not a cosmetic gap.

BEGIN;

ALTER TABLE short_interest_finra ADD COLUMN IF NOT EXISTS days_to_cover NUMERIC(8, 2);
ALTER TABLE short_interest_finra ADD COLUMN IF NOT EXISTS avg_daily_volume BIGINT;

COMMENT ON COLUMN short_interest_finra.days_to_cover IS
    'FINRA-reported days-to-cover (short_shares / avg_daily_volume) - standard short-squeeze risk metric. Column was missing entirely before migration 1140; the loader fetched this from FINRA but had nowhere to put it.';

COMMENT ON COLUMN short_interest_finra.avg_daily_volume IS
    'FINRA-reported average daily volume used to compute days_to_cover. Column was missing entirely before migration 1140.';

COMMIT;
