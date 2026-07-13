-- Migration 117: Add missing columns to market_sentiment
--
-- ISSUE: Migration 066 creates market_sentiment with `CREATE TABLE IF NOT EXISTS`,
-- which is a no-op against production's already-existing object -- CREATE TABLE
-- IF NOT EXISTS never adds columns to a table that already exists. Production's
-- market_sentiment predates bullish_pct/bearish_pct/neutral_pct, and no version ever
-- had data_unavailable/reason (schema.sql's fresh-install definition also lacked them,
-- even though loaders/load_market_sentiment.py has always written to them).
--
-- Running this as a plain ALTER TABLE against production revealed production's
-- market_sentiment is actually a VIEW, not a table ("market_sentiment" is not a
-- table, composite type, or foreign table) -- undocumented drift from some earlier
-- manual/out-of-band fix, not created by anything in this repo. A view has no
-- independent storage, so it cannot hold the daily upserts loaders/load_market_sentiment.py
-- needs to write; it must be a real table. Nothing else in the codebase builds on
-- top of it (only two read-only SELECT queries reference it), so it's safe to
-- replace outright.
--
-- SYMPTOM: /api/algo/sentiment returns 503 on every request:
--   psycopg2.errors.UndefinedColumn: column "bullish_pct" does not exist
-- and the loader itself has never successfully inserted a row on production.
--
-- SOLUTION: Detect whether market_sentiment is a view (drop + recreate as a real
-- table) or a table (idempotently ALTER it) so this applies cleanly regardless of
-- which state a given environment is in.

DO $$
BEGIN
    IF EXISTS (
        SELECT 1 FROM pg_class c
        JOIN pg_namespace n ON n.oid = c.relnamespace
        WHERE c.relname = 'market_sentiment' AND n.nspname = 'public' AND c.relkind = 'v'
    ) THEN
        DROP VIEW market_sentiment CASCADE;
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
    ELSE
        ALTER TABLE market_sentiment ADD COLUMN IF NOT EXISTS bullish_pct DECIMAL(8, 2);
        ALTER TABLE market_sentiment ADD COLUMN IF NOT EXISTS bearish_pct DECIMAL(8, 2);
        ALTER TABLE market_sentiment ADD COLUMN IF NOT EXISTS neutral_pct DECIMAL(8, 2);
        ALTER TABLE market_sentiment ADD COLUMN IF NOT EXISTS data_unavailable BOOLEAN NOT NULL DEFAULT FALSE;
        ALTER TABLE market_sentiment ADD COLUMN IF NOT EXISTS reason VARCHAR(200);
    END IF;
END $$;
