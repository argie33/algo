-- Migration 105: Add atr_50 column to technical_data_daily
-- The load_technical_data_daily.py loader computes atr_50 (50-period ATR)
-- but this column was missing from the DB schema, causing bulk insert failures.

ALTER TABLE technical_data_daily
ADD COLUMN IF NOT EXISTS atr_50 DECIMAL(12, 4);

ANALYZE technical_data_daily;
