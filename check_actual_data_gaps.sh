#!/bin/bash
################################################################################
# CHECK ACTUAL DATA GAPS - See real gaps in YOUR database
#
# This script checks YOUR actual database to show:
#   1. What growth metrics you already have
#   2. Which upstream data exists
#   3. Exactly which symbols are missing what
#
# Usage: source .env.local && ./check_actual_data_gaps.sh
################################################################################

set -e

if [ -z "$DB_HOST" ]; then
    echo "❌ Database credentials not set"
    echo "Run: source .env.local"
    exit 1
fi

echo "🔍 CHECKING YOUR ACTUAL DATA GAPS"
echo "=================================="
echo ""
echo "Database: $DB_HOST:$DB_PORT / $DB_NAME"
echo "User: $DB_USER"
echo ""

# Function to run queries
query() {
    psql -h "$DB_HOST" -U "$DB_USER" -d "$DB_NAME" -t -c "$1" 2>/dev/null || echo "ERROR"
}

echo "1️⃣ GROWTH METRICS - What You Have Today"
echo "━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━"

query "
SELECT
    COUNT(*) as total_rows,
    COUNT(CASE WHEN revenue_growth_3y_cagr IS NOT NULL THEN 1 END) as revenue_growth,
    COUNT(CASE WHEN eps_growth_3y_cagr IS NOT NULL THEN 1 END) as eps_growth,
    COUNT(CASE WHEN fcf_growth_yoy IS NOT NULL THEN 1 END) as fcf_growth,
    COUNT(CASE WHEN quarterly_growth_momentum IS NOT NULL THEN 1 END) as quarterly_momentum
FROM growth_metrics
WHERE date = CURRENT_DATE;
" | awk '{
    total=$1
    rev=$2
    eps=$3
    fcf=$4
    qtr=$5
    printf "Total rows: %s\n", total
    printf "  revenue_growth_3y_cagr: %s (%.1f%%)\n", rev, (total > 0 ? rev*100/total : 0)
    printf "  eps_growth_3y_cagr: %s (%.1f%%)\n", eps, (total > 0 ? eps*100/total : 0)
    printf "  fcf_growth_yoy: %s (%.1f%%)\n", fcf, (total > 0 ? fcf*100/total : 0)
    printf "  quarterly_growth_momentum: %s (%.1f%%)\n", qtr, (total > 0 ? qtr*100/total : 0)
}'

echo ""
echo "2️⃣ UPSTREAM DATA - Which Tables Have Data"
echo "━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━"

echo ""
echo "Annual Income Statements:"
query "SELECT COUNT(DISTINCT symbol) FROM annual_income_statement;" | xargs echo "  Symbols:"

echo "Quarterly Income Statements:"
query "SELECT COUNT(DISTINCT symbol) FROM quarterly_income_statement;" | xargs echo "  Symbols:"

echo "Annual Cash Flow:"
query "SELECT COUNT(DISTINCT symbol) FROM annual_cash_flow;" | xargs echo "  Symbols:"

echo "Annual Balance Sheet:"
query "SELECT COUNT(DISTINCT symbol) FROM annual_balance_sheet;" | xargs echo "  Symbols:"

echo "Earnings History:"
query "SELECT COUNT(DISTINCT symbol) FROM earnings_history;" | xargs echo "  Symbols:"

echo "Key Metrics (Today):"
query "SELECT COUNT(DISTINCT symbol) FROM key_metrics WHERE date = CURRENT_DATE;" | xargs echo "  Symbols:"

echo ""
echo "3️⃣ SYMBOL CATEGORIES - How Many Symbols in Each"
echo "━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━"

query "
WITH gap_categories AS (
    SELECT
        CASE
            WHEN (SELECT COUNT(*) FROM annual_income_statement WHERE annual_income_statement.symbol = ss.symbol) > 0
                THEN 'has_annual_statements'
            WHEN (SELECT COUNT(*) FROM quarterly_income_statement WHERE quarterly_income_statement.symbol = ss.symbol) > 0
                THEN 'has_quarterly_statements'
            WHEN (SELECT COUNT(*) FROM key_metrics WHERE key_metrics.symbol = ss.symbol AND date = CURRENT_DATE) > 0
                THEN 'has_key_metrics_only'
            ELSE 'no_data'
        END as category
    FROM stock_symbols ss
)
SELECT
    category,
    COUNT(*) as count,
    ROUND(100.0 * COUNT(*) / (SELECT COUNT(*) FROM stock_symbols), 1) || '%' as percentage
