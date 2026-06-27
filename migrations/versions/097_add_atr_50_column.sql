-- Migration: Add atr_50 column to technical_data_daily
-- Issue: load_vcp_patterns.py requires atr_50 for volatility contraction pattern detection
-- This column stores the 50-period Average True Range for long-term volatility analysis

ALTER TABLE technical_data_daily ADD COLUMN IF NOT EXISTS atr_50 DECIMAL(12, 4);

-- Create index for VCP pattern queries
CREATE INDEX IF NOT EXISTS idx_technical_data_daily_atr_50 ON technical_data_daily(atr_50) WHERE atr_50 IS NOT NULL;
