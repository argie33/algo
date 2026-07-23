-- Migration 121: Expand quality_metrics with ROIC, margins, cash ratios, absolute values
-- Adds comprehensive quality factor inputs for scoring

BEGIN;

-- Add margin and profitability metrics
ALTER TABLE quality_metrics
ADD COLUMN IF NOT EXISTS gross_margin NUMERIC(10, 2),
ADD COLUMN IF NOT EXISTS ebitda_margin NUMERIC(10, 2),
ADD COLUMN IF NOT EXISTS roic_pct NUMERIC(10, 2),
ADD COLUMN IF NOT EXISTS fcf_to_net_income NUMERIC(10, 2),
ADD COLUMN IF NOT EXISTS ocf_to_net_income NUMERIC(10, 2),
ADD COLUMN IF NOT EXISTS payout_ratio NUMERIC(10, 2);

-- Add absolute dollar values
ALTER TABLE quality_metrics
ADD COLUMN IF NOT EXISTS free_cash_flow NUMERIC(15, 2),
ADD COLUMN IF NOT EXISTS operating_cash_flow NUMERIC(15, 2),
ADD COLUMN IF NOT EXISTS total_debt NUMERIC(15, 2),
ADD COLUMN IF NOT EXISTS total_cash NUMERIC(15, 2),
ADD COLUMN IF NOT EXISTS cash_per_share NUMERIC(10, 2),
ADD COLUMN IF NOT EXISTS ebitda NUMERIC(15, 2);

-- Add growth and trend metrics
ALTER TABLE quality_metrics
ADD COLUMN IF NOT EXISTS earnings_growth_yoy NUMERIC(10, 2),
ADD COLUMN IF NOT EXISTS revenue_growth_yoy NUMERIC(10, 2);

COMMIT;
