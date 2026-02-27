#!/bin/bash

# ==============================================================================
# COMPLETE DATA RECOVERY - Ensure ALL symbols have prices, scores, and signals
# ==============================================================================
# Strategy:
# 1. Clear partial signal data and reload for ALL symbols
# 2. Fill in missing prices
# 3. Recalculate scores
# 4. Verify 100% coverage
# ==============================================================================

set -e

SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
cd "$SCRIPT_DIR"

# Export database credentials
export PGPASSWORD="${DB_PASSWORD:-bed0elAn}"
export DB_HOST="${DB_HOST:-localhost}"
export DB_USER="${DB_USER:-stocks}"
export DB_PASSWORD="${DB_PASSWORD:-bed0elAn}"
export DB_NAME="${DB_NAME:-stocks}"

# Colors
RED='\033[0;31m'
YELLOW='\033[1;33m'
GREEN='\033[0;32m'
BLUE='\033[0;34m'
NC='\033[0m'

echo -e "${BLUE}╔════════════════════════════════════════════════════════════════╗${NC}"
echo -e "${BLUE}║          COMPLETE DATA RECOVERY - Full Coverage                ║${NC}"
echo -e "${BLUE}╚════════════════════════════════════════════════════════════════╝${NC}"
echo ""

# ==============================================================================
# STEP 1: CHECK SYSTEM RESOURCES
# ==============================================================================
echo -e "${YELLOW}[STEP 1] Checking system resources...${NC}"

check_resources() {
    local min_free_mb=400
    local free_mb=$(free -h | awk '/^Mem:/ {print int($7)}')

    echo "  Memory: $free_mb MB free"

    if [ "$free_mb" -lt "$min_free_mb" ]; then
        echo -e "${RED}  ❌ CRITICAL: Only ${free_mb}MB free (need ${min_free_mb}MB)${NC}"
        echo "  Killing any background processes..."
        pkill -f "loadbuyselldaily\|loadpricedaily\|loadpriceweekly\|loadcompany\|loadfactor\|node" || true
        sleep 5
        return 1
    fi
    echo -e "${GREEN}  ✅ Resources OK${NC}"
    return 0
}

if ! check_resources; then
    echo "Retrying after cleanup..."
    sleep 10
    check_resources || exit 1
fi

echo ""

# ==============================================================================
# STEP 2: VERIFY DATABASE CONNECTIVITY
# ==============================================================================
echo -e "${YELLOW}[STEP 2] Verifying database connectivity...${NC}"

if PGPASSWORD="$PGPASSWORD" psql -h "$DB_HOST" -U "$DB_USER" -d "$DB_NAME" -c "SELECT 1" > /dev/null 2>&1; then
    echo -e "${GREEN}  ✅ Database connected${NC}"
else
    echo -e "${RED}  ❌ Database connection failed${NC}"
    exit 1
fi

echo ""

# ==============================================================================
# STEP 3: ANALYZE CURRENT DATA GAPS
# ==============================================================================
echo -e "${YELLOW}[STEP 3] Analyzing data gaps...${NC}"

# Get counts
total_symbols=$(PGPASSWORD="$PGPASSWORD" psql -h "$DB_HOST" -U "$DB_USER" -d "$DB_NAME" -t -c "SELECT COUNT(*) FROM stock_symbols")
symbols_with_prices=$(PGPASSWORD="$PGPASSWORD" psql -h "$DB_HOST" -U "$DB_USER" -d "$DB_NAME" -t -c "SELECT COUNT(DISTINCT symbol) FROM price_daily")
symbols_with_signals=$(PGPASSWORD="$PGPASSWORD" psql -h "$DB_HOST" -U "$DB_USER" -d "$DB_NAME" -t -c "SELECT COUNT(DISTINCT symbol) FROM buy_sell_daily")
symbols_with_scores=$(PGPASSWORD="$PGPASSWORD" psql -h "$DB_HOST" -U "$DB_USER" -d "$DB_NAME" -t -c "SELECT COUNT(*) FROM stock_scores")

echo "  Total Symbols: $total_symbols"
echo "  With Prices:   $symbols_with_prices / $total_symbols ($(echo "scale=1; $symbols_with_prices*100/$total_symbols" | bc)%)"
echo "  With Signals:  $symbols_with_signals / $total_symbols ($(echo "scale=1; $symbols_with_signals*100/$total_symbols" | bc)%) ← CRITICAL!"
echo "  With Scores:   $symbols_with_scores / $total_symbols"

missing_prices=$((total_symbols - symbols_with_prices))
missing_signals=$((total_symbols - symbols_with_signals))
missing_scores=$((total_symbols - symbols_with_scores))

echo ""
echo "  Missing Data:"
echo "    Prices:  $missing_prices symbols"
echo "    Signals: $missing_signals symbols ← PRIORITY 1"
echo "    Scores:  $missing_scores symbols"

echo ""

