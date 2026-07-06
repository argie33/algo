-- Migration 114: Add missing indexes on price_daily for breadth/market metrics performance
-- Issue: Breadth fetcher window function query timeouts on complex JOINs
-- Solution: Add indexes on frequently filtered columns to accelerate query planning
-- Performance Impact: 20s -> ~500ms for breadth queries (40x improvement expected)

-- Index on date (DESC) for rapid date-range filtering in breadth/technical queries
CREATE INDEX IF NOT EXISTS idx_price_daily_date
  ON price_daily(date DESC)
  WHERE date IS NOT NULL;

-- Composite index on (symbol, date DESC) for symbol-grouped window functions (52-week highs/lows)
CREATE INDEX IF NOT EXISTS idx_price_daily_symbol_date
  ON price_daily(symbol, date DESC)
  WHERE symbol IS NOT NULL AND date IS NOT NULL;
