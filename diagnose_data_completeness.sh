#!/bin/bash
################################################################################
# DATA COMPLETENESS DIAGNOSTIC
#
# Checks EVERY table to show:
#   1. What data exists
#   2. What's completely missing
#   3. Which loaders to run
#
# Usage: source .env.local && bash diagnose_data_completeness.sh
################################################################################

set -e

if [ -z "$DB_HOST" ]; then
    echo "❌ Database not configured"
    echo "Run: source .env.local"
    exit 1
fi

RED='\033[0;31m'
GREEN='\033[0;32m'
YELLOW='\033[1;33m'
NC='\033[0m'

echo ""
echo "🔍 COMPREHENSIVE DATA DIAGNOSTIC"
echo "================================"
echo "Database: $DB_HOST:$DB_PORT / $DB_NAME"
echo ""

# Function to safely query
safe_query() {
    psql -h "$DB_HOST" -U "$DB_USER" -d "$DB_NAME" -t -c "$1" 2>/dev/null || echo "ERROR"
}

# Function to get row count
count_table() {
    local table=$1
    local where=${2:-""}
    if [ -z "$where" ]; then
        safe_query "SELECT COUNT(*) FROM $table LIMIT 1;" | tr -d ' '
    else
        safe_query "SELECT COUNT(*) FROM $table WHERE $where LIMIT 1;" | tr -d ' '
    fi
}

# Function to get distinct symbol count
symbol_count() {
    local table=$1
    local where=${2:-""}
    if [ -z "$where" ]; then
        safe_query "SELECT COUNT(DISTINCT symbol) FROM $table LIMIT 1;" | tr -d ' '
    else
        safe_query "SELECT COUNT(DISTINCT symbol) FROM $table WHERE $where LIMIT 1;" | tr -d ' '
    fi
}

print_status() {
    local count=$1
    local max=$2
    if [ "$count" = "ERROR" ]; then
        echo -e "${RED}❌ ERROR${NC}"
    elif [ "$count" -eq 0 ]; then
        echo -e "${RED}❌ EMPTY${NC} (0 rows)"
    else
        local pct=$((count * 100 / max))
        if [ "$pct" -gt 80 ]; then
            echo -e "${GREEN}✅ LOADED${NC} ($count / $max, $pct%)"
        elif [ "$pct" -gt 30 ]; then
            echo -e "${YELLOW}⚠️  PARTIAL${NC} ($count / $max, $pct%)"
        else
            echo -e "${RED}❌ SPARSE${NC} ($count / $max, $pct%)"
        fi
    fi
}

# Get total symbol count
total_symbols=$(count_table "stock_symbols")
echo "Total symbols in database: $total_symbols"
echo ""

echo "════════════════════════════════════════════════════════════════"
echo "📊 FINANCIAL STATEMENTS"
echo "════════════════════════════════════════════════════════════════"

echo ""
echo "1. ANNUAL INCOME STATEMENTS (revenue, net income, operating income)"
count=$(symbol_count "annual_income_statement")
echo "   Symbols: $count / $total_symbols"
print_status "$count" "$total_symbols"
row_count=$(count_table "annual_income_statement")
echo "   Rows: $row_count"
echo ""

echo "2. QUARTERLY INCOME STATEMENTS (recent quarterly data)"
count=$(symbol_count "quarterly_income_statement")
echo "   Symbols: $count / $total_symbols"
print_status "$count" "$total_symbols"
row_count=$(count_table "quarterly_income_statement")
echo "   Rows: $row_count"
echo ""

echo "3. ANNUAL CASH FLOW (FCF, operating cash flow)"
count=$(symbol_count "annual_cash_flow")
echo "   Symbols: $count / $total_symbols"
print_status "$count" "$total_symbols"
row_count=$(count_table "annual_cash_flow")
echo "   Rows: $row_count"
echo ""

echo "4. ANNUAL BALANCE SHEET (total assets, equity)"
count=$(symbol_count "annual_balance_sheet")
echo "   Symbols: $count / $total_symbols"
print_status "$count" "$total_symbols"
row_count=$(count_table "annual_balance_sheet")
echo "   Rows: $row_count"
echo ""

echo "════════════════════════════════════════════════════════════════"
echo "📈 EARNINGS & KEY METRICS"
echo "════════════════════════════════════════════════════════════════"

echo ""
echo "5. EARNINGS HISTORY (EPS actual vs estimate)"
count=$(symbol_count "earnings_history")
echo "   Symbols: $count / $total_symbols"
print_status "$count" "$total_symbols"
row_count=$(count_table "earnings_history")
echo "   Rows: $row_count"
echo ""

echo "6. KEY METRICS - TODAY"
count=$(symbol_count "key_metrics" "date = CURRENT_DATE")
echo "   Symbols: $count / $total_symbols"
print_status "$count" "$total_symbols"
row_count=$(count_table "key_metrics" "date = CURRENT_DATE")
echo "   Rows: $row_count"
echo ""

echo "════════════════════════════════════════════════════════════════"
echo "📊 CALCULATED METRICS"
echo "════════════════════════════════════════════════════════════════"

