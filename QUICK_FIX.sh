#!/bin/bash
# Quick fix: Wait for current loaders, then complete data load

echo "STEP 1: Waiting for current loaders to finish..."
sleep 5
while pgrep -f "loaddailycompanydata.py|loadstockscores.py" > /dev/null; do
    RUNNING=$(pgrep -f "loaddailycompanydata.py|loadstockscores.py" | wc -l)
    echo "  Still running: $RUNNING loaders..."
    sleep 10
done
echo "✅ Current loaders complete"

echo ""
echo "STEP 2: Checking earnings table..."
EARNINGS_COUNT=$(psql -h localhost -U stocks -d stocks -t -c "SELECT COUNT(*) FROM earnings;")
echo "  Earnings rows: $EARNINGS_COUNT"

if [ "$EARNINGS_COUNT" -lt 10000 ]; then
    echo "  ❌ Earnings not loaded, re-running loaddailycompanydata..."
    python3 /home/stocks/algo/loaddailycompanydata.py
fi

echo ""
echo "STEP 3: Running loadstockscores..."
python3 /home/stocks/algo/loadstockscores.py

echo ""
echo "STEP 4: Updating price data to current..."
python3 /home/stocks/algo/loadpricedaily.py
python3 /home/stocks/algo/loadpricemonthly.py

echo ""
echo "STEP 5: Loading missing ETF data..."
python3 /home/stocks/algo/loadetfpriceweekly.py
python3 /home/stocks/algo/loadetfpricemonthly.py

echo ""
echo "✅ ALL DONE! Running verification..."
/home/stocks/algo/verify_all_data.sh

