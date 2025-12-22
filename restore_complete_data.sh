#!/bin/bash
#  COMPLETE DATA RESTORATION SCRIPT
# Restores price data and regenerates signals to match TradingView

set -e  # Exit on any error

echo ""
echo "================================================================================"
echo "COMPLETE DATA RESTORATION"
echo "================================================================================"
echo ""

# Color codes
RED='\033[0;31m'
GREEN='\033[0;32m'
YELLOW='\033[1;33m'
NC='\033[0m' # No Color

cd /home/stocks/algo

# STEP 1: Load all price data
echo -e "${YELLOW}STEP 1: LOADING ALL PRICE DATA...${NC}"
echo "This will fetch price data for all stocks and ETFs"
echo ""

echo "Loading stock daily prices..."
python3 loadpricedaily.py
echo -e "${GREEN}✅ Stock daily prices loaded${NC}"

echo ""
echo "Loading stock weekly prices..."
python3 loadpriceweekly.py
echo -e "${GREEN}✅ Stock weekly prices loaded${NC}"

echo ""
echo "Loading stock monthly prices..."
python3 loadpricemonthly.py
echo -e "${GREEN}✅ Stock monthly prices loaded${NC}"

echo ""
echo "Loading ETF daily prices..."
python3 loadetfpricedaily.py
echo -e "${GREEN}✅ ETF daily prices loaded${NC}"

echo ""
echo "Loading ETF weekly prices..."
python3 loadetfpriceweekly.py
echo -e "${GREEN}✅ ETF weekly prices loaded${NC}"

echo ""
echo "Loading ETF monthly prices..."
python3 loadetfpricemonthly.py
echo -e "${GREEN}✅ ETF monthly prices loaded${NC}"

# STEP 2: Clear corrupted signals
echo ""
echo -e "${YELLOW}STEP 2: CLEARING CORRUPTED SIGNALS...${NC}"
python3 << 'PYEOF'
import psycopg2
import os
from dotenv import load_dotenv

load_dotenv('.env.local')
conn = psycopg2.connect(
    host=os.environ.get("DB_HOST", "localhost"),
    port=int(os.environ.get("DB_PORT", 5432)),
    user=os.environ.get("DB_USER", "postgres"),
    password=os.environ.get("DB_PASSWORD", "password"),
    dbname=os.environ.get("DB_NAME", "stocks")
)
cur = conn.cursor()

tables = ['buy_sell_daily', 'buy_sell_weekly', 'buy_sell_monthly',
          'buy_sell_daily_etf', 'buy_sell_weekly_etf', 'buy_sell_monthly_etf']

for table in tables:
    cur.execute(f"DELETE FROM {table} WHERE signal IN ('Buy', 'Sell')")
    conn.commit()
    deleted = cur.rowcount
    if deleted > 0:
        print(f"  Deleted {deleted} corrupted signals from {table}")

cur.close()
conn.close()
print("✅ Corrupted signals cleared")
PYEOF

# STEP 3: Regenerate signals
echo ""
echo -e "${YELLOW}STEP 3: REGENERATING SIGNALS FROM COMPLETE PRICE DATA...${NC}"

echo "Regenerating stock daily signals..."
python3 loadbuyselldaily.py
echo -e "${GREEN}✅ Stock daily signals regenerated${NC}"

echo ""
echo "Regenerating stock weekly signals..."
python3 loadbuysellweekly.py
echo -e "${GREEN}✅ Stock weekly signals regenerated${NC}"

echo ""
echo "Regenerating stock monthly signals..."
python3 loadbuysellmonthly.py
echo -e "${GREEN}✅ Stock monthly signals regenerated${NC}"

echo ""
echo "Regenerating ETF daily signals..."
python3 loadbuysell_etf_daily.py
echo -e "${GREEN}✅ ETF daily signals regenerated${NC}"

echo ""
echo "Regenerating ETF weekly signals..."
python3 loadbuysell_etf_weekly.py
echo -e "${GREEN}✅ ETF weekly signals regenerated${NC}"

echo ""
echo "Regenerating ETF monthly signals..."
python3 loadbuysell_etf_monthly.py
echo -e "${GREEN}✅ ETF monthly signals regenerated${NC}"

# STEP 4: Verification
echo ""
echo -e "${YELLOW}STEP 4: VERIFICATION...${NC}"
python3 << 'PYEOF'
import psycopg2
import os
from dotenv import load_dotenv

load_dotenv('.env.local')
conn = psycopg2.connect(
    host=os.environ.get("DB_HOST", "localhost"),
    port=int(os.environ.get("DB_PORT", 5432)),
    user=os.environ.get("DB_USER", "postgres"),
    password=os.environ.get("DB_PASSWORD", "password"),
    dbname=os.environ.get("DB_NAME", "stocks")
)
cur = conn.cursor()

# Check for remaining duplicates
cur.execute("""
    SELECT COUNT(*)
    FROM (
        SELECT symbol, date, signal, COUNT(*)
        FROM buy_sell_daily
        WHERE signal IN ('Buy', 'Sell')
        GROUP BY symbol, date, signal
        HAVING COUNT(*) > 1
    ) t
""")

dup_count = cur.fetchone()[0]

if dup_count == 0:
    print("✅ NO DUPLICATES FOUND - Data integrity restored!")
else:
    print(f"⚠️  WARNING: {dup_count} duplicate signals still exist")

# Check signal counts
cur.execute("SELECT COUNT(*) FROM buy_sell_daily WHERE signal IN ('Buy', 'Sell')")
count = cur.fetchone()[0]
print(f"✅ Total signals regenerated: {count}")

cur.close()
conn.close()
PYEOF

echo ""
echo "================================================================================"
echo -e "${GREEN}✅ RESTORATION COMPLETE${NC}"
echo "================================================================================"
echo ""
echo "Next steps:"
echo "1. Verify signals now match TradingView"
echo "2. Commit changes: git add -A && git commit -m 'Fix: Restore complete price data and regenerate signals'"
echo "3. Validate with: python3 /home/stocks/algo/verify_signals_debug.py ABNB"
echo ""
