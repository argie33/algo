-- Migration: Add data_type column to algo_config table
-- Reason: Config management code expects data_type field for type tracking
-- The schema.sql defines it but existing database doesn't have the column

ALTER TABLE algo_config
ADD COLUMN IF NOT EXISTS data_type VARCHAR(50);

-- Set default data_type for existing rows (infer from key patterns if needed)
UPDATE algo_config
SET data_type = CASE
    WHEN key LIKE '%pct' OR key LIKE '%percent%' THEN 'float'
    WHEN key LIKE '%count%' OR key LIKE '%limit%' THEN 'int'
    WHEN key LIKE '%enable%' OR key LIKE '%require%' THEN 'boolean'
    ELSE 'string'
END
WHERE data_type IS NULL;
