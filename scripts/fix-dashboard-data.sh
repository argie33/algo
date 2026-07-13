#!/bin/bash
# Fix dashboard data quality issues for 2026-07-10
# Regenerates missing derived data tables to restore dashboard functionality

set -e

echo "=================================="
echo "Dashboard Data Fix Script"
echo "Generated: 2026-07-10"
echo "===================================="
echo ""

# Colors for output
RED='\033[0;31m'
GREEN='\033[0;32m'
YELLOW='\033[1;33m'
NC='\033[0m' # No Color

# Check if running from repo root
if [ ! -f "CLAUDE.md" ]; then
    echo -e "${RED}Error: Must run from repo root directory${NC}"
    exit 1
fi

# Set environment for local dev
export ENVIRONMENT="development"
export LOCAL_MODE="true"
export DB_HOST="${DB_HOST:-localhost}"
export DB_PORT="${DB_PORT:-5432}"
export DB_NAME="${DB_NAME:-stocks}"
export DB_USER="${DB_USER:-stocks}"
export DB_PASSWORD="${DB_PASSWORD:-stocks}"
export LOADER_PARALLELISM="1"
export ORCHESTRATOR_DRY_RUN="false"
export PYTHONPATH="$(pwd)"

echo -e "${YELLOW}[CONFIG]${NC} Local dev environment configured"
echo "  DB_HOST: $DB_HOST:$DB_PORT"
echo "  DB_NAME: $DB_NAME"
echo ""

# Step 1: Regenerate technical_data_daily
echo -e "${YELLOW}[STEP 1]${NC} Regenerating technical_data_daily for 2026-07-10..."
echo "  This processes 10,323+ symbols and computes technical indicators"
echo "  Expected time: 2-5 minutes"
echo ""

if INTRADAY_MODE=true python3 loaders/load_technical_data_daily.py; then
    echo -e "${GREEN}[SUCCESS]${NC} technical_data_daily regenerated"
    # Verify data was added
    TECH_COUNT=$(python3 -c "
import psycopg2, os
conn = psycopg2.connect(host='$DB_HOST', port=$DB_PORT, user='$DB_USER', password='$DB_PASSWORD', database='$DB_NAME')
cur = conn.cursor()
cur.execute(\"SELECT COUNT(*) FROM technical_data_daily WHERE date='2026-07-10'\")
print(cur.fetchone()[0])
cur.close()
conn.close()
" 2>/dev/null || echo "0")
    echo "  Rows for 2026-07-10: $TECH_COUNT (expected: ~10,000)"
else
    echo -e "${RED}[FAILED]${NC} technical_data_daily loader failed"
    exit 1
fi
echo ""

# Step 2: Regenerate buy_sell_daily signals
echo -e "${YELLOW}[STEP 2]${NC} Regenerating buy_sell_daily signals for 2026-07-10..."
echo "  This generates BUY/SELL trading signals from technical indicators"
echo "  Expected time: 1-3 minutes"
echo ""

if python3 loaders/load_buy_sell_daily.py; then
    echo -e "${GREEN}[SUCCESS]${NC} buy_sell_daily signals regenerated"
    # Verify data was added
    SIGNALS_COUNT=$(python3 -c "
import psycopg2, os
conn = psycopg2.connect(host='$DB_HOST', port=$DB_PORT, user='$DB_USER', password='$DB_PASSWORD', database='$DB_NAME')
cur = conn.cursor()
cur.execute(\"SELECT COUNT(*) FROM buy_sell_daily WHERE date='2026-07-10'\")
print(cur.fetchone()[0])
cur.close()
conn.close()
" 2>/dev/null || echo "0")
    echo "  Signals for 2026-07-10: $SIGNALS_COUNT (expected: ~400)"
else
    echo -e "${RED}[FAILED]${NC} buy_sell_daily loader failed"
    echo "  This may be normal if technical_data_daily coverage is still low"
    echo "  Retry after technical_data_daily completes fully"
fi
echo ""

# Step 3: Regenerate market_health_daily
echo -e "${YELLOW}[STEP 3]${NC} Regenerating market_health_daily for 2026-07-10..."
echo "  This generates market health indicators (breadth, VIX, yield curve)"
echo "  Expected time: 30 seconds"
echo ""

if python3 loaders/load_market_health_daily.py; then
    echo -e "${GREEN}[SUCCESS]${NC} market_health_daily regenerated"
    # Verify data was added
    HEALTH_COUNT=$(python3 -c "
import psycopg2, os
conn = psycopg2.connect(host='$DB_HOST', port=$DB_PORT, user='$DB_USER', password='$DB_PASSWORD', database='$DB_NAME')
cur = conn.cursor()
cur.execute(\"SELECT COUNT(*) FROM market_health_daily WHERE date='2026-07-10'\")
print(cur.fetchone()[0])
cur.close()
conn.close()
" 2>/dev/null || echo "0")
    echo "  Rows for 2026-07-10: $HEALTH_COUNT (expected: 1)"
else
    echo -e "${RED}[FAILED]${NC} market_health_daily loader failed"
    exit 1
fi
echo ""

# Summary
echo -e "${GREEN}=================================="
echo "Data Regeneration Complete!"
echo "==================================${NC}"
echo ""
echo "Next steps:"
echo "1. Start API dev server in terminal 1:"
echo "   python3 lambda/api/dev_server.py"
echo ""
echo "2. Start dashboard in terminal 2:"
echo "   python3 -m dashboard --local -w 30"
echo ""
echo "3. Dashboard should now display all data without 'unavailable' messages"
echo ""
