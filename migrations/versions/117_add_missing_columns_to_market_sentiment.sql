-- Migration 117: Add missing columns to market_sentiment
--
-- ISSUE: Migration 066 creates market_sentiment with `CREATE TABLE IF NOT EXISTS`,
-- which is a no-op against production's older, already-existing table -- CREATE TABLE
-- IF NOT EXISTS never adds columns to a table that already exists. Production's
-- market_sentiment predates bullish_pct/bearish_pct/neutral_pct, and no table ever
-- had data_unavailable/reason (schema.sql's fresh-install definition also lacks them,
-- even though loaders/load_market_sentiment.py has always written to them).
--
-- SYMPTOM: /api/algo/sentiment returns 503 on every request:
--   psycopg2.errors.UndefinedColumn: column "bullish_pct" does not exist
-- and the loader itself has never successfully inserted a row on production.
--
-- SOLUTION: Idempotently ALTER the existing table instead of relying on CREATE TABLE.

ALTER TABLE market_sentiment ADD COLUMN IF NOT EXISTS bullish_pct DECIMAL(8, 2);
ALTER TABLE market_sentiment ADD COLUMN IF NOT EXISTS bearish_pct DECIMAL(8, 2);
ALTER TABLE market_sentiment ADD COLUMN IF NOT EXISTS neutral_pct DECIMAL(8, 2);
ALTER TABLE market_sentiment ADD COLUMN IF NOT EXISTS data_unavailable BOOLEAN NOT NULL DEFAULT FALSE;
ALTER TABLE market_sentiment ADD COLUMN IF NOT EXISTS reason VARCHAR(200);
