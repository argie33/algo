#!/bin/bash

# Comprehensive Data Loading Status & Monitoring Script
# Real-time tracking of all data loaders and database state

set -e

# Colors for output
RED='\033[0;31m'
GREEN='\033[0;32m'
YELLOW='\033[1;33m'
BLUE='\033[0;34m'
NC='\033[0m' # No Color

# Database config
export PGPASSWORD=bed0elAn
DB_HOST=localhost
DB_USER=stocks
DB_NAME=stocks

echo -e "${BLUE}════════════════════════════════════════════════════════════════${NC}"
echo -e "${BLUE}  📊 DATA LOADING STATUS REPORT - $(date +'%Y-%m-%d %H:%M:%S')${NC}"
echo -e "${BLUE}════════════════════════════════════════════════════════════════${NC}"

# ━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━
# 1️⃣  RUNNING PROCESSES
# ━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━

echo -e "\n${BLUE}━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━${NC}"
echo -e "${BLUE}1️⃣  RUNNING LOADER PROCESSES${NC}"
echo -e "${BLUE}━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━${NC}"

running_count=$(ps aux | grep -E "python3.*load(price|buysell|stock)" | grep -v grep | wc -l)

if [ $running_count -eq 0 ]; then
    echo -e "${YELLOW}⚠️  No loaders currently running${NC}"
else
    echo -e "${GREEN}✅ $running_count loader processes active${NC}"
    ps aux | grep -E "python3.*load(price|buysell|stock)" | grep -v grep | awk '{print "  • "$11" - "$2" - CPU: "$3"% - MEM: "$4"%"}'
fi

# ━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━
# 2️⃣  DATABASE STATISTICS
# ━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━

echo -e "\n${BLUE}━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━${NC}"
echo -e "${BLUE}2️⃣  DATABASE STATISTICS${NC}"
echo -e "${BLUE}━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━${NC}"

# Stock Symbols
symbols_count=$(psql -h $DB_HOST -U $DB_USER -d $DB_NAME -t -c "SELECT COUNT(*) FROM stock_symbols;" 2>/dev/null || echo "0")
echo -e "\n📌 ${YELLOW}Stock Symbols:${NC} $symbols_count / 4,988"
if [ "$symbols_count" -ge 4900 ]; then
    pct=$((symbols_count * 100 / 4988))
    echo -e "   ${GREEN}✅ $pct% Complete${NC}"
else
    pct=$((symbols_count * 100 / 4988))
    echo -e "   ${YELLOW}⏳ $pct% Complete${NC}"
fi

# Price Data
prices_symbols=$(psql -h $DB_HOST -U $DB_USER -d $DB_NAME -t -c "SELECT COUNT(DISTINCT symbol) FROM price_daily WHERE symbol IN (SELECT symbol FROM stock_symbols);" 2>/dev/null || echo "0")
prices_records=$(psql -h $DB_HOST -U $DB_USER -d $DB_NAME -t -c "SELECT COUNT(*) FROM price_daily;" 2>/dev/null || echo "0")
echo -e "\n💰 ${YELLOW}Price Data:${NC} $prices_symbols symbols / 4,988"
echo -e "   Records: $prices_records"
if [ "$prices_symbols" -ge 4500 ]; then
    pct=$((prices_symbols * 100 / 4988))
    echo -e "   ${GREEN}✅ $pct% Complete${NC}"
elif [ "$prices_symbols" -ge 3000 ]; then
    pct=$((prices_symbols * 100 / 4988))
    echo -e "   ${YELLOW}⏳ $pct% Complete${NC}"
else
    pct=$((prices_symbols * 100 / 4988))
    echo -e "   ${YELLOW}⏳ $pct% Complete${NC}"
fi

# Buy/Sell Signals
signals_symbols=$(psql -h $DB_HOST -U $DB_USER -d $DB_NAME -t -c "SELECT COUNT(DISTINCT symbol) FROM buy_sell_daily WHERE symbol IN (SELECT symbol FROM stock_symbols);" 2>/dev/null || echo "0")
signals_records=$(psql -h $DB_HOST -U $DB_USER -d $DB_NAME -t -c "SELECT COUNT(*) FROM buy_sell_daily;" 2>/dev/null || echo "0")
echo -e "\n📈 ${YELLOW}Buy/Sell Signals:${NC} $signals_symbols symbols / 4,988"
echo -e "   Records: $signals_records"
if [ "$signals_symbols" -ge 3000 ]; then
    pct=$((signals_symbols * 100 / 4988))
    echo -e "   ${GREEN}✅ $pct% Complete${NC}"
