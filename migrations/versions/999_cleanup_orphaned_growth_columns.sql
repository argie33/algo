-- Migration: Remove unused growth_metrics columns
-- These columns (quarterly_growth_momentum, revenue_growth_yoy) were added to the schema
-- but were never populated by the loader. They're not referenced in load_quality_growth_metrics.py
-- and advanced_filters.py has fallback logic for when they're NULL.
-- Clean up schema by removing unused columns.

ALTER TABLE IF EXISTS growth_metrics
DROP COLUMN IF EXISTS quarterly_growth_momentum CASCADE;

ALTER TABLE IF EXISTS growth_metrics
DROP COLUMN IF EXISTS revenue_growth_yoy CASCADE;
