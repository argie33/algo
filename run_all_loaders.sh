#!/bin/bash

# Master Data Loader Shell Script Wrapper
# Runs all essential loaders for Portfolio Dashboard

set -e  # Exit on error

cd /home/stocks/algo

echo "=========================================="
echo "  STARTING MASTER DATA LOADER"
echo "=========================================="
echo ""
echo "This will populate your portfolio dashboard with REAL DATA from:"
echo "  ✓ Alpaca (portfolio & prices)"
echo "  ✓ Company Database (sectors & fundamentals)"
echo "  ✓ Stock Scores (quality metrics)"
echo "  ✓ Trading Signals (buy/sell signals)"
echo "  ✓ Options Data (covered calls)"
echo "  ✓ Market Sentiment"
echo ""
echo "Estimated time: 20-40 minutes (depending on data size)"
echo ""

# Run the Python master loader
python3 run_all_data_loaders.py

exit_code=$?

echo ""
echo "=========================================="
if [ $exit_code -eq 0 ]; then
    echo "  ✅ ALL DATA LOADERS COMPLETED SUCCESSFULLY"
    echo "=========================================="
    echo ""
    echo "Next steps:"
    echo "  1. Refresh your Portfolio Dashboard"
    echo "  2. All metrics should now show REAL DATA"
    echo "  3. No more synthetic values or blanks"
    echo ""
else
    echo "  ❌ SOME LOADERS FAILED"
    echo "=========================================="
    echo ""
    echo "See above for which loaders failed."
    echo "Run individual loaders to debug:"
    echo "  python3 loadalpacaportfolio.py"
    echo "  python3 loadstockscores.py"
    echo "  python3 loadbuyselldaily.py"
    echo ""
fi

exit $exit_code
