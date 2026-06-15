-- Migration 074: Add price_data_age_days column to technical_data_daily
-- load_technical_data_daily.py writes this column to track how stale the source
-- price_daily data is (in trading days). Column was added to schema.sql but no
-- migration existed, so the column may be absent on existing instances.
ALTER TABLE technical_data_daily ADD COLUMN IF NOT EXISTS price_data_age_days INTEGER;
