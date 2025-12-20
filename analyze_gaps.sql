-- Growth Metrics Gap Analysis - Direct SQL
-- Run this with: psql stocks < analyze_gaps.sql
-- Or: psql -h localhost -U stocks -d stocks -f analyze_gaps.sql

\echo '==================== GROWTH METRICS GAP ANALYSIS ===================='
\echo ''

-- 1. Total Universe
\echo '📊 TOTAL SYMBOLS IN DATABASE'
\echo '────────────────────────────────────────'
SELECT COUNT(*) as total_symbols FROM stock_symbols;
\echo ''

-- 2. Growth Metrics Coverage
\echo '📈 GROWTH METRICS COVERAGE (TODAY)'
\echo '────────────────────────────────────────'
WITH today_metrics AS (
    SELECT
        'revenue_growth_3y_cagr' as metric,
        COUNT(*) as total_rows,
        COUNT(CASE WHEN revenue_growth_3y_cagr IS NOT NULL THEN 1 END) as non_null,
        ROUND(100.0 * COUNT(CASE WHEN revenue_growth_3y_cagr IS NOT NULL THEN 1 END) / COUNT(*), 1) as coverage_pct
    FROM growth_metrics
    WHERE date = CURRENT_DATE
    UNION ALL
    SELECT
        'eps_growth_3y_cagr',
        COUNT(*),
        COUNT(CASE WHEN eps_growth_3y_cagr IS NOT NULL THEN 1 END),
        ROUND(100.0 * COUNT(CASE WHEN eps_growth_3y_cagr IS NOT NULL THEN 1 END) / COUNT(*), 1)
    FROM growth_metrics
    WHERE date = CURRENT_DATE
    UNION ALL
    SELECT
        'operating_income_growth_yoy',
        COUNT(*),
        COUNT(CASE WHEN operating_income_growth_yoy IS NOT NULL THEN 1 END),
        ROUND(100.0 * COUNT(CASE WHEN operating_income_growth_yoy IS NOT NULL THEN 1 END) / COUNT(*), 1)
    FROM growth_metrics
    WHERE date = CURRENT_DATE
    UNION ALL
    SELECT
        'fcf_growth_yoy',
        COUNT(*),
        COUNT(CASE WHEN fcf_growth_yoy IS NOT NULL THEN 1 END),
        ROUND(100.0 * COUNT(CASE WHEN fcf_growth_yoy IS NOT NULL THEN 1 END) / COUNT(*), 1)
    FROM growth_metrics
    WHERE date = CURRENT_DATE
    UNION ALL
    SELECT
        'net_income_growth_yoy',
        COUNT(*),
        COUNT(CASE WHEN net_income_growth_yoy IS NOT NULL THEN 1 END),
        ROUND(100.0 * COUNT(CASE WHEN net_income_growth_yoy IS NOT NULL THEN 1 END) / COUNT(*), 1)
    FROM growth_metrics
    WHERE date = CURRENT_DATE
    UNION ALL
    SELECT
        'quarterly_growth_momentum',
        COUNT(*),
        COUNT(CASE WHEN quarterly_growth_momentum IS NOT NULL THEN 1 END),
        ROUND(100.0 * COUNT(CASE WHEN quarterly_growth_momentum IS NOT NULL THEN 1 END) / COUNT(*), 1)
    FROM growth_metrics
    WHERE date = CURRENT_DATE
)
SELECT
    metric,
    non_null || '/' || total_rows as "rows_with_data",
    coverage_pct || '%' as coverage
FROM today_metrics
ORDER BY coverage_pct DESC;
\echo ''

-- 3. Upstream Data Sources
\echo '📦 UPSTREAM DATA SOURCE COVERAGE'
\echo '────────────────────────────────────────'
SELECT
    'annual_income_statement' as data_source,
    COUNT(DISTINCT symbol) as symbols_with_data,
    ROUND(100.0 * COUNT(DISTINCT symbol) / (SELECT COUNT(*) FROM stock_symbols), 1) || '%' as coverage
FROM annual_income_statement
UNION ALL
SELECT
    'quarterly_income_statement',
    COUNT(DISTINCT symbol),
    ROUND(100.0 * COUNT(DISTINCT symbol) / (SELECT COUNT(*) FROM stock_symbols), 1) || '%'
