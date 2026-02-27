#!/bin/bash

# ==============================================================================
# LOAD ALL SIGNALS - Complete Buy/Sell Signal Coverage for All 4,989 Symbols
# ==============================================================================
# Focuses on loading signals for ALL symbols, monitoring progress
# ==============================================================================

set -e

export PGPASSWORD="bed0elAn"
export DB_HOST="localhost"
export DB_USER="stocks"
export DB_PASSWORD="bed0elAn"
export DB_NAME="stocks"

SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
cd "$SCRIPT_DIR"

GREEN='\033[0;32m'
YELLOW='\033[1;33m'
BLUE='\033[0;34m'
RED='\033[0;31m'
NC='\033[0m'

echo -e "${BLUE}╔════════════════════════════════════════════════════════════════╗${NC}"
echo -e "${BLUE}║     LOAD ALL BUY/SELL SIGNALS - Complete Coverage             ║${NC}"
echo -e "${BLUE}╚════════════════════════════════════════════════════════════════╝${NC}"
echo ""

# Check memory
free_mb=$(free -h | awk '/^Mem:/ {print int($7)}')
echo -e "${YELLOW}System Resources:${NC}"
echo "  Free Memory: ${free_mb}MB"
echo ""

if [ "$free_mb" -lt 300 ]; then
    echo -e "${RED}❌ WARNING: Low memory (${free_mb}MB). This will take longer.${NC}"
    echo "  Waiting 30 seconds before starting..."
    sleep 30
fi

# Current status
echo -e "${YELLOW}Current Data Status:${NC}"
psql -h "$DB_HOST" -U "$DB_USER" -d "$DB_NAME" -t -c "
SELECT 'Total Symbols: ' || COUNT(*) FROM stock_symbols
UNION ALL
SELECT 'Symbols with signals: ' || COUNT(DISTINCT symbol) FROM buy_sell_daily
UNION ALL
SELECT 'Total signal records: ' || COUNT(*) FROM buy_sell_daily
" 2>/dev/null | sed 's/^/  /'

echo ""

# Run the signal loader
echo -e "${YELLOW}Starting buy/sell signal loader...${NC}"
echo "  This will process all 4,989 symbols"
echo "  Estimated time: 60-90 minutes (depends on API rate limits)"
echo ""
echo "  Process started at: $(date +'%Y-%m-%d %H:%M:%S')"
echo "  Tracking progress in: logs/signal_load_progress.log"
echo ""

# Create progress tracking file
mkdir -p logs
echo "[$(date +'%Y-%m-%d %H:%M:%S')] Starting full signal load for all 4989 symbols..." > logs/signal_load_progress.log

# Run loader with output capture
timeout 10800 python3 loadbuyselldaily.py 2>&1 | tee -a logs/signal_load_progress.log | tail -100

echo ""
echo -e "${YELLOW}Signal load complete. Verifying results...${NC}"
echo ""

# Final verification
psql -h "$DB_HOST" -U "$DB_USER" -d "$DB_NAME" -t -c "
SELECT 'FINAL SIGNAL STATUS:' as status
UNION ALL
SELECT '  Total signal records: ' || COUNT(*) FROM buy_sell_daily
UNION ALL
SELECT '  Unique symbols: ' || COUNT(DISTINCT symbol) FROM buy_sell_daily
UNION ALL
SELECT '  Coverage: ' || ROUND(COUNT(DISTINCT symbol) * 100.0 / 4989, 1) || '%' FROM buy_sell_daily
" 2>/dev/null | sed 's/^/  /'

echo ""

# Check for any symbols still missing
missing=$(psql -h "$DB_HOST" -U "$DB_USER" -d "$DB_NAME" -t -c "
SELECT COUNT(*) FROM stock_symbols
WHERE symbol NOT IN (SELECT DISTINCT symbol FROM buy_sell_daily)
" 2>/dev/null | tr -d ' ')

if [ "$missing" -gt 0 ]; then
    echo -e "${YELLOW}⚠️  $missing symbols still missing signals${NC}"
    echo "  These symbols will be attempted on next run"
else
    echo -e "${GREEN}✅ ALL 4,989 SYMBOLS NOW HAVE BUY/SELL SIGNALS!${NC}"
fi

echo ""
echo -e "Completed: $(date +'%Y-%m-%d %H:%M:%S')"
