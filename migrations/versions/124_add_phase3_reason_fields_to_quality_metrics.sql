-- Migration 124: Add Phase 3 expansion metric reason fields
-- Adds missing _unavailable_reason columns for Phase 3 metrics that were added
-- without corresponding reason field initialization (Session 357+).
-- Fixes: https://github.com/... (scores showing "No data" without explanation)

-- These columns are needed to satisfy GOVERNANCE.md fail-fast principle:
-- Every NULL field must have an explicit _unavailable_reason explaining why.

BEGIN;

-- Add missing reason fields for Phase 3 metrics
ALTER TABLE quality_metrics
ADD COLUMN IF NOT EXISTS gross_margin_unavailable_reason VARCHAR(255),
ADD COLUMN IF NOT EXISTS roic_pct_unavailable_reason VARCHAR(255),
ADD COLUMN IF NOT EXISTS fcf_to_net_income_unavailable_reason VARCHAR(255),
ADD COLUMN IF NOT EXISTS ocf_to_net_income_unavailable_reason VARCHAR(255),
ADD COLUMN IF NOT EXISTS payout_ratio_unavailable_reason VARCHAR(255),
ADD COLUMN IF NOT EXISTS free_cash_flow_unavailable_reason VARCHAR(255),
ADD COLUMN IF NOT EXISTS operating_cash_flow_unavailable_reason VARCHAR(255),
ADD COLUMN IF NOT EXISTS total_debt_unavailable_reason VARCHAR(255),
ADD COLUMN IF NOT EXISTS total_cash_unavailable_reason VARCHAR(255),
ADD COLUMN IF NOT EXISTS cash_per_share_unavailable_reason VARCHAR(255),
ADD COLUMN IF NOT EXISTS ebitda_unavailable_reason VARCHAR(255),
ADD COLUMN IF NOT EXISTS earnings_growth_yoy_unavailable_reason VARCHAR(255),
ADD COLUMN IF NOT EXISTS revenue_growth_yoy_unavailable_reason VARCHAR(255);

-- Backfill: Set reason="missing_sec_data" for existing NULL values
-- (loader will populate correctly going forward)
UPDATE quality_metrics
SET gross_margin_unavailable_reason = 'missing_sec_data'
WHERE gross_margin IS NULL AND data_unavailable = FALSE AND gross_margin_unavailable_reason IS NULL;

UPDATE quality_metrics
SET roic_pct_unavailable_reason = 'missing_sec_data'
WHERE roic_pct IS NULL AND data_unavailable = FALSE AND roic_pct_unavailable_reason IS NULL;

UPDATE quality_metrics
SET fcf_to_net_income_unavailable_reason = 'missing_sec_data'
WHERE fcf_to_net_income IS NULL AND data_unavailable = FALSE AND fcf_to_net_income_unavailable_reason IS NULL;

UPDATE quality_metrics
SET ocf_to_net_income_unavailable_reason = 'missing_sec_data'
WHERE ocf_to_net_income IS NULL AND data_unavailable = FALSE AND ocf_to_net_income_unavailable_reason IS NULL;

UPDATE quality_metrics
SET payout_ratio_unavailable_reason = 'missing_sec_data'
WHERE payout_ratio IS NULL AND data_unavailable = FALSE AND payout_ratio_unavailable_reason IS NULL;

UPDATE quality_metrics
SET free_cash_flow_unavailable_reason = 'missing_sec_data'
WHERE free_cash_flow IS NULL AND data_unavailable = FALSE AND free_cash_flow_unavailable_reason IS NULL;

UPDATE quality_metrics
SET operating_cash_flow_unavailable_reason = 'missing_sec_data'
WHERE operating_cash_flow IS NULL AND data_unavailable = FALSE AND operating_cash_flow_unavailable_reason IS NULL;

UPDATE quality_metrics
SET total_debt_unavailable_reason = 'missing_sec_data'
WHERE total_debt IS NULL AND data_unavailable = FALSE AND total_debt_unavailable_reason IS NULL;

UPDATE quality_metrics
SET total_cash_unavailable_reason = 'missing_sec_data'
WHERE total_cash IS NULL AND data_unavailable = FALSE AND total_cash_unavailable_reason IS NULL;

UPDATE quality_metrics
SET cash_per_share_unavailable_reason = 'missing_sec_data'
WHERE cash_per_share IS NULL AND data_unavailable = FALSE AND cash_per_share_unavailable_reason IS NULL;

UPDATE quality_metrics
SET ebitda_unavailable_reason = 'missing_sec_data'
WHERE ebitda IS NULL AND data_unavailable = FALSE AND ebitda_unavailable_reason IS NULL;

UPDATE quality_metrics
SET earnings_growth_yoy_unavailable_reason = 'missing_sec_data'
WHERE earnings_growth_yoy IS NULL AND data_unavailable = FALSE AND earnings_growth_yoy_unavailable_reason IS NULL;

UPDATE quality_metrics
SET revenue_growth_yoy_unavailable_reason = 'missing_sec_data'
WHERE revenue_growth_yoy IS NULL AND data_unavailable = FALSE AND revenue_growth_yoy_unavailable_reason IS NULL;

COMMIT;
