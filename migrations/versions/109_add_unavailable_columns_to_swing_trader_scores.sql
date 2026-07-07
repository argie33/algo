-- Migration 109: Add data_unavailable columns to swing_trader_scores if table exists
--
-- This migration only runs if swing_trader_scores table exists.
-- In fresh deployments, the table may not exist yet.

DO $$
BEGIN
    IF EXISTS (SELECT 1 FROM information_schema.tables WHERE table_schema = 'public' AND table_name = 'swing_trader_scores') THEN
        ALTER TABLE swing_trader_scores
        ADD COLUMN IF NOT EXISTS data_unavailable BOOLEAN DEFAULT FALSE;

        ALTER TABLE swing_trader_scores
        ADD COLUMN IF NOT EXISTS unavailability_reason VARCHAR(255);

        CREATE INDEX IF NOT EXISTS idx_swing_trader_scores_unavailable
        ON swing_trader_scores(symbol) WHERE data_unavailable = TRUE;

        ANALYZE swing_trader_scores;
    END IF;
END $$;
