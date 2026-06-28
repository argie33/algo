-- Migration 062: Add active column to stock_symbols
-- Column was added to schema.sql CREATE TABLE definition but was never applied
-- as a versioned migration, so existing databases are missing it.
-- get_active_symbols() in utils/loaders/helpers.py queries WHERE active = true,
-- which fails with UndefinedColumn until this migration runs.

ALTER TABLE stock_symbols ADD COLUMN IF NOT EXISTS active BOOLEAN DEFAULT TRUE;
CREATE INDEX IF NOT EXISTS idx_stock_symbols_active ON stock_symbols(active);
