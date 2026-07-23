-- Migration 119: Add technical indicator columns to momentum_metrics
-- Enables storing RSI, MACD, ROC, and SMA price comparisons in momentum_metrics
-- table for comprehensive momentum scoring

BEGIN;

-- Add technical indicator columns to momentum_metrics
ALTER TABLE momentum_metrics
ADD COLUMN IF NOT EXISTS rsi_14 NUMERIC(10, 2),
ADD COLUMN IF NOT EXISTS macd_line NUMERIC(10, 3),
ADD COLUMN IF NOT EXISTS macd_signal NUMERIC(10, 3),
ADD COLUMN IF NOT EXISTS price_vs_sma_50 NUMERIC(10, 2),
ADD COLUMN IF NOT EXISTS price_vs_sma_200 NUMERIC(10, 2),
ADD COLUMN IF NOT EXISTS roc_20d NUMERIC(10, 2),
ADD COLUMN IF NOT EXISTS roc_60d NUMERIC(10, 2),
ADD COLUMN IF NOT EXISTS roc_120d NUMERIC(10, 2),
ADD COLUMN IF NOT EXISTS roc_252d NUMERIC(10, 2);

-- Create index on symbol+updated_at for efficient lookups
CREATE INDEX IF NOT EXISTS idx_momentum_metrics_symbol_date ON momentum_metrics(symbol, updated_at DESC);

COMMIT;
