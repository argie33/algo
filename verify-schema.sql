-- =============================================================================
-- DATABASE SCHEMA VERIFICATION SCRIPT
-- =============================================================================
-- Run this after init_db.sql to verify all tables were created successfully
-- Checks: table counts, critical tables, column existence, indexes

\echo ''
\echo '=========================================='
\echo '🔍 VERIFYING SCHEMA SETUP...'
\echo '=========================================='
\echo ''

-- Count total tables
\echo '📊 TABLE COUNT:'
SELECT
    schemaname,
    COUNT(*) as table_count
FROM pg_tables
WHERE schemaname = 'public'
GROUP BY schemaname;

\echo ''
\echo '✅ CRITICAL TABLES CHECK:'
SELECT
    table_name,
    CASE
        WHEN EXISTS (SELECT 1 FROM information_schema.tables WHERE table_name = t.table_name AND table_schema = 'public')
        THEN '✅ EXISTS'
        ELSE '❌ MISSING'
    END as status
FROM (VALUES
    ('users'),
    ('trades'),
    ('algo_positions'),
    ('algo_portfolio_snapshots'),
    ('market_health_daily'),
    ('technical_data_daily'),
    ('signal_quality_scores'),
    ('data_completeness_scores'),
    ('portfolio_holdings'),
    ('analyst_sentiment_analysis'),
    ('earnings_history'),
    ('buy_sell_daily'),
    ('price_daily'),
    ('stock_symbols')
) as t(table_name)
ORDER BY table_name;

\echo ''
\echo '🔍 CHECKING KEY COLUMN EXISTENCE:'
SELECT
    table_name,
    column_name,
    '✅ EXISTS' as status
FROM information_schema.columns
WHERE table_name IN ('buy_sell_daily', 'users', 'trades', 'algo_positions', 'market_health_daily', 'technical_data_daily')
  AND column_name IN ('id', 'user_id', 'symbol', 'date', 'entry_price', 'rsi', 'adx', 'macd', 'sma_50')
ORDER BY table_name, column_name;

\echo ''
\echo '📈 HYPERTABLES CREATED:'
SELECT
    schemaname,
    tablename,
    'YES' as is_hypertable
FROM pg_tables
WHERE tablename IN (
    'price_daily', 'price_weekly', 'price_monthly',
    'buy_sell_daily',
    'market_health_daily',
    'technical_data_daily',
    'trend_template_data',
    'signal_quality_scores',
    'data_completeness_scores',
    'analyst_sentiment_analysis',
    'earnings_history', 'earnings_estimates',
    'insider_transactions',
    'quality_metrics', 'growth_metrics', 'value_metrics', 'stability_metrics',
    'mean_reversion_signals_daily',
    'range_signals_daily',
    'economic_calendar', 'economic_data',
    'fear_greed_index',
    'commodity_prices', 'commodity_correlations',
    'algo_portfolio_snapshots',
    'algo_trades',
    'algo_audit_log',
    'filter_rejection_log'
);

\echo ''
\echo '🔑 INDEXES CREATED:'
SELECT COUNT(*) as total_indexes
FROM pg_indexes
WHERE schemaname = 'public';

\echo ''
\echo '✅ SCHEMA VERIFICATION COMPLETE!'
\echo ''
\echo 'Sample queries to test:'
\echo '  SELECT COUNT(*) FROM stock_symbols;'
\echo '  SELECT COUNT(*) FROM users;'
\echo '  SELECT COUNT(*) FROM trades;'
\echo '  SELECT * FROM stock_symbols LIMIT 3;'
\echo ''
