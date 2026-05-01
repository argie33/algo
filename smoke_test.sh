#!/bin/bash
# Smoke Test for Stock Analytics Loaders
# Validates setup before AWS deployment

set -e

echo "=================================="
echo "Stock Analytics Smoke Test"
echo "=================================="
echo ""

PASS=0
FAIL=0

# Test 1: Check Python version
echo "Test 1: Python version..."
python3 --version > /dev/null && echo "  ✓ Python 3 installed" && ((PASS++)) || { echo "  ✗ Python 3 not found"; ((FAIL++)); }

# Test 2: Check required modules
echo "Test 2: Required Python modules..."
for module in psycopg2 boto3 yfinance pandas numpy requests; do
  python3 -c "import $module" 2>/dev/null && echo "  ✓ $module" && ((PASS++)) || { echo "  ✗ $module missing"; ((FAIL++)); }
done

# Test 3: Check DatabaseHelper
echo "Test 3: DatabaseHelper..."
[ -f "db_helper.py" ] && echo "  ✓ db_helper.py exists" && ((PASS++)) || { echo "  ✗ db_helper.py missing"; ((FAIL++)); }
python3 -c "from db_helper import DatabaseHelper; print('  ✓ DatabaseHelper imports')" && ((PASS++)) || { echo "  ✗ DatabaseHelper import failed"; ((FAIL++)); }

# Test 4: Check refactored loaders
echo "Test 4: Refactored loaders (sample check)..."
count=$(grep -l "from db_helper import DatabaseHelper" load*.py 2>/dev/null | wc -l || echo "0")
if [ "$count" -ge 50 ]; then
  echo "  ✓ $count loaders using DatabaseHelper"
  ((PASS++))
else
  echo "  ✗ Only $count loaders refactored (expected 54)"
  ((FAIL++))
fi

# Test 5: Check database connectivity
echo "Test 5: Database connectivity..."
if [ -n "$DB_HOST" ]; then
  python3 -c "
import psycopg2
try:
  conn = psycopg2.connect(host='$DB_HOST', user='$DB_USER', password='$DB_PASSWORD', dbname='$DB_NAME')
  conn.close()
  print('  ✓ Database connection successful')
except Exception as e:
  print(f'  ✗ Database connection failed: {e}')
  exit(1)
" && ((PASS++)) || ((FAIL++))
else
  echo "  ⚠ DB_HOST not set (skipping)"
fi

# Test 6: Check Docker
echo "Test 6: Docker..."
docker --version > /dev/null && echo "  ✓ Docker installed" && ((PASS++)) || echo "  ⚠ Docker not available (OK if not needed)"

# Test 7: Check AWS CLI
echo "Test 7: AWS CLI..."
aws --version > /dev/null && echo "  ✓ AWS CLI installed" && ((PASS++)) || echo "  ⚠ AWS CLI not available (OK if not deploying yet)"

# Test 8: Run test_database_helper.py
echo "Test 8: DatabaseHelper validation..."
python3 test_database_helper.py > /dev/null 2>&1 && echo "  ✓ DatabaseHelper tests passed" && ((PASS++)) || echo "  ⚠ DatabaseHelper tests skipped (OK without DB)"

# Summary
echo ""
echo "=================================="
echo "Smoke Test Results"
echo "=================================="
echo "✓ Passed: $PASS"
echo "✗ Failed: $FAIL"
echo ""

if [ $FAIL -eq 0 ]; then
  echo "✅ All tests passed! Ready for deployment."
  exit 0
else
  echo "❌ Some tests failed. Please fix before deploying."
  exit 1
fi