elif [ "$signals_symbols" -ge 1000 ]; then
    pct=$((signals_symbols * 100 / 4988))
    echo -e "   ${YELLOW}⏳ $pct% Complete${NC}"
else
    pct=$((signals_symbols * 100 / 4988))
    echo -e "   ${RED}❌ $pct% Complete${NC}"
fi

# Stock Scores
scores_count=$(psql -h $DB_HOST -U $DB_USER -d $DB_NAME -t -c "SELECT COUNT(*) FROM stock_scores;" 2>/dev/null || echo "0")
echo -e "\n⭐ ${YELLOW}Stock Scores:${NC} $scores_count / 4,988"
if [ "$scores_count" -ge 4500 ]; then
    pct=$((scores_count * 100 / 4988))
    echo -e "   ${GREEN}✅ $pct% Complete${NC}"
else
    pct=$((scores_count * 100 / 4988))
    echo -e "   ${YELLOW}⏳ $pct% Complete${NC}"
fi

# ━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━
# 3️⃣  ERROR ANALYSIS
# ━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━

echo -e "\n${BLUE}━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━${NC}"
echo -e "${BLUE}3️⃣  ERROR ANALYSIS${NC}"
echo -e "${BLUE}━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━${NC}"

for log_file in /tmp/buy_sell_daily.log /tmp/stock_scores.log /tmp/price_daily.log /tmp/loader_loadpricedaily.log; do
    if [ -f "$log_file" ]; then
        error_count=$(grep -i "error\|failed\|exception" "$log_file" 2>/dev/null | wc -l)
        if [ "$error_count" -gt 0 ]; then
            echo -e "\n${RED}❌ $(basename $log_file): $error_count errors${NC}"
            grep -i "error\|failed\|exception" "$log_file" 2>/dev/null | tail -3 | sed 's/^/   /'
        else
            echo -e "\n${GREEN}✅ $(basename $log_file): No errors${NC}"
        fi
    fi
done

# ━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━
# 4️⃣  RECENT LOG MESSAGES
# ━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━

echo -e "\n${BLUE}━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━${NC}"
echo -e "${BLUE}4️⃣  RECENT LOG ACTIVITY${NC}"
echo -e "${BLUE}━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━${NC}"

if [ -f /tmp/buy_sell_daily.log ]; then
    echo -e "\n📊 Buy/Sell Signals:"
    tail -3 /tmp/buy_sell_daily.log | sed 's/^/   /'
fi

if [ -f /tmp/stock_scores.log ]; then
    echo -e "\n⭐ Stock Scores:"
    tail -3 /tmp/stock_scores.log | sed 's/^/   /'
fi

# ━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━
# 5️⃣  COMPLETION ESTIMATION
# ━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━

echo -e "\n${BLUE}━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━${NC}"
echo -e "${BLUE}5️⃣  OVERALL STATUS${NC}"
echo -e "${BLUE}━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━${NC}"

# Calculate overall completion
total_items=$((symbols_count + prices_symbols + signals_symbols + scores_count))
target_items=$((4988 * 4))
pct=$((total_items * 100 / target_items))

if [ $running_count -eq 0 ]; then
    echo -e "\n${YELLOW}⏸️  All loaders have completed${NC}"
    echo -e "Overall completion: ${pct}%"

    if [ "$symbols_count" -ge 4900 ] && [ "$prices_symbols" -ge 4500 ] && [ "$signals_symbols" -ge 3000 ] && [ "$scores_count" -ge 4500 ]; then
        echo -e "\n${GREEN}🎉 DATA LOADING COMPLETE - READY FOR PRODUCTION${NC}"
    else
        echo -e "\n${YELLOW}⚠️  Some data gaps remain - manual verification needed${NC}"
    fi
else
    echo -e "\n${GREEN}🚀 Loaders still running...${NC}"
    echo -e "Overall completion: ${pct}%"
    echo -e "Estimated time remaining: 30-60 minutes"
fi

echo -e "\n${BLUE}════════════════════════════════════════════════════════════════${NC}"
