#!/bin/bash

# Real-time progress monitor for data loading
export PGPASSWORD="bed0elAn"

GREEN='\033[0;32m'
YELLOW='\033[1;33m'
RED='\033[0;31m'
BLUE='\033[0;34m'
NC='\033[0m'

clear

while true; do
    clear
    echo -e "${BLUE}╔════════════════════════════════════════════════════════════╗${NC}"
    echo -e "${BLUE}║          REAL-TIME DATA LOADING PROGRESS                 ║${NC}"
    echo -e "${BLUE}║          $(date +'%Y-%m-%d %H:%M:%S')                                   ║${NC}"
    echo -e "${BLUE}╚════════════════════════════════════════════════════════════╝${NC}"
    echo ""

    # Get current counts
    SIGNAL_SYM=$(psql -h localhost -U stocks -d stocks -t -c "SELECT COUNT(DISTINCT symbol) FROM buy_sell_daily" 2>/dev/null || echo "?")
    SIGNAL_REC=$(psql -h localhost -U stocks -d stocks -t -c "SELECT COUNT(*) FROM buy_sell_daily" 2>/dev/null || echo "?")
    SCORE_COUNT=$(psql -h localhost -U stocks -d stocks -t -c "SELECT COUNT(*) FROM stock_scores" 2>/dev/null || echo "?")
    PRICE_SYM=$(psql -h localhost -U stocks -d stocks -t -c "SELECT COUNT(DISTINCT symbol) FROM price_daily" 2>/dev/null || echo "?")
    PRICE_REC=$(psql -h localhost -U stocks -d stocks -t -c "SELECT COUNT(*) FROM price_daily" 2>/dev/null || echo "?")
    GROWTH=$(psql -h localhost -U stocks -d stocks -t -c "SELECT COUNT(*) FROM growth_metrics" 2>/dev/null || echo "?")
    QUAL=$(psql -h localhost -U stocks -d stocks -t -c "SELECT COUNT(*) FROM quality_metrics" 2>/dev/null || echo "?")
    VALUE=$(psql -h localhost -U stocks -d stocks -t -c "SELECT COUNT(*) FROM value_metrics" 2>/dev/null || echo "?")

    # Memory
    FREE_MB=$(free -h | awk '/^Mem:/ {print $4}')
    MEM_PCT=$(free | awk '/^Mem:/ {printf "%.0f", ($3/$2)*100}')

    # Active processes
    PYTHON_COUNT=$(ps aux | grep -E "python3 load" | grep -v grep | wc -l)

    # Display
    echo -e "${YELLOW}📊 DATA LOADING STATUS:${NC}"
    echo ""
    echo -e "  Buy/Sell Signals:    ${SIGNAL_SYM}/4989 symbols  (${SIGNAL_REC} total records)"
    [ "$SIGNAL_SYM" -lt 100 ] && echo -e "    ${YELLOW}⏳ Loading... (still in early symbols)${NC}"
    [ "$SIGNAL_SYM" -gt 500 ] && echo -e "    ${GREEN}✅ Good progress!${NC}"
    [ "$SIGNAL_SYM" -gt 2000 ] && echo -e "    ${GREEN}✅ Excellent!${NC}"
    [ "$SIGNAL_SYM" = "4989" ] && echo -e "    ${GREEN}✅ COMPLETE!${NC}"
    echo ""

    echo -e "  Stock Scores:        ${SCORE_COUNT}/4989"
    [ "$SCORE_COUNT" = "4989" ] && echo -e "    ${GREEN}✅ COMPLETE${NC}" || echo -e "    ${YELLOW}⏳ Updating${NC}"
    echo ""

    echo -e "  Daily Prices:        ${PRICE_SYM}/4989 symbols  (${PRICE_REC} total records)"
    [ "$PRICE_SYM" -lt 4951 ] && echo -e "    ${YELLOW}⏳ Loading missing ${$((4989 - PRICE_SYM))} symbols${NC}" || echo -e "    ${GREEN}✅ COMPLETE${NC}"
    echo ""

    echo -e "  Factor Metrics:"
    echo -e "    Growth:            ${GROWTH} symbols"
    echo -e "    Quality:           ${QUAL}/4989"
    echo -e "    Value:             ${VALUE} symbols"
    echo ""

    echo -e "${YELLOW}💻 SYSTEM RESOURCES:${NC}"
    echo -e "  Memory:              ${MEM_PCT}% used  (${FREE_MB} free)"
    [ "$MEM_PCT" -gt 80 ] && echo -e "    ${RED}⚠️ WARNING: Low memory!${NC}"
    [ "$MEM_PCT" -le 80 ] && echo -e "    ${GREEN}✅ OK${NC}"
    echo -e "  Active Loaders:      ${PYTHON_COUNT} processes"
    echo ""

    echo -e "${BLUE}════════════════════════════════════════════════════════════${NC}"
    echo "Press Ctrl+C to stop monitoring"
    echo "Refreshing in 10 seconds..."

    sleep 10
done
