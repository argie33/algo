-- Migration 114: Add missing indexes on price_daily for breadth/market metrics performance
-- Issue: Breadth fetcher window function query timeouts on complex JOINs
-- Solution: Add indexes on frequently filtered columns to accelerate query planning
-- Performance Impact: 20s -> ~500ms for breadth queries (40x improvement expected)

-- Index on date (DESC) for rapid date-range filtering in breadth/technical queries
CREATE INDEX CONCURRENTLY IF NOT EXISTS idx_price_daily_date
  ON price_daily(date DESC)
  WHERE date IS NOT NULL;

-- Composite index on (symbol, date DESC) for symbol-grouped window functions (52-week highs/lows)
CREATE INDEX CONCURRENTLY IF NOT EXISTS idx_price_daily_symbol_date
  ON price_daily(symbol, date DESC)
  WHERE symbol IS NOT NULL AND date IS NOT NULL;

-- Verify indexes were created
-- Query planner will now use these for:
-- - BreadthFetcher._compute_new_highs_lows (line 557-587): window function over symbol+date
-- - Market technical queries: date range filters
-- - Price history lookups: symbol + date range combined

SELECT indexname, tablename, schemaname
FROM pg_indexes
WHERE tablename = 'price_daily' AND indexname LIKE 'idx_price_daily%'
ORDER BY indexname;
