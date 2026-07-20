-- Migration 0046: Add data_unavailable columns to score tables
-- Purpose: Enable explicit marking of unavailable/incomplete factor scores

-- Add data_unavailable column to stock_scores
ALTER TABLE stock_scores
ADD COLUMN IF NOT EXISTS data_unavailable BOOLEAN DEFAULT FALSE,
ADD COLUMN IF NOT EXISTS reason VARCHAR(500);

-- Add columns to swing_trader_scores
ALTER TABLE swing_trader_scores
ADD COLUMN IF NOT EXISTS data_unavailable BOOLEAN DEFAULT FALSE,
ADD COLUMN IF NOT EXISTS unavailability_reason VARCHAR(500);

-- Create indexes for faster filtering
CREATE INDEX IF NOT EXISTS idx_stock_scores_data_unavailable
ON stock_scores(data_unavailable, symbol);

CREATE INDEX IF NOT EXISTS idx_swing_trader_scores_data_unavailable
ON swing_trader_scores(data_unavailable, symbol, date);
