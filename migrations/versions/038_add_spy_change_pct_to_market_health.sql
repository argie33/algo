-- Migration 038: Add SPY change percent to market_health_daily (Issue E4)
-- Adds pre-computed SPY daily change percentage to eliminate calculation in dashboard fetch_market()
-- This moves calculation logic from data-presentation layer to data-loading layer
-- Column is nullable with no default — safe to add on live tables without locking

ALTER TABLE market_health_daily
    ADD COLUMN IF NOT EXISTS spy_change_pct DECIMAL(8, 2) NULL;
