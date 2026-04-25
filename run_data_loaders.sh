#!/bin/bash

# ═══════════════════════════════════════════════════════════════════════════════
# MASTER DATA LOADER SCRIPT - Runs all critical loaders in priority order
#
# Usage: bash run_data_loaders.sh [tier1|tier2|tier3|all|quick]
#   tier1  - Foundational only (stock symbols, prices, company data)
#   tier2  - Add trading signals and metrics
#   tier3  - Add financial statements
#   all    - Run everything (slow!)
#   quick  - Tier 1+2 (fast, gets you most data)
# ═══════════════════════════════════════════════════════════════════════════════

set -e

# Colors for output
GREEN='\033[0;32m'
YELLOW='\033[1;33m'
RED='\033[0;31m'
BLUE='\033[0;34m'
NC='\033[0m' # No Color

# Default to 'quick' if no argument provided
MODE="${1:-quick}"

# Counters
SUCCESS=0
FAILED=0
SKIPPED=0

# Function to print section headers
print_header() {
    echo ""
    echo "╔════════════════════════════════════════════════════════════════╗"
    echo "║  $1"
    echo "╚════════════════════════════════════════════════════════════════╝"
    echo ""
}

# Function to run a loader
run_loader() {
    local loader=$1
    local description=$2

    if [ ! -f "$loader" ]; then
        echo -e "${RED}✗ File not found: $loader${NC}"
        ((FAILED++))
        return 1
    fi

    echo -e "${BLUE}→${NC} Running: $description..."

    if timeout 3600 python3 "$loader" 2>&1; then
        echo -e "${GREEN}✓ Complete: $description${NC}\n"
        ((SUCCESS++))
        return 0
    else
        echo -e "${RED}✗ Failed: $description${NC}\n"
        ((FAILED++))
        return 1
    fi
}

# ═══════════════════════════════════════════════════════════════════════════════
# MAIN EXECUTION
# ═══════════════════════════════════════════════════════════════════════════════

print_header "DATA LOADER EXECUTION - Mode: $MODE"

# TIER 0: Always run this first
print_header "TIER 0: SCHEMA INITIALIZATION"
run_loader "init_database.py" "Initialize database schema (77 tables)"

# TIER 1: Foundational data
if [[ "$MODE" == "tier1" ]] || [[ "$MODE" == "quick" ]] || [[ "$MODE" == "tier2" ]] || [[ "$MODE" == "tier3" ]] || [[ "$MODE" == "all" ]]; then
    print_header "TIER 1: FOUNDATIONAL DATA"

    run_loader "loadstocksymbols.py" "Load 5000+ stock symbols"

    # These can run in parallel
    echo -e "${BLUE}→${NC} Running price and company data in parallel..."
    python3 loadlatestpricedaily.py > /tmp/loadlatestpricedaily.log 2>&1 &
    PID1=$!
    python3 loaddailycompanydata.py > /tmp/loaddailycompanydata.log 2>&1 &
    PID2=$!

    echo "   Waiting for loadlatestpricedaily.py..."
    if wait $PID1; then
        echo -e "${GREEN}✓ Complete: Load latest daily prices${NC}"
        ((SUCCESS++))
    else
        echo -e "${RED}✗ Failed: Load latest daily prices${NC}"
        ((FAILED++))
    fi

    echo "   Waiting for loaddailycompanydata.py..."
    if wait $PID2; then
        echo -e "${GREEN}✓ Complete: Load company profiles and metrics${NC}"
        ((SUCCESS++))
    else
        echo -e "${RED}✗ Failed: Load company profiles${NC}"
        ((FAILED++))
    fi
    echo ""
fi

# TIER 2: Analytics and signals
if [[ "$MODE" == "tier2" ]] || [[ "$MODE" == "quick" ]] || [[ "$MODE" == "tier3" ]] || [[ "$MODE" == "all" ]]; then
    print_header "TIER 2: TRADING SIGNALS & METRICS"

    # Run in parallel
    echo -e "${BLUE}→${NC} Running signals and metrics in parallel..."
    python3 loadbuyselldaily.py > /tmp/loadbuyselldaily.log 2>&1 &
    PID1=$!
    python3 loadfactormetrics.py > /tmp/loadfactormetrics.log 2>&1 &
    PID2=$!
    python3 loadsectors.py > /tmp/loadsectors.log 2>&1 &
    PID3=$!
    python3 loadearningshistory.py > /tmp/loadearningshistory.log 2>&1 &
    PID4=$!

    echo "   Waiting for all to complete..."
    wait_count=4
    failed=0

    if wait $PID1; then
        echo -e "${GREEN}✓ Buy/Sell Daily Signals${NC}"
        ((SUCCESS++))
    else
        ((FAILED++))
        ((failed++))
    fi

    if wait $PID2; then
        echo -e "${GREEN}✓ Factor Metrics${NC}"
        ((SUCCESS++))
    else
        ((FAILED++))
        ((failed++))
    fi

    if wait $PID3; then
        echo -e "${GREEN}✓ Sector Rankings${NC}"
        ((SUCCESS++))
    else
        ((FAILED++))
        ((failed++))
    fi

    if wait $PID4; then
        echo -e "${GREEN}✓ Earnings History${NC}"
        ((SUCCESS++))
    else
        ((FAILED++))
        ((failed++))
    fi

    echo ""
