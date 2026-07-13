-- Migration 1107: Add missing data_unavailable columns to etf_symbols
--
-- CONTEXT: loaders/load_market_constituents.py::_upsert_etf_symbols() has always
-- inserted into etf_symbols(symbol, security_name, data_unavailable,
-- data_unavailable_reason), but no migration ever created these two columns --
-- confirmed missing in both local dev and AWS RDS (not out-of-band drift, a genuine
-- gap). This crashes the StockSymbols step (first step of the eod_pipeline state
-- machine) on every single run with:
--   UndefinedColumn: column "data_unavailable" of relation "etf_symbols" does not exist
-- which blocks every later pipeline step (market_health_daily, trend_template_data,
-- market_exposure_daily, etc.) from ever running.

ALTER TABLE etf_symbols
ADD COLUMN IF NOT EXISTS data_unavailable BOOLEAN DEFAULT FALSE,
ADD COLUMN IF NOT EXISTS data_unavailable_reason VARCHAR(500);
