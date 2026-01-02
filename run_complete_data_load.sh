#!/bin/bash
# Complete Data Loading Pipeline
# Runs loaddailycompanydata.py first, then loadstockscores.py sequentially

set -e  # Exit on any error

cd /home/stocks/algo

echo "=========================================="
echo "PHASE 1: Loading Company Data + Earnings"
echo "=========================================="
echo "Starting: $(date)"
echo ""

python3 loaddailycompanydata.py
PHASE1_EXIT=$?

if [ $PHASE1_EXIT -ne 0 ]; then
    echo "❌ PHASE 1 FAILED - Company data loader exited with code $PHASE1_EXIT"
    exit 1
fi

echo ""
echo "=========================================="
echo "PHASE 1 COMPLETE: $(date)"
echo "=========================================="
echo ""

# Verify earnings data was loaded
EARNINGS_COUNT=$(psql -h localhost -U stocks -d stocks -t -c "SELECT COUNT(*) FROM earnings;" 2>/dev/null || echo "0")
echo "Earnings table now has: $EARNINGS_COUNT rows"

if [ "$EARNINGS_COUNT" -eq "0" ]; then
    echo "⚠️  WARNING: Earnings table is still empty! Stock scores may be incomplete."
fi

echo ""
echo "=========================================="
echo "PHASE 2: Calculating Stock Scores"
echo "=========================================="
echo "Starting: $(date)"
echo ""

python3 loadstockscores.py
PHASE2_EXIT=$?

if [ $PHASE2_EXIT -ne 0 ]; then
    echo "❌ PHASE 2 FAILED - Stock scores loader exited with code $PHASE2_EXIT"
    exit 1
fi

echo ""
echo "=========================================="
echo "PHASE 2 COMPLETE: $(date)"
echo "=========================================="
echo ""

# Final verification
echo "=========================================="
echo "FINAL DATA VERIFICATION"
echo "=========================================="

psql -h localhost -U stocks -d stocks << 'EOF'
SELECT
  'earnings' as table_name,
  COUNT(*) as row_count,
  COUNT(DISTINCT symbol) as unique_stocks
FROM earnings
UNION ALL
SELECT
  'stock_scores',
  COUNT(*),
  COUNT(DISTINCT symbol)
FROM stock_scores
UNION ALL
SELECT
  'company_profile',
  COUNT(*),
  COUNT(DISTINCT symbol)
FROM company_profile
ORDER BY table_name;
EOF

echo ""
echo "✅ DATA LOADING COMPLETE: $(date)"
echo ""
echo "System is ready for use!"
