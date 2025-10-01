-- Migration: Add new score columns to stock_scores table
-- Safe to run multiple times (uses IF NOT EXISTS and ALTER TABLE IF NOT EXISTS syntax)
-- Adds: relative_strength_score, positioning_score, sentiment_score

DO $$
BEGIN
    -- Add relative_strength_score column if it doesn't exist
    IF NOT EXISTS (
        SELECT 1 FROM information_schema.columns
        WHERE table_name='stock_scores' AND column_name='relative_strength_score'
    ) THEN
        ALTER TABLE stock_scores ADD COLUMN relative_strength_score NUMERIC(5,2);
        RAISE NOTICE 'Added relative_strength_score column';
    ELSE
        RAISE NOTICE 'relative_strength_score column already exists';
    END IF;

    -- Add positioning_score column if it doesn't exist
    IF NOT EXISTS (
        SELECT 1 FROM information_schema.columns
        WHERE table_name='stock_scores' AND column_name='positioning_score'
    ) THEN
        ALTER TABLE stock_scores ADD COLUMN positioning_score NUMERIC(5,2);
        RAISE NOTICE 'Added positioning_score column';
    ELSE
        RAISE NOTICE 'positioning_score column already exists';
    END IF;

    -- Add sentiment_score column if it doesn't exist
    IF NOT EXISTS (
        SELECT 1 FROM information_schema.columns
        WHERE table_name='stock_scores' AND column_name='sentiment_score'
    ) THEN
        ALTER TABLE stock_scores ADD COLUMN sentiment_score NUMERIC(5,2);
        RAISE NOTICE 'Added sentiment_score column';
    ELSE
        RAISE NOTICE 'sentiment_score column already exists';
    END IF;
END
$$;

-- Create indexes for new columns (will fail silently if they exist)
CREATE INDEX IF NOT EXISTS idx_stock_scores_relative_strength ON stock_scores(relative_strength_score DESC);
CREATE INDEX IF NOT EXISTS idx_stock_scores_positioning ON stock_scores(positioning_score DESC);
CREATE INDEX IF NOT EXISTS idx_stock_scores_sentiment ON stock_scores(sentiment_score DESC);

-- Set default values for existing rows
UPDATE stock_scores
SET
    relative_strength_score = COALESCE(relative_strength_score, 75.0),
    positioning_score = COALESCE(positioning_score, 70.0),
    sentiment_score = COALESCE(sentiment_score, 65.0);

-- Verify the changes
SELECT
    column_name,
    data_type,
    is_nullable
FROM information_schema.columns
WHERE table_name = 'stock_scores'
    AND column_name IN ('relative_strength_score', 'positioning_score', 'sentiment_score')
ORDER BY column_name;

-- Show sample data
SELECT
    symbol,
    composite_score,
    relative_strength_score,
    positioning_score,
    sentiment_score
FROM stock_scores
LIMIT 5;
