-- Migration: Optimize market API query performance
-- Addresses slow endpoints:
--   /api/market/sentiment (7.4s) - missing indexes on sentiment tables
--   /api/market/seasonality (8.6s) - missing indexes on seasonality tables
--   /api/market/technicals (7.8s) - suboptimal breadth join
--   /api/market/top-movers (7.5s) - missing index on stock_symbols.symbol

-- ============= SENTIMENT TABLES =============
-- AAII sentiment queries by date range (no current indexes)
CREATE INDEX IF NOT EXISTS idx_aaii_sentiment_date
ON aaii_sentiment (date DESC)
WHERE bullish IS NOT NULL;

-- NAAIM queries by date range
CREATE INDEX IF NOT EXISTS idx_naaim_date
ON naaim (date DESC)
WHERE naaim_number_mean IS NOT NULL;

-- Fear & Greed index queries by date range
CREATE INDEX IF NOT EXISTS idx_fear_greed_index_date
ON fear_greed_index (date DESC)
WHERE fear_greed_value IS NOT NULL;

-- ============= SEASONALITY TABLES =============
-- Seasonality monthly stats (currently unindexed)
CREATE INDEX IF NOT EXISTS idx_seasonality_monthly_stats_month
ON seasonality_monthly_stats (month);

-- Seasonality day-of-week (currently unindexed)
CREATE INDEX IF NOT EXISTS idx_seasonality_day_of_week_day_num
ON seasonality_day_of_week (day_num);

-- ============= STOCK SYMBOLS =============
-- Top-movers query joins on stock_symbols.symbol (currently unindexed)
CREATE INDEX IF NOT EXISTS idx_stock_symbols_symbol
ON stock_symbols (symbol)
WHERE etf IS NULL OR etf != 'Y';

-- ============= PRICE DAILY OPTIMIZATION =============
-- Breadth calculation self-joins on date (additional index for date-only filters)
CREATE INDEX IF NOT EXISTS idx_price_daily_date_symbol
ON price_daily (date DESC, symbol)
WHERE close IS NOT NULL AND symbol NOT LIKE '^%';

-- ============= ANALYZE TABLES =============
-- Update table statistics for query planner optimization
ANALYZE aaii_sentiment;
ANALYZE naaim;
ANALYZE fear_greed_index;
ANALYZE seasonality_monthly_stats;
ANALYZE seasonality_day_of_week;
ANALYZE stock_symbols;
ANALYZE price_daily;

-- Verify indexes were created
SELECT
    schemaname,
    tablename,
    indexname
FROM pg_indexes
WHERE schemaname = 'public'
  AND tablename IN (
    'aaii_sentiment', 'naaim', 'fear_greed_index',
    'seasonality_monthly_stats', 'seasonality_day_of_week',
    'stock_symbols', 'price_daily'
  )
  AND indexname LIKE 'idx_%sentiment%'
  OR indexname LIKE 'idx_%seasonality%'
  OR indexname LIKE 'idx_stock_symbols_symbol'
  OR indexname LIKE 'idx_price_daily_date_symbol'
ORDER BY tablename, indexname;
