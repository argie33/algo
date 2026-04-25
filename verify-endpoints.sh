#!/bin/bash
echo "Checking endpoint/table alignment..."
echo "======================================="

echo "Sectors route expects:"
grep -h "FROM\|TABLE" webapp/lambda/routes/sectors.js 2>/dev/null | grep -E "sector|industry" | head -5

echo ""
echo "Financials route expects:"
grep -h "FROM\|annual_\|quarterly_" webapp/lambda/routes/financials.js 2>/dev/null | head -5

echo ""
echo "Signals route expects:"
grep -h "buy_sell_" webapp/lambda/routes/signals.js 2>/dev/null | head -3

echo ""
echo "Price route expects:"
grep -h "price_" webapp/lambda/routes/price.js 2>/dev/null | head -3
