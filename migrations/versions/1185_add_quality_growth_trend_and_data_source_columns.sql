-- Migration 1185: Add quality_metrics growth-trend columns, data_source, and stability_metrics gaps
--
-- ISSUE: same untracked-drift class as migrations 1181-1184. loaders/load_value_quality_
-- growth_metrics.py's own quality_metrics INSERT (see its _insert_quality_metrics method)
-- writes the SAME growth-trend fields into BOTH quality_metrics and growth_metrics (by
-- design - quality_metrics uses them as quality-score sub-components, growth_metrics uses
-- them for growth scoring; two real consumers of the same computed values, not a duplicate
-- table). Migration 1174 added these 10 trend fields (+ reasons) to growth_metrics only;
-- quality_metrics's own copy was never migrated, so its INSERT 503s/crashes with
-- UndefinedColumn on any database that has 1174 but not this fix.
--
-- Also: quality_metrics/growth_metrics/stability_metrics all write a `data_source` column
-- (value_metrics already has it, migration untracked same as the others) - never added to
-- these three. stability_metrics's INSERT also references `created_at` and `debt_to_assets`
-- (quality_metrics already has debt_to_assets; stability_metrics's own copy - used for a
-- different sub-score - was never migrated).

ALTER TABLE quality_metrics
    ADD COLUMN IF NOT EXISTS data_source VARCHAR(50),
    ADD COLUMN IF NOT EXISTS quality_score_unavailable_reason VARCHAR(255),
    ADD COLUMN IF NOT EXISTS net_income_growth_yoy NUMERIC(10, 4),
    ADD COLUMN IF NOT EXISTS net_income_growth_yoy_unavailable_reason VARCHAR(255),
    ADD COLUMN IF NOT EXISTS operating_income_growth_yoy NUMERIC(10, 4),
    ADD COLUMN IF NOT EXISTS operating_income_growth_yoy_unavailable_reason VARCHAR(255),
    ADD COLUMN IF NOT EXISTS gross_margin_trend NUMERIC(10, 4),
    ADD COLUMN IF NOT EXISTS gross_margin_trend_unavailable_reason VARCHAR(255),
    ADD COLUMN IF NOT EXISTS operating_margin_trend NUMERIC(10, 4),
    ADD COLUMN IF NOT EXISTS operating_margin_trend_unavailable_reason VARCHAR(255),
    ADD COLUMN IF NOT EXISTS net_margin_trend NUMERIC(10, 4),
    ADD COLUMN IF NOT EXISTS net_margin_trend_unavailable_reason VARCHAR(255),
    ADD COLUMN IF NOT EXISTS roe_trend NUMERIC(10, 4),
    ADD COLUMN IF NOT EXISTS roe_trend_unavailable_reason VARCHAR(255),
    ADD COLUMN IF NOT EXISTS sustainable_growth_rate NUMERIC(10, 4),
    ADD COLUMN IF NOT EXISTS sustainable_growth_rate_unavailable_reason VARCHAR(255),
    ADD COLUMN IF NOT EXISTS fcf_growth_yoy NUMERIC(10, 4),
    ADD COLUMN IF NOT EXISTS fcf_growth_yoy_unavailable_reason VARCHAR(255),
    ADD COLUMN IF NOT EXISTS ocf_growth_yoy NUMERIC(10, 4),
    ADD COLUMN IF NOT EXISTS ocf_growth_yoy_unavailable_reason VARCHAR(255),
    ADD COLUMN IF NOT EXISTS asset_growth_yoy NUMERIC(10, 4),
    ADD COLUMN IF NOT EXISTS asset_growth_yoy_unavailable_reason VARCHAR(255);

ALTER TABLE growth_metrics ADD COLUMN IF NOT EXISTS data_source VARCHAR(50);

ALTER TABLE stability_metrics
    ADD COLUMN IF NOT EXISTS data_source VARCHAR(50),
    ADD COLUMN IF NOT EXISTS created_at TIMESTAMP WITH TIME ZONE DEFAULT NOW(),
    ADD COLUMN IF NOT EXISTS debt_to_assets NUMERIC(8, 4);
