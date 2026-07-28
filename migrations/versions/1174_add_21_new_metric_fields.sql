-- Migration 1174: Add 21 new computed metric fields
-- Adds earnings/estimate fields to quality_metrics and trend fields to growth_metrics
-- These fields support enhanced quality/growth scoring with trend analysis

-- Add 10 earnings/estimate fields to quality_metrics
ALTER TABLE quality_metrics
ADD COLUMN earnings_surprise_avg NUMERIC(10,4),
ADD COLUMN eps_growth_stability NUMERIC(10,4),
ADD COLUMN earnings_beat_rate NUMERIC(10,4),
ADD COLUMN consecutive_positive_quarters NUMERIC(5,0),
ADD COLUMN estimate_revision_direction NUMERIC(10,4),
ADD COLUMN revision_activity_30d NUMERIC(5,0),
ADD COLUMN estimate_momentum_60d NUMERIC(10,4),
ADD COLUMN estimate_momentum_90d NUMERIC(10,4),
ADD COLUMN revision_trend_score NUMERIC(10,4),
ADD COLUMN earnings_growth_4q_avg NUMERIC(10,4);

-- Add corresponding unavailable_reason fields
ALTER TABLE quality_metrics
ADD COLUMN earnings_surprise_avg_unavailable_reason VARCHAR(255),
ADD COLUMN eps_growth_stability_unavailable_reason VARCHAR(255),
ADD COLUMN earnings_beat_rate_unavailable_reason VARCHAR(255),
ADD COLUMN consecutive_positive_quarters_unavailable_reason VARCHAR(255),
ADD COLUMN estimate_revision_direction_unavailable_reason VARCHAR(255),
ADD COLUMN revision_activity_30d_unavailable_reason VARCHAR(255),
ADD COLUMN estimate_momentum_60d_unavailable_reason VARCHAR(255),
ADD COLUMN estimate_momentum_90d_unavailable_reason VARCHAR(255),
ADD COLUMN revision_trend_score_unavailable_reason VARCHAR(255),
ADD COLUMN earnings_growth_4q_avg_unavailable_reason VARCHAR(255);

-- Add 11 trend fields to growth_metrics
ALTER TABLE growth_metrics
ADD COLUMN net_income_growth_yoy NUMERIC(10,4),
ADD COLUMN operating_income_growth_yoy NUMERIC(10,4),
ADD COLUMN gross_margin_trend NUMERIC(10,4),
ADD COLUMN operating_margin_trend NUMERIC(10,4),
ADD COLUMN net_margin_trend NUMERIC(10,4),
ADD COLUMN roe_trend NUMERIC(10,4),
ADD COLUMN sustainable_growth_rate NUMERIC(10,4),
ADD COLUMN quarterly_growth_momentum NUMERIC(10,4),
ADD COLUMN fcf_growth_yoy NUMERIC(10,4),
ADD COLUMN ocf_growth_yoy NUMERIC(10,4),
ADD COLUMN asset_growth_yoy NUMERIC(10,4);

-- Add corresponding unavailable_reason fields
ALTER TABLE growth_metrics
ADD COLUMN net_income_growth_yoy_unavailable_reason VARCHAR(255),
ADD COLUMN operating_income_growth_yoy_unavailable_reason VARCHAR(255),
ADD COLUMN gross_margin_trend_unavailable_reason VARCHAR(255),
ADD COLUMN operating_margin_trend_unavailable_reason VARCHAR(255),
ADD COLUMN net_margin_trend_unavailable_reason VARCHAR(255),
ADD COLUMN roe_trend_unavailable_reason VARCHAR(255),
ADD COLUMN sustainable_growth_rate_unavailable_reason VARCHAR(255),
ADD COLUMN quarterly_growth_momentum_unavailable_reason VARCHAR(255),
ADD COLUMN fcf_growth_yoy_unavailable_reason VARCHAR(255),
ADD COLUMN ocf_growth_yoy_unavailable_reason VARCHAR(255),
ADD COLUMN asset_growth_yoy_unavailable_reason VARCHAR(255);

-- Migration metadata
-- This adds 42 new columns (21 value columns + 21 reason columns)
-- to support enhanced quality and growth score computations with
-- full audit trail of unavailability reasons.
