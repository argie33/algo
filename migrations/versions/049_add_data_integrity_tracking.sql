-- Migration 049: Add data integrity tracking columns
-- Tracks when values are capped or use fallback data due to DB constraints or missing source data
-- These support the Financial Data Integrity Audit recommendations

-- buy_sell_daily: Track when volume surge exceeds database DECIMAL(8,4) limit
-- Helps identify signals generated during extreme market conditions where metrics are truncated
ALTER TABLE buy_sell_daily
    ADD COLUMN IF NOT EXISTS volume_surge_capped BOOLEAN DEFAULT FALSE;

-- Add index for quick filtering of signals with capped metrics
CREATE INDEX IF NOT EXISTS buy_sell_daily_volume_surge_capped_idx
    ON buy_sell_daily(date, volume_surge_capped)
    WHERE volume_surge_capped = TRUE;