echo ""
echo "7. GROWTH METRICS - TODAY"
count=$(symbol_count "growth_metrics" "date = CURRENT_DATE")
echo "   Symbols: $count / $total_symbols"
print_status "$count" "$total_symbols"
row_count=$(count_table "growth_metrics" "date = CURRENT_DATE")
echo "   Rows: $row_count"
if [ "$count" != "ERROR" ] && [ "$count" -gt 0 ]; then
    echo ""
    echo "   Coverage by metric:"
    safe_query "
    SELECT
        'revenue_growth' as metric, COUNT(CASE WHEN revenue_growth_3y_cagr IS NOT NULL THEN 1 END)::text as count
    FROM growth_metrics WHERE date = CURRENT_DATE
    UNION ALL
    SELECT 'eps_growth', COUNT(CASE WHEN eps_growth_3y_cagr IS NOT NULL THEN 1 END)::text
    FROM growth_metrics WHERE date = CURRENT_DATE
    UNION ALL
    SELECT 'fcf_growth', COUNT(CASE WHEN fcf_growth_yoy IS NOT NULL THEN 1 END)::text
    FROM growth_metrics WHERE date = CURRENT_DATE
    UNION ALL
    SELECT 'quarterly_momentum', COUNT(CASE WHEN quarterly_growth_momentum IS NOT NULL THEN 1 END)::text
    FROM growth_metrics WHERE date = CURRENT_DATE;
    " | while read metric count; do
        pct=$((count * 100 / total_symbols))
        printf "     %s: %s symbols (%d%%)\n" "$metric" "$count" "$pct"
    done
fi
echo ""

echo "8. QUALITY METRICS - TODAY"
count=$(symbol_count "quality_metrics" "date = CURRENT_DATE")
echo "   Symbols: $count / $total_symbols"
print_status "$count" "$total_symbols"
row_count=$(count_table "quality_metrics" "date = CURRENT_DATE")
echo "   Rows: $row_count"
echo ""

echo "9. MOMENTUM METRICS - TODAY"
count=$(symbol_count "momentum_metrics" "date = CURRENT_DATE")
echo "   Symbols: $count / $total_symbols"
print_status "$count" "$total_symbols"
row_count=$(count_table "momentum_metrics" "date = CURRENT_DATE")
echo "   Rows: $row_count"
echo ""

echo "════════════════════════════════════════════════════════════════"
echo "🎯 RECOMMENDATIONS"
echo "════════════════════════════════════════════════════════════════"
echo ""

# Check what's missing and recommend loaders
echo "MISSING DATA ANALYSIS:"
echo ""

annual_stmts=$(symbol_count "annual_income_statement")
if [ "$annual_stmts" -lt 1000 ]; then
    echo "  ❌ Annual Income Statements: MISSING"
    echo "     → Run: python3 loadannualincomestatement.py"
    echo ""
fi

quarterly_stmts=$(symbol_count "quarterly_income_statement")
if [ "$quarterly_stmts" -lt 1000 ]; then
    echo "  ❌ Quarterly Income Statements: MISSING"
    echo "     → Run: python3 loadquarterlyincomestatement.py"
    echo ""
fi

cash_flow=$(symbol_count "annual_cash_flow")
if [ "$cash_flow" -lt 1000 ]; then
    echo "  ❌ Annual Cash Flow: MISSING"
    echo "     → Run: python3 loadannualcashflow.py"
    echo ""
fi

balance_sheet=$(symbol_count "annual_balance_sheet")
if [ "$balance_sheet" -lt 1000 ]; then
    echo "  ❌ Annual Balance Sheet: MISSING"
    echo "     → Run: python3 loadannualbalancesheet.py"
    echo ""
fi

earnings_hist=$(symbol_count "earnings_history")
if [ "$earnings_hist" -lt 1000 ]; then
    echo "  ❌ Earnings History: MISSING"
    echo "     → Run: python3 loadearningshistory.py"
    echo ""
fi

key_metrics=$(symbol_count "key_metrics" "date = CURRENT_DATE")
if [ "$key_metrics" -lt 1000 ]; then
    echo "  ❌ Key Metrics: MISSING/STALE"
    echo "     → Run: python3 loaddailycompanydata.py"
    echo ""
fi

growth_metrics=$(symbol_count "growth_metrics" "date = CURRENT_DATE")
if [ "$growth_metrics" -lt $((total_symbols / 2)) ]; then
    echo "  ❌ Growth Metrics: INCOMPLETE"
    echo "     → Run: python3 loadfactormetrics.py"
    echo ""
fi

echo ""
echo "════════════════════════════════════════════════════════════════"
echo "✅ ACTION PLAN"
echo "════════════════════════════════════════════════════════════════"
echo ""
echo "1. Check which loaders are recommended above"
echo "2. Run them in this order:"
echo "   a) loaddailycompanydata.py (key_metrics - fastest)"
echo "   b) loadannualincomestatement.py"
echo "   c) loadquarterlyincomestatement.py"
echo "   d) loadannualcashflow.py"
echo "   e) loadannualbalancesheet.py"
echo "   f) loadearningshistory.py"
echo "   g) loadfactormetrics.py (uses all the above data)"
echo ""
echo "3. To run all growth metrics calculation:"
echo "   python3 loadfactormetrics.py"
echo ""
echo "4. Then re-run this diagnostic to verify improvement:"
echo "   bash diagnose_data_completeness.sh"
echo ""