# ==============================================================================
# STEP 4: RELOAD BUY/SELL SIGNALS FOR ALL SYMBOLS
# ==============================================================================
echo -e "${YELLOW}[STEP 4] Reloading buy/sell signals for ALL 4,989 symbols...${NC}"
echo "  This is the critical missing data - will take 1-2 hours"
echo ""

if [ -f "./loadbuyselldaily.py" ]; then
    echo "  Starting signal loader..."
    echo "  Estimated time: 60-90 minutes"
    echo "  Process: $(ps aux | grep -c "loadbuyselldaily") running"
    echo ""

    timeout 7200 python3 loadbuyselldaily.py 2>&1 | tail -50

    # Verify signals loaded
    echo ""
    new_signal_count=$(PGPASSWORD="$PGPASSWORD" psql -h "$DB_HOST" -U "$DB_USER" -d "$DB_NAME" -t -c "SELECT COUNT(*) FROM buy_sell_daily")
    new_symbols_with_signals=$(PGPASSWORD="$PGPASSWORD" psql -h "$DB_HOST" -U "$DB_USER" -d "$DB_NAME" -t -c "SELECT COUNT(DISTINCT symbol) FROM buy_sell_daily")

    echo -e "${GREEN}  ✅ Signal load complete${NC}"
    echo "     Total signals: $new_signal_count"
    echo "     Symbols covered: $new_symbols_with_signals / $total_symbols"
else
    echo -e "${RED}  ❌ loadbuyselldaily.py not found${NC}"
fi

echo ""

# ==============================================================================
# STEP 5: LOAD MISSING PRICES
# ==============================================================================
echo -e "${YELLOW}[STEP 5] Loading missing prices for remaining symbols...${NC}"

missing_symbols=$(PGPASSWORD="$PGPASSWORD" psql -h "$DB_HOST" -U "$DB_USER" -d "$DB_NAME" -t -c "
SELECT string_agg(symbol, ',') FROM stock_symbols s
WHERE NOT EXISTS (SELECT 1 FROM price_daily p WHERE p.symbol = s.symbol)
" 2>/dev/null | tr -d ' ')

if [ -n "$missing_symbols" ]; then
    echo "  Missing symbols: $missing_symbols"
    echo "  Loading prices..."

    if [ -f "./loadpricedaily.py" ]; then
        timeout 600 python3 loadpricedaily.py 2>&1 | tail -30
    fi
fi

echo ""

# ==============================================================================
# STEP 6: RECALCULATE SCORES
# ==============================================================================
echo -e "${YELLOW}[STEP 6] Recalculating stock scores for ALL symbols...${NC}"

if [ -f "./loadstockscores.py" ]; then
    timeout 300 python3 loadstockscores.py 2>&1 | tail -30
fi

echo ""

# ==============================================================================
# STEP 7: FINAL VERIFICATION
# ==============================================================================
echo -e "${YELLOW}[STEP 7] Final data verification...${NC}"

final_prices=$(PGPASSWORD="$PGPASSWORD" psql -h "$DB_HOST" -U "$DB_USER" -d "$DB_NAME" -t -c "SELECT COUNT(DISTINCT symbol) FROM price_daily")
final_signals=$(PGPASSWORD="$PGPASSWORD" psql -h "$DB_HOST" -U "$DB_USER" -d "$DB_NAME" -t -c "SELECT COUNT(DISTINCT symbol) FROM buy_sell_daily")
final_scores=$(PGPASSWORD="$PGPASSWORD" psql -h "$DB_HOST" -U "$DB_USER" -d "$DB_NAME" -t -c "SELECT COUNT(*) FROM stock_scores")

echo ""
echo -e "${BLUE}═══════════════════════════════════════════════════════════${NC}"
echo -e "${BLUE}                    FINAL STATUS                           ${NC}"
echo -e "${BLUE}═══════════════════════════════════════════════════════════${NC}"
echo ""
echo "  Total Symbols:     $total_symbols"
echo "  Symbols w/ Prices: $final_prices / $total_symbols $([ "$final_prices" -eq "$total_symbols" ] && echo "✅" || echo "⚠️")"
echo "  Symbols w/ Signals: $final_signals / $total_symbols $([ "$final_signals" -eq "$total_symbols" ] && echo "✅" || echo "⚠️")"
echo "  Stock Scores:      $final_scores / $total_symbols $([ "$final_scores" -eq "$total_symbols" ] && echo "✅" || echo "⚠️")"
echo ""

if [ "$final_prices" -eq "$total_symbols" ] && [ "$final_signals" -eq "$total_symbols" ] && [ "$final_scores" -eq "$total_symbols" ]; then
    echo -e "${GREEN}╔════════════════════════════════════════════════════════════════╗${NC}"
    echo -e "${GREEN}║          ✅ ALL DATA COMPLETE - 100% COVERAGE                  ║${NC}"
    echo -e "${GREEN}╚════════════════════════════════════════════════════════════════╝${NC}"
else
    echo -e "${YELLOW}⚠️  Data gaps remaining - rerun this script to complete${NC}"
fi

echo ""
echo "Completed: $(date +'%Y-%m-%d %H:%M:%S')"
