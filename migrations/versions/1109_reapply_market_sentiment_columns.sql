-- Migration 1109: Re-apply market_sentiment column fix (117 was marked applied but never took effect)
--
-- ISSUE: Migration 117 (add_missing_columns_to_market_sentiment) is recorded in
-- schema_version as applied, but production's market_sentiment table is still missing
-- bullish_pct/bearish_pct/neutral_pct -- /api/algo/sentiment has been returning 503
-- "Database schema issue" (psycopg2.errors.UndefinedColumn: column "bullish_pct" does
-- not exist) continuously in production as of 2026-07-13.
--
-- The migration runner tracks applied migrations by filename/version only, never by
-- content hash. Migration 117's SQL was edited in-place after an earlier attempt was
-- recorded as applied (see that file's "UPDATE (2026-07-13)" comment about handling
-- materialized views), so the corrected DO block has never actually executed against
-- production. Rather than fight the historical schema_version record, this migration
-- re-applies the same fix under a new version so it is guaranteed to run.
--
-- Idempotent regardless of current state (view, materialized view, table missing
-- columns, or table already correct).

DO $$
DECLARE
    kind CHAR;
BEGIN
    SELECT c.relkind INTO kind
    FROM pg_class c
    JOIN pg_namespace n ON n.oid = c.relnamespace
    WHERE c.relname = 'market_sentiment' AND n.nspname = 'public';

    IF kind IN ('v', 'm') THEN
        IF kind = 'v' THEN
            DROP VIEW market_sentiment CASCADE;
        ELSE
            DROP MATERIALIZED VIEW market_sentiment CASCADE;
        END IF;
        CREATE TABLE market_sentiment (
            id SERIAL PRIMARY KEY,
            date DATE NOT NULL UNIQUE,
            fear_greed_index DECIMAL(8, 4),
            put_call_ratio DECIMAL(8, 4),
            vix DECIMAL(8, 4),
            sentiment_score DECIMAL(8, 4),
            bullish_pct DECIMAL(8, 2),
            bearish_pct DECIMAL(8, 2),
            neutral_pct DECIMAL(8, 2),
            data_unavailable BOOLEAN NOT NULL DEFAULT FALSE,
            reason VARCHAR(200),
            created_at TIMESTAMP WITH TIME ZONE DEFAULT CURRENT_TIMESTAMP
        );
        CREATE INDEX IF NOT EXISTS idx_market_sentiment_date ON market_sentiment(date DESC);
    ELSIF kind = 'r' THEN
        ALTER TABLE market_sentiment ADD COLUMN IF NOT EXISTS bullish_pct DECIMAL(8, 2);
        ALTER TABLE market_sentiment ADD COLUMN IF NOT EXISTS bearish_pct DECIMAL(8, 2);
        ALTER TABLE market_sentiment ADD COLUMN IF NOT EXISTS neutral_pct DECIMAL(8, 2);
        ALTER TABLE market_sentiment ADD COLUMN IF NOT EXISTS data_unavailable BOOLEAN NOT NULL DEFAULT FALSE;
        ALTER TABLE market_sentiment ADD COLUMN IF NOT EXISTS reason VARCHAR(200);
    ELSE
        CREATE TABLE market_sentiment (
            id SERIAL PRIMARY KEY,
            date DATE NOT NULL UNIQUE,
            fear_greed_index DECIMAL(8, 4),
            put_call_ratio DECIMAL(8, 4),
            vix DECIMAL(8, 4),
            sentiment_score DECIMAL(8, 4),
            bullish_pct DECIMAL(8, 2),
            bearish_pct DECIMAL(8, 2),
            neutral_pct DECIMAL(8, 2),
            data_unavailable BOOLEAN NOT NULL DEFAULT FALSE,
            reason VARCHAR(200),
            created_at TIMESTAMP WITH TIME ZONE DEFAULT CURRENT_TIMESTAMP
        );
        CREATE INDEX IF NOT EXISTS idx_market_sentiment_date ON market_sentiment(date DESC);
    END IF;
END $$;
