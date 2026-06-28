-- Migration 060: Add covering index on price_daily for 52-week stats aggregation
-- The deep-value endpoint aggregates MAX(high) and MIN(low) over 52 weeks for ~5000 symbols.
-- Without this index, PostgreSQL must fetch high/low from the heap for each row.
-- INCLUDE(high, low, close) makes this an index-only scan.
CREATE INDEX IF NOT EXISTS idx_price_daily_symbol_date_cover
    ON price_daily(symbol, date DESC)
    INCLUDE (high, low, close);
