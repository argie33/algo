-- Migration 1001: Add data_unavailable flags to loaders missing governance compliance
-- Date: 2026-07-04
-- Reason: GOVERNANCE.md § Data Quality requires explicit data_unavailable flag on ALL records

-- Tier 1: Core independent loaders
ALTER TABLE technical_data_daily
ADD COLUMN IF NOT EXISTS data_unavailable BOOLEAN DEFAULT FALSE,
ADD COLUMN IF NOT EXISTS reason VARCHAR(500);

ALTER TABLE economic_data
ADD COLUMN IF NOT EXISTS data_unavailable BOOLEAN DEFAULT FALSE,
ADD COLUMN IF NOT EXISTS reason VARCHAR(500);

ALTER TABLE stock_symbols
ADD COLUMN IF NOT EXISTS data_unavailable BOOLEAN DEFAULT FALSE,
ADD COLUMN IF NOT EXISTS reason VARCHAR(500);

-- Tier 2: Loaders depending on price/technical data
ALTER TABLE buy_sell_daily
ADD COLUMN IF NOT EXISTS data_unavailable BOOLEAN DEFAULT FALSE,
ADD COLUMN IF NOT EXISTS reason VARCHAR(500);

ALTER TABLE market_exposure_daily
ADD COLUMN IF NOT EXISTS data_unavailable BOOLEAN DEFAULT FALSE,
ADD COLUMN IF NOT EXISTS reason VARCHAR(500);

ALTER TABLE trend_template_data
ADD COLUMN IF NOT EXISTS data_unavailable BOOLEAN DEFAULT FALSE,
ADD COLUMN IF NOT EXISTS reason VARCHAR(500);

-- Tier 3: Signal/ranking loaders
ALTER TABLE signal_quality_scores
ADD COLUMN IF NOT EXISTS data_unavailable BOOLEAN DEFAULT FALSE,
ADD COLUMN IF NOT EXISTS reason VARCHAR(500);

ALTER TABLE sector_ranking
ADD COLUMN IF NOT EXISTS data_unavailable BOOLEAN DEFAULT FALSE,
ADD COLUMN IF NOT EXISTS reason VARCHAR(500);

-- Tier 4: Aggregator loaders
ALTER TABLE algo_metrics_daily
ADD COLUMN IF NOT EXISTS data_unavailable BOOLEAN DEFAULT FALSE,
ADD COLUMN IF NOT EXISTS reason VARCHAR(500);

-- Tier 5: SEC financial data loaders
ALTER TABLE annual_balance_sheet
ADD COLUMN IF NOT EXISTS data_unavailable BOOLEAN DEFAULT FALSE,
ADD COLUMN IF NOT EXISTS reason VARCHAR(500);

ALTER TABLE annual_income_statement
ADD COLUMN IF NOT EXISTS data_unavailable BOOLEAN DEFAULT FALSE,
ADD COLUMN IF NOT EXISTS reason VARCHAR(500);

ALTER TABLE annual_cash_flow
ADD COLUMN IF NOT EXISTS data_unavailable BOOLEAN DEFAULT FALSE,
ADD COLUMN IF NOT EXISTS reason VARCHAR(500);

-- Create indexes for efficient data_unavailable queries
CREATE INDEX IF NOT EXISTS idx_technical_data_daily_unavailable
ON technical_data_daily(data_unavailable) WHERE data_unavailable = TRUE;

CREATE INDEX IF NOT EXISTS idx_economic_data_unavailable
ON economic_data(data_unavailable) WHERE data_unavailable = TRUE;

CREATE INDEX IF NOT EXISTS idx_stock_symbols_unavailable
ON stock_symbols(data_unavailable) WHERE data_unavailable = TRUE;

CREATE INDEX IF NOT EXISTS idx_buy_sell_daily_unavailable
ON buy_sell_daily(data_unavailable) WHERE data_unavailable = TRUE;

CREATE INDEX IF NOT EXISTS idx_market_exposure_daily_unavailable
ON market_exposure_daily(data_unavailable) WHERE data_unavailable = TRUE;

CREATE INDEX IF NOT EXISTS idx_trend_template_data_unavailable
ON trend_template_data(data_unavailable) WHERE data_unavailable = TRUE;

CREATE INDEX IF NOT EXISTS idx_signal_quality_scores_unavailable
ON signal_quality_scores(data_unavailable) WHERE data_unavailable = TRUE;

CREATE INDEX IF NOT EXISTS idx_sector_ranking_unavailable
ON sector_ranking(data_unavailable) WHERE data_unavailable = TRUE;

CREATE INDEX IF NOT EXISTS idx_algo_metrics_daily_unavailable
ON algo_metrics_daily(data_unavailable) WHERE data_unavailable = TRUE;

CREATE INDEX IF NOT EXISTS idx_annual_balance_sheet_unavailable
ON annual_balance_sheet(data_unavailable) WHERE data_unavailable = TRUE;

CREATE INDEX IF NOT EXISTS idx_annual_income_statement_unavailable
ON annual_income_statement(data_unavailable) WHERE data_unavailable = TRUE;

CREATE INDEX IF NOT EXISTS idx_annual_cash_flow_unavailable
ON annual_cash_flow(data_unavailable) WHERE data_unavailable = TRUE;

-- Log migration completion
INSERT INTO schema_migrations (version, description, installed_on)
VALUES ('1001', 'Add data_unavailable columns to 12 loaders for GOVERNANCE compliance', NOW())
ON CONFLICT (version) DO NOTHING;
