-- Migration 075: Add put_call_ratio to market_health_daily
-- Required by load_market_health_daily.py which computes daily put/call ratio
-- from SPY options chain and market_exposure.py which reads it as a scoring factor.
-- Column exists in schema.sql but was never added as a versioned migration for existing DBs.

ALTER TABLE market_health_daily
    ADD COLUMN IF NOT EXISTS put_call_ratio DECIMAL(8, 4);
