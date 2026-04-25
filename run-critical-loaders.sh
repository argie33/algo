#!/bin/bash
# Run all critical data loaders to populate complete database
# Focused on high-impact loaders needed for frontend to work

set -e

echo "════════════════════════════════════════════════════════════════"
echo " CRITICAL DATA LOADER EXECUTION - $(date)"
echo "════════════════════════════════════════════════════════════════"

# Check if .env.local exists for database credentials
if [ ! -f ".env.local" ]; then
    echo "⚠️  .env.local not found. Using environment variables:"
    echo "   DB_HOST=${DB_HOST:-localhost}"
    echo "   DB_USER=${DB_USER:-stocks}"
fi

# Color codes
GREEN='\033[0;32m'
RED='\033[0;31m'
YELLOW='\033[1;33m'
NC='\033[0m' # No Color

# Track results
LOADERS_RUN=0
LOADERS_PASSED=0
LOADERS_FAILED=0
FAILED_LOADERS=""

run_loader() {
    local loader_name=$1
    local description=$2

    echo ""
    echo "────────────────────────────────────────────────────────────────"
    echo "▶ Running: $description"
    echo "  Loader: $loader_name"
    echo "────────────────────────────────────────────────────────────────"

    LOADERS_RUN=$((LOADERS_RUN + 1))

    if python3 "$loader_name" 2>&1; then
        echo -e "${GREEN}✓ PASSED${NC}: $loader_name"
        LOADERS_PASSED=$((LOADERS_PASSED + 1))
    else
        echo -e "${RED}✗ FAILED${NC}: $loader_name"
        LOADERS_FAILED=$((LOADERS_FAILED + 1))
        FAILED_LOADERS="$FAILED_LOADERS\n  - $loader_name"
    fi
}

# ════════════════════════════════════════════════════════════════════
# CRITICAL PRIORITY 1: Financial statements (for FinancialData page)
# ════════════════════════════════════════════════════════════════════
echo ""
echo -e "${YELLOW}PRIORITY 1: Financial Statements (blocks FinancialData page)${NC}"
run_loader "loadannualincomestatement.py" "Annual Income Statements (revenue, net income, EPS)"
run_loader "loadannualbalancesheet.py" "Annual Balance Sheets (assets, liabilities, equity)"
run_loader "loadannualcashflow.py" "Annual Cash Flows (operating, investing, financing)"
run_loader "loadquarterlyincomestatement.py" "Quarterly Income Statements"
run_loader "loadquarterlybalancesheet.py" "Quarterly Balance Sheets"
run_loader "loadquarterlycashflow.py" "Quarterly Cash Flows"

# ════════════════════════════════════════════════════════════════════
# PRIORITY 2: Company data (institutional, analyst, positioning)
# ════════════════════════════════════════════════════════════════════
echo ""
echo -e "${YELLOW}PRIORITY 2: Daily Company Data (positioning, analyst data)${NC}"
run_loader "loaddailycompanydata.py" "Company profiles, institutional positioning, key metrics"

# ════════════════════════════════════════════════════════════════════
# PRIORITY 3: Technical & Market Data
# ════════════════════════════════════════════════════════════════════
echo ""
echo -e "${YELLOW}PRIORITY 3: Technical & Market Data${NC}"
run_loader "loadtechnicalsdaily.py" "Technical indicators (RSI, MACD, Bollinger Bands, ATR, ADX)"
run_loader "loadanalystsentiment.py" "Analyst sentiment scores"
run_loader "loadanalystupgradedowngrade.py" "Analyst rating changes"

# ════════════════════════════════════════════════════════════════════
# PRIORITY 4: Options & Advanced Data
# ════════════════════════════════════════════════════════════════════
echo ""
echo -e "${YELLOW}PRIORITY 4: Options & Advanced Data${NC}"
run_loader "loadoptionschains.py" "Options chains (may have limited coverage due to yfinance)"

# ════════════════════════════════════════════════════════════════════
# SUMMARY
# ════════════════════════════════════════════════════════════════════
echo ""
echo "════════════════════════════════════════════════════════════════"
echo " EXECUTION SUMMARY"
echo "════════════════════════════════════════════════════════════════"
echo "Total loaders run:    $LOADERS_RUN"
echo -e "Passed:              ${GREEN}$LOADERS_PASSED${NC}"
echo -e "Failed:              ${RED}$LOADERS_FAILED${NC}"

if [ $LOADERS_FAILED -gt 0 ]; then
    echo ""
    echo -e "${RED}Failed loaders:${NC}"
    echo -e "$FAILED_LOADERS"
    echo ""
    echo "Note: Some failures may be due to API rate limiting or temporary"
    echo "outages. Consider re-running failed loaders individually."
fi

echo ""
echo "✓ Loader execution complete at $(date)"
echo ""

# Exit with error if any loader failed
if [ $LOADERS_FAILED -gt 0 ]; then
    exit 1
fi

exit 0