FROM quarterly_income_statement
UNION ALL
SELECT
    'annual_cash_flow',
    COUNT(DISTINCT symbol),
    ROUND(100.0 * COUNT(DISTINCT symbol) / (SELECT COUNT(*) FROM stock_symbols), 1) || '%'
FROM annual_cash_flow
UNION ALL
SELECT
    'annual_balance_sheet',
    COUNT(DISTINCT symbol),
    ROUND(100.0 * COUNT(DISTINCT symbol) / (SELECT COUNT(*) FROM stock_symbols), 1) || '%'
FROM annual_balance_sheet
UNION ALL
SELECT
    'earnings_history',
    COUNT(DISTINCT symbol),
    ROUND(100.0 * COUNT(DISTINCT symbol) / (SELECT COUNT(*) FROM stock_symbols), 1) || '%'
FROM earnings_history
UNION ALL
SELECT
    'key_metrics (today)',
    COUNT(DISTINCT symbol),
    ROUND(100.0 * COUNT(DISTINCT symbol) / (SELECT COUNT(*) FROM stock_symbols), 1) || '%'
FROM key_metrics
WHERE date = CURRENT_DATE
ORDER BY coverage DESC;
\echo ''

-- 4. Gap Categories
\echo '🔍 DATA GAP CATEGORIES'
\echo '────────────────────────────────────────'
WITH gap_analysis AS (
    SELECT
        CASE
            WHEN (SELECT COUNT(*) FROM annual_income_statement WHERE annual_income_statement.symbol = ss.symbol) > 0
                THEN 'has_annual_statements'
            WHEN (SELECT COUNT(*) FROM quarterly_income_statement WHERE quarterly_income_statement.symbol = ss.symbol) > 0
                THEN 'has_quarterly_statements'
            WHEN (SELECT COUNT(*) FROM key_metrics WHERE key_metrics.symbol = ss.symbol AND date = CURRENT_DATE) > 0
                THEN 'has_key_metrics_only'
            ELSE 'no_data'
        END as gap_category
    FROM stock_symbols ss
)
SELECT
    gap_category,
    COUNT(*) as symbol_count,
    ROUND(100.0 * COUNT(*) / (SELECT COUNT(*) FROM stock_symbols), 1) || '%' as percentage
FROM gap_analysis
GROUP BY gap_category
ORDER BY symbol_count DESC;
\echo ''

-- 5. Symbols Missing Growth Metrics
\echo '📋 SYMBOLS WITH INCOMPLETE GROWTH METRICS'
\echo '────────────────────────────────────────'
\echo 'Sample of symbols missing most growth metrics:'
SELECT DISTINCT s.symbol
FROM stock_symbols s
LEFT JOIN growth_metrics gm ON s.symbol = gm.symbol AND gm.date = CURRENT_DATE
WHERE NOT EXISTS (
    SELECT 1 FROM growth_metrics gm2
    WHERE gm2.symbol = s.symbol
    AND gm2.date = CURRENT_DATE
    AND (
        gm2.revenue_growth_3y_cagr IS NOT NULL
        OR gm2.eps_growth_3y_cagr IS NOT NULL
        OR gm2.fcf_growth_yoy IS NOT NULL
    )
)
LIMIT 20;
\echo ''

-- 6. Summary Stats
\echo '📊 SUMMARY STATISTICS'
\echo '────────────────────────────────────────'
SELECT
    (SELECT COUNT(*) FROM stock_symbols) as total_symbols,
    (SELECT COUNT(*) FROM annual_income_statement)::text as annual_statements,
    (SELECT COUNT(*) FROM quarterly_income_statement)::text as quarterly_statements,
    (SELECT COUNT(*) FROM growth_metrics WHERE date = CURRENT_DATE)::text as growth_metrics_rows,
    (SELECT COUNT(CASE WHEN revenue_growth_3y_cagr IS NOT NULL THEN 1 END) FROM growth_metrics WHERE date = CURRENT_DATE)::text as metrics_with_revenue_growth;
\echo ''

\echo '✅ Analysis complete!'
\echo '==================== END ANALYSIS ===================='
