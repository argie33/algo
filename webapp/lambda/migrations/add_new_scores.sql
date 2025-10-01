-- Add new score columns to stock_scores table
-- Migration: Add relative_strength_score, positioning_score, sentiment_score

ALTER TABLE stock_scores
ADD COLUMN IF NOT EXISTS relative_strength_score NUMERIC(5,2),
ADD COLUMN IF NOT EXISTS positioning_score NUMERIC(5,2),
ADD COLUMN IF NOT EXISTS sentiment_score NUMERIC(5,2);

-- Add indexes for the new score columns
CREATE INDEX IF NOT EXISTS idx_stock_scores_relative_strength ON stock_scores(relative_strength_score DESC);
CREATE INDEX IF NOT EXISTS idx_stock_scores_positioning ON stock_scores(positioning_score DESC);
CREATE INDEX IF NOT EXISTS idx_stock_scores_sentiment ON stock_scores(sentiment_score DESC);
