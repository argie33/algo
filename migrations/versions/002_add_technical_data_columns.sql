-- Migration: Add missing columns to technical_data_daily
-- Columns were added to init.sql after the table was created in production,
-- but CREATE TABLE IF NOT EXISTS does not add new columns to existing tables.

-- Up
ALTER TABLE technical_data_daily ADD COLUMN IF NOT EXISTS rsi_14 DECIMAL(8, 4);
ALTER TABLE technical_data_daily ADD COLUMN IF NOT EXISTS macd_histogram DECIMAL(12, 4);
ALTER TABLE technical_data_daily ADD COLUMN IF NOT EXISTS sma_150 DECIMAL(12, 4);
ALTER TABLE technical_data_daily ADD COLUMN IF NOT EXISTS atr_14 DECIMAL(12, 4);
ALTER TABLE technical_data_daily ADD COLUMN IF NOT EXISTS bb_upper DECIMAL(12, 4);
ALTER TABLE technical_data_daily ADD COLUMN IF NOT EXISTS bb_middle DECIMAL(12, 4);
ALTER TABLE technical_data_daily ADD COLUMN IF NOT EXISTS bb_lower DECIMAL(12, 4);
ALTER TABLE technical_data_daily ADD COLUMN IF NOT EXISTS volume_ma_50 BIGINT;

-- Down
ALTER TABLE technical_data_daily DROP COLUMN IF EXISTS rsi_14;
ALTER TABLE technical_data_daily DROP COLUMN IF EXISTS macd_histogram;
ALTER TABLE technical_data_daily DROP COLUMN IF EXISTS sma_150;
ALTER TABLE technical_data_daily DROP COLUMN IF EXISTS atr_14;
ALTER TABLE technical_data_daily DROP COLUMN IF EXISTS bb_upper;
ALTER TABLE technical_data_daily DROP COLUMN IF EXISTS bb_middle;
ALTER TABLE technical_data_daily DROP COLUMN IF EXISTS bb_lower;
ALTER TABLE technical_data_daily DROP COLUMN IF EXISTS volume_ma_50;