FROM gap_categories
GROUP BY category
ORDER BY count DESC;
" | awk '{printf "  %s: %s (%s)\n", $1, $2, $3}'

echo ""
echo "4️⃣ SPECIFIC MISSING GAPS"
echo "━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━"

echo "Symbols MISSING growth metrics entirely:"
count=$(query "
SELECT COUNT(DISTINCT s.symbol)
FROM stock_symbols s
LEFT JOIN growth_metrics gm ON s.symbol = gm.symbol AND gm.date = CURRENT_DATE
WHERE gm.symbol IS NULL
OR (
    gm.revenue_growth_3y_cagr IS NULL
    AND gm.eps_growth_3y_cagr IS NULL
    AND gm.fcf_growth_yoy IS NULL
    AND gm.quarterly_growth_momentum IS NULL
);
")
echo "  $count symbols have no growth metrics"

echo ""
echo "Symbols with PARTIAL growth metrics (some NULL, some filled):"
count=$(query "
SELECT COUNT(DISTINCT symbol)
FROM growth_metrics
WHERE date = CURRENT_DATE
AND (
    (revenue_growth_3y_cagr IS NULL AND eps_growth_3y_cagr IS NOT NULL)
    OR (revenue_growth_3y_cagr IS NOT NULL AND eps_growth_3y_cagr IS NULL)
    OR (fcf_growth_yoy IS NULL AND quarterly_growth_momentum IS NOT NULL)
);
")
echo "  $count symbols have some but not all metrics"

echo ""
echo "5️⃣ SAMPLE OF SYMBOLS MISSING DATA"
echo "━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━"

echo "Symbols with NO growth data (sample):"
query "
SELECT symbol
FROM stock_symbols s
WHERE NOT EXISTS (
    SELECT 1 FROM growth_metrics gm
    WHERE gm.symbol = s.symbol AND gm.date = CURRENT_DATE
    AND (
        gm.revenue_growth_3y_cagr IS NOT NULL
        OR gm.eps_growth_3y_cagr IS NOT NULL
        OR gm.fcf_growth_yoy IS NOT NULL
    )
)
LIMIT 20;
" | sed 's/^/  /'

echo ""
echo "6️⃣ WHAT CAN WE LOAD?"
echo "━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━"

echo "Symbols that HAVE annual statements (can load complete data):"
query "SELECT COUNT(DISTINCT symbol) FROM annual_income_statement;" | xargs echo "  "

echo "Symbols that HAVE quarterly data (can load recent growth):"
query "SELECT COUNT(DISTINCT symbol) FROM quarterly_income_statement;" | xargs echo "  "

echo "Symbols that HAVE cash flow (can load FCF metrics):"
query "SELECT COUNT(DISTINCT symbol) FROM annual_cash_flow;" | xargs echo "  "

echo "Symbols with NO upstream data at all (cannot load):"
query "
SELECT COUNT(DISTINCT s.symbol)
FROM stock_symbols s
WHERE NOT EXISTS (SELECT 1 FROM annual_income_statement WHERE symbol = s.symbol)
  AND NOT EXISTS (SELECT 1 FROM quarterly_income_statement WHERE symbol = s.symbol)
  AND NOT EXISTS (SELECT 1 FROM annual_cash_flow WHERE symbol = s.symbol)
  AND NOT EXISTS (SELECT 1 FROM annual_balance_sheet WHERE symbol = s.symbol)
  AND NOT EXISTS (SELECT 1 FROM earnings_history WHERE symbol = s.symbol)
  AND NOT EXISTS (SELECT 1 FROM key_metrics WHERE symbol = s.symbol AND date = CURRENT_DATE);
" | xargs echo "  "

echo ""
echo "================== ANALYSIS COMPLETE =================="
echo ""
echo "📊 Next Steps:"
echo "   1. Run the full data load pipeline:"
echo "      ./run_full_data_load.sh all"
echo ""
echo "   2. Run this script again after loading:"
echo "      ./check_actual_data_gaps.sh"
echo ""
echo "   3. Compare before/after to see improvement"
echo ""
