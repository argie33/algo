#!/bin/bash
# Script to fix stock_scores table by adding new columns
# Run with: sudo bash fix_stock_scores_table.sh

echo "Fixing stock_scores table..."

# Run as postgres user via sudo
sudo -u postgres psql -d stocks << 'PGSQL'
-- Drop the temporary table
DROP TABLE IF EXISTS stock_scores_new CASCADE;

-- Add new columns to original table
ALTER TABLE stock_scores
ADD COLUMN IF NOT EXISTS relative_strength_score NUMERIC(5,2) DEFAULT 75.0,
ADD COLUMN IF NOT EXISTS positioning_score NUMERIC(5,2) DEFAULT 70.0,
ADD COLUMN IF NOT EXISTS sentiment_score NUMERIC(5,2) DEFAULT 65.0;

-- Create indexes
CREATE INDEX IF NOT EXISTS idx_stock_scores_relative_strength ON stock_scores(relative_strength_score DESC);
CREATE INDEX IF NOT EXISTS idx_stock_scores_positioning ON stock_scores(positioning_score DESC);
CREATE INDEX IF NOT EXISTS idx_stock_scores_sentiment ON stock_scores(sentiment_score DESC);

-- Show result
SELECT column_name, data_type
FROM information_schema.columns
WHERE table_name='stock_scores'
AND column_name IN ('relative_strength_score', 'positioning_score', 'sentiment_score')
ORDER BY column_name;

PGSQL

echo "✅ Done! Run this script with: sudo bash fix_stock_scores_table.sh"
