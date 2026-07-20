-- Migration 1135: Track actual data source per price row (fixes silent yfinance fallback)
-- Date: 2026-07-20
--
-- ROOT CAUSE: steering/DATA_LOADERS.md claims "Symbols Alpaca doesn't serve ... are marked
-- explicitly data_unavailable rather than falling back to deprecated yfinance API" - but
-- utils/data/source_router.py::fetch_ohlcv_batch actually DOES fall back to yfinance, both
-- per-symbol (_fill_alpaca_residual_from_yfinance, for symbols Alpaca doesn't serve) and
-- wholesale (full yfinance batch on an Alpaca outage). Each row IS tagged in-memory with
-- `_source_name`, but loaders/price_transformer.py + utils/bulk_insert_manager.py never
-- persisted it - price_daily/etf_price_daily had no column to hold it - so the fallback was
-- genuinely silent at the DB level, violating GOVERNANCE.md's "no silent fallbacks / operator
-- visibility" rules and making it impossible to audit after the fact which rows came from
-- the lower-quality/deprecated source.
--
-- FIX: add a `data_source` column and have loaders/load_prices.py populate it per row from
-- the router's per-row `_source_name` marker (falling back to the batch-level last_source
-- for the wholesale-fallback case, where individual rows aren't tagged). No backfill for
-- existing rows - the source of historical rows was never recorded and cannot be
-- reconstructed; NULL means "recorded before this migration", not "unknown source is alpaca".

BEGIN;

ALTER TABLE price_daily ADD COLUMN IF NOT EXISTS data_source VARCHAR(20);
ALTER TABLE etf_price_daily ADD COLUMN IF NOT EXISTS data_source VARCHAR(20);

COMMENT ON COLUMN price_daily.data_source IS
    'Which upstream API actually served this row: alpaca (primary) or yfinance (per-symbol residual or wholesale-outage fallback - see utils/data/source_router.py). NULL for rows written before this migration.';
COMMENT ON COLUMN etf_price_daily.data_source IS
    'Which upstream API actually served this row: alpaca (primary) or yfinance (per-symbol residual or wholesale-outage fallback - see utils/data/source_router.py). NULL for rows written before this migration.';

COMMIT;
