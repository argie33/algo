#!/bin/bash
# Backfill Stage 2 symbol data (BRK.B, LEN.B, WSO.B)
# Run this to get all Stage 2 data current

echo "=================================="
echo "Backfilling Stage 2 Symbol Data"
echo "=================================="
echo ""

# Run the price daily loader which handles all symbols
echo "Updating daily prices for all symbols including BRK.B, LEN.B, WSO.B..."
python3 loadpricedaily.py

if [ $? -eq 0 ]; then
    echo ""
    echo "Success! Daily price data updated."
    echo ""
    echo "To verify:"
    python3 -c "
from algo_signals import SignalComputer
from datetime import date

print('Verifying Stage 2 symbols are now current:')
sc = SignalComputer()
test_date = date.today()

for symbol in ['BRK.B', 'LEN.B', 'WSO.B']:
    try:
        result = sc.minervini_trend_template(symbol, test_date)
        print(f'  {symbol}: OK (can run signals)')
    except Exception as e:
        print(f'  {symbol}: ERROR - {str(e)[:50]}')
    "
else
    echo "ERROR: Data loader failed!"
    exit 1
fi
