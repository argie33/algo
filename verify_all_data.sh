#!/bin/bash

# Data verification script - checks all tables are complete and current

echo "═══════════════════════════════════════════════════════════"
echo "DATA INTEGRITY CHECK"
echo "═══════════════════════════════════════════════════════════"

psql -h localhost -U stocks -d stocks << 'SQL'
-- Check all key tables and their freshness
SELECT 
    'stock_symbols' as table_name,
    COUNT(*) as row_count,
    'Expected: 5300+' as expected
FROM stock_symbols
UNION ALL
SELECT 'etf_symbols', COUNT(*), 'Expected: 4800+' FROM etf_symbols
UNION ALL
SELECT 'price_daily', COUNT(*), 'Expected: 23M+ rows' FROM price_daily
UNION ALL
SELECT 'price_weekly', COUNT(*), 'Expected: 600K+ rows' FROM price_weekly
UNION ALL
SELECT 'price_monthly', COUNT(*), 'Expected: 880K+ rows' FROM price_monthly
UNION ALL
SELECT 'etf_price_daily', COUNT(*), 'Expected: 7M+ rows' FROM etf_price_daily
UNION ALL
SELECT 'etf_price_weekly', COUNT(*), 'Expected: 400K+ rows (NEW)' FROM etf_price_weekly
UNION ALL
SELECT 'etf_price_monthly', COUNT(*), 'Expected: 60K+ rows (NEW)' FROM etf_price_monthly
UNION ALL
SELECT 'company_profile', COUNT(*), 'Expected: 5300+' FROM company_profile
UNION ALL
SELECT 'earnings', COUNT(*), 'Expected: 50K+ (CRITICAL!)' FROM earnings
UNION ALL
SELECT 'stock_scores', COUNT(*), 'Expected: 5300+' FROM stock_scores;

-- Check data freshness (latest date in price tables)
SELECT '' as spacer;
SELECT '--- PRICE DATA FRESHNESS ---' as check;
SELECT 'price_daily max date', MAX(date) FROM price_daily;
SELECT 'etf_price_daily max date', MAX(date) FROM etf_price_daily;
SELECT 'price_weekly max date', MAX(date) FROM price_weekly;
SELECT 'price_monthly max date', MAX(date) FROM price_monthly;

-- Check for missing critical data
SELECT '' as spacer;
SELECT '--- POTENTIAL ISSUES ---' as check;
SELECT 'Stocks without scores' as issue, COUNT(*) as count 
FROM stock_symbols s 
WHERE NOT EXISTS (SELECT 1 FROM stock_scores WHERE symbol = s.symbol);
SQL

echo "═══════════════════════════════════════════════════════════"
echo "If you see LOW numbers or OLD dates above, run:"
echo "  ./run_all_loaders.sh"
echo "═══════════════════════════════════════════════════════════"
