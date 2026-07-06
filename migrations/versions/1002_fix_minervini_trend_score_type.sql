-- Fix minervini_trend_score column type from INTEGER to NUMERIC
-- minervini_trend_score is calculated as sum of 8 boolean components (0-8 range)
-- and cast to float in load_trend_criteria_data.py, so must be NUMERIC not INTEGER

ALTER TABLE trend_template_data
  ALTER COLUMN minervini_trend_score TYPE numeric(5,1);

-- Update data_loader_status to record this migration
INSERT INTO data_loader_status (table_name, status, last_updated)
VALUES ('trend_template_data', 'SCHEMA_FIXED', NOW())
ON CONFLICT (table_name) DO UPDATE
SET status = 'SCHEMA_FIXED', last_updated = NOW();
