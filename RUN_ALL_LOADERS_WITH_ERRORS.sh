#!/bin/bash

# Complete data loading script with full error reporting
# Runs all loaders in the correct order and reports any issues

cd /home/arger/algo

RED='\033[0;31m'
GREEN='\033[0;32m'
YELLOW='\033[1;33m'
BLUE='\033[0;34m'
NC='\033[0m'

echo -e "${BLUE}════════════════════════════════════════════════════════${NC}"
echo -e "${BLUE}         COMPLETE DATA LOADING - NO ERRORS MODE          ${NC}"
echo -e "${BLUE}════════════════════════════════════════════════════════${NC}"
echo ""

# Track results
LOADED=0
FAILED=0
ERRORS=""

# Function to run a loader and check for errors
run_loader() {
    local loader=$1
    local name=$2

    echo -e "${YELLOW}[$(date +%H:%M:%S)]${NC} Loading: $name..."

    # Run loader and capture output
    OUTPUT=$(python3 "$loader" 2>&1)
    EXIT_CODE=$?

    if [ $EXIT_CODE -eq 0 ]; then
        echo -e "${GREEN}✓ SUCCESS${NC}: $name"
        LOADED=$((LOADED + 1))
        # Show what was loaded
        echo "$OUTPUT" | grep -E "Loaded|inserted|created|Success" | head -3
    else
        echo -e "${RED}✗ FAILED${NC}: $name (Exit code: $EXIT_CODE)"
        FAILED=$((FAILED + 1))
        ERRORS="$ERRORS\n\n━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━\n$name ERRORS:\n$OUTPUT\n"

        # Still show first 20 lines of error
        echo "$OUTPUT" | head -20
    fi
    echo ""
}

# PHASE 1: FOUNDATION
echo -e "${BLUE}PHASE 1: FOUNDATION DATA${NC}"
echo "━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━"
run_loader "loadstocksymbols.py" "Stock Symbols"

# PHASE 2: CORE DATA FOR SCORES/SIGNALS
echo ""
echo -e "${BLUE}PHASE 2: CORE DATA (For Scores & Signals)${NC}"
echo "━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━"

run_loader "loadpricedaily.py" "Daily Prices"
run_loader "loaddailycompanydata.py" "Daily Company Data"
run_loader "loadfundamentalmetrics.py" "Fundamental Metrics"
run_loader "loadtechnicalindicators.py" "Technical Indicators"
run_loader "loadbuysellDaily.py" "Buy/Sell Signals (Daily)"
run_loader "loadbuysellweekly.py" "Buy/Sell Signals (Weekly)"
run_loader "loadbuysellmonthly.py" "Buy/Sell Signals (Monthly)"
run_loader "loadstockscores.py" "Stock Scores"

# PHASE 3: ADDITIONAL DATA
echo ""
echo -e "${BLUE}PHASE 3: ADDITIONAL DATA (Optional)${NC}"
echo "━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━"

run_loader "loadannualincomestatement.py" "Annual Income Statement"
run_loader "loadannualbalancesheet.py" "Annual Balance Sheet"
run_loader "loadannualcashflow.py" "Annual Cash Flow"
run_loader "loadquarterlyincomestatement.py" "Quarterly Income Statement"
run_loader "loadquarterlybalancesheet.py" "Quarterly Balance Sheet"
run_loader "loadquarterlycashflow.py" "Quarterly Cash Flow"
run_loader "loadearningshistory.py" "Earnings History"
run_loader "loadearningsrevisions.py" "Earnings Revisions"
run_loader "loadearningssurprise.py" "Earnings Surprise"
run_loader "loadanalystsentiment.py" "Analyst Sentiment"
run_loader "loadanalystupgradedowngrade.py" "Analyst Upgrade/Downgrade"
run_loader "loadetfpricedaily.py" "ETF Price (Daily)"
run_loader "loadetfpriceweekly.py" "ETF Price (Weekly)"
run_loader "loadetfpricemonthly.py" "ETF Price (Monthly)"
run_loader "loadsentiment.py" "News Sentiment"
run_loader "loadnews.py" "News"
run_loader "loadoptionschains.py" "Options Chains"
run_loader "loadseasonality.py" "Seasonality"
run_loader "loadrelativeperformance.py" "Relative Performance"

# SUMMARY
echo ""
echo -e "${BLUE}════════════════════════════════════════════════════════${NC}"
echo -e "${BLUE}                    LOADING SUMMARY                      ${NC}"
echo -e "${BLUE}════════════════════════════════════════════════════════${NC}"
echo ""
echo -e "${GREEN}✓ Successful: $LOADED${NC}"
echo -e "${RED}✗ Failed: $FAILED${NC}"
echo ""

if [ $FAILED -gt 0 ]; then
    echo -e "${RED}━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━${NC}"
    echo -e "${RED}ERRORS FOUND:${NC}"
    echo -e "${RED}━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━${NC}"
    echo -e "$ERRORS"
else
    echo -e "${GREEN}✓ NO ERRORS - ALL DATA LOADED SUCCESSFULLY!${NC}"
fi

# Verify data in database
echo ""
echo -e "${BLUE}DATABASE VERIFICATION:${NC}"
PGPASSWORD=bed0elAn psql -h localhost -U stocks -d stocks -c "
SELECT
    (SELECT COUNT(*) FROM stock_symbols) as stocks,
    (SELECT COUNT(*) FROM price_daily) as prices,
    (SELECT COUNT(*) FROM fundamental_metrics) as metrics,
    (SELECT COUNT(*) FROM stock_scores) as scores,
    (SELECT COUNT(*) FROM buy_sell_daily) as signals;
" 2>/dev/null || echo "Database not accessible"

echo ""
if [ $FAILED -eq 0 ]; then
    echo -e "${GREEN}✅ COMPLETE SUCCESS - ALL DATA LOADED, NO ERRORS!${NC}"
else
    echo -e "${RED}⚠️  SOME LOADERS FAILED - CHECK ERRORS ABOVE${NC}"
fi

echo -e "${BLUE}════════════════════════════════════════════════════════${NC}"
