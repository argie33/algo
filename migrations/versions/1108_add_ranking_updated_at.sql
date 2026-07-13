-- Migration 1108: Add missing updated_at column to sector_ranking / industry_ranking
--
-- CONTEXT: loaders/load_sector_rankings.py's ON CONFLICT ... DO UPDATE SET
-- updated_at = NOW() has always assumed both tables have this column. Confirmed
-- missing in AWS RDS for sector_ranking (present locally) -- same class of gap as
-- migration 1107 (etf_symbols). Verified live via a fresh sector_ranking loader
-- invocation: UndefinedColumn: column "updated_at" of relation "sector_ranking" does
-- not exist. Adding to industry_ranking too since it shares the identical upsert
-- pattern and the same drift risk, even though its own failure hasn't been observed
-- yet (sector_ranking's upsert fails first in the same transaction).

ALTER TABLE sector_ranking
ADD COLUMN IF NOT EXISTS created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
ADD COLUMN IF NOT EXISTS updated_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP;

ALTER TABLE industry_ranking
ADD COLUMN IF NOT EXISTS created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
ADD COLUMN IF NOT EXISTS updated_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP;