fi

# TIER 3: Financial Statements
if [[ "$MODE" == "tier3" ]] || [[ "$MODE" == "all" ]]; then
    print_header "TIER 3: FINANCIAL STATEMENTS"

    echo -e "${BLUE}→${NC} Loading financial statements for all 5000+ stocks (parallel)..."

    python3 loadannualincomestatement.py > /tmp/loadannualincomestatement.log 2>&1 &
    PID1=$!
    python3 loadannualbalancesheet.py > /tmp/loadannualbalancesheet.log 2>&1 &
    PID2=$!
    python3 loadannualcashflow.py > /tmp/loadannualcashflow.log 2>&1 &
    PID3=$!
    python3 loadquarterlyincomestatement.py > /tmp/loadquarterlyincomestatement.log 2>&1 &
    PID4=$!
    python3 loadquarterlybalancesheet.py > /tmp/loadquarterlybalancesheet.log 2>&1 &
    PID5=$!
    python3 loadquarterlycashflow.py > /tmp/loadquarterlycashflow.log 2>&1 &
    PID6=$!

    echo "   Waiting for all financial statements to complete..."

    wait_pids=($PID1 $PID2 $PID3 $PID4 $PID5 $PID6)
    names=("Annual Income Statement" "Annual Balance Sheet" "Annual Cash Flow" \
           "Quarterly Income Statement" "Quarterly Balance Sheet" "Quarterly Cash Flow")

    for i in "${!wait_pids[@]}"; do
        if wait ${wait_pids[$i]}; then
            echo -e "${GREEN}✓ ${names[$i]}${NC}"
            ((SUCCESS++))
        else
            echo -e "${RED}✗ ${names[$i]}${NC}"
            ((FAILED++))
        fi
    done
    echo ""
fi

# TIER 4: Sentiment and Market Data
if [[ "$MODE" == "all" ]]; then
    print_header "TIER 4: SENTIMENT & MARKET DATA"

    echo -e "${BLUE}→${NC} Running sentiment and market loaders in parallel..."

    python3 loadaaiidata.py > /tmp/loadaaiidata.log 2>&1 &
    PID1=$!
    python3 loadnaaim.py > /tmp/loadnaaim.log 2>&1 &
    PID2=$!
    python3 loadfeargreed.py > /tmp/loadfeargreed.log 2>&1 &
    PID3=$!

    echo "   Waiting for sentiment data to complete..."

    if wait $PID1; then
        echo -e "${GREEN}✓ AAII Sentiment${NC}"
        ((SUCCESS++))
    else
        ((FAILED++))
    fi

    if wait $PID2; then
        echo -e "${GREEN}✓ NAAIM Index${NC}"
        ((SUCCESS++))
    else
        ((FAILED++))
    fi

    if wait $PID3; then
        echo -e "${GREEN}✓ Fear & Greed Index${NC}"
        ((SUCCESS++))
    else
        ((FAILED++))
    fi

    echo ""
fi

# ═══════════════════════════════════════════════════════════════════════════════
# SUMMARY
# ═══════════════════════════════════════════════════════════════════════════════

print_header "EXECUTION COMPLETE"

echo "Results:"
echo -e "  ${GREEN}✓ Successful: $SUCCESS${NC}"
echo -e "  ${RED}✗ Failed: $FAILED${NC}"
echo ""

if [ $FAILED -eq 0 ]; then
    echo -e "${GREEN}✓ ALL LOADERS COMPLETED SUCCESSFULLY${NC}"
    echo ""
    echo "Your database is now populated with:"
    echo "  • 5000+ stock symbols"
    echo "  • Daily price data (1.2M+ candles)"
    echo "  • Company profiles and metrics"
    echo "  • Buy/sell signals"
    echo "  • Technical indicators"
    echo "  • Financial statements"
    echo "  • Sector and industry rankings"
    echo "  $([ "$MODE" == "all" ] && echo "• Sentiment and market data")"
    echo ""
    echo "You can now start your frontend:"
    echo "  cd webapp/frontend-admin && npm run dev"
    echo ""
    echo "Access at: http://localhost:5174"
else
    echo -e "${RED}⚠ Some loaders failed. Check logs in /tmp/ for details.${NC}"
    echo ""
    echo "Failed loaders:"
    grep -l "Failed" /tmp/*.log 2>/dev/null | xargs -I {} basename {} .log || true
fi

echo ""
