-- Expand quality_metrics columns to handle extreme values
-- Some stocks with massive losses produce percentage values that exceed DECIMAL(8,4) range.
-- Expand to DECIMAL(10,2) to handle outliers (-99,999.99 to 99,999.99).

ALTER TABLE quality_metrics
  ALTER COLUMN operating_margin TYPE DECIMAL(10, 2),
  ALTER COLUMN net_margin TYPE DECIMAL(10, 2),
  ALTER COLUMN roe TYPE DECIMAL(10, 2),
  ALTER COLUMN roa TYPE DECIMAL(10, 2),
  ALTER COLUMN debt_to_equity TYPE DECIMAL(10, 2),
  ALTER COLUMN current_ratio TYPE DECIMAL(10, 2),
  ALTER COLUMN quick_ratio TYPE DECIMAL(10, 2),
  ALTER COLUMN interest_coverage TYPE DECIMAL(10, 2);

-- Note: growth_metrics, value_metrics, positioning_metrics, stability_metrics already have
-- DECIMAL(14,4) or DECIMAL(8,4) columns that can handle these ranges without issue.
