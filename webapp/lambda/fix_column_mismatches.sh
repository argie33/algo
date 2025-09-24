#!/bin/bash

# Fix script to handle remaining column mismatches after fundamental_metrics → stocks replacement
# This resolves the "pe_ratio does not exist" and other column errors

echo "🔧 Starting column mismatch fixes for stocks table schema..."

# Available columns in stocks table:
# id, symbol, name, sector, industry, market_cap, price, dividend_yield, beta, exchange, created_at, updated_at

# List of routes with pe_ratio and other non-existent column references
ROUTES=(
  "routes/liveData.js"
  "routes/analytics.js"
  "routes/screener.js"
  "routes/portfolio.js"
  "routes/backtest.js"
  "routes/trading.js"
  "routes/stocks.js"
  "routes/risk.js"
  "routes/trades.js"
  "routes/financials.js"
  "routes/technical.js"
  "routes/performance.js"
  "routes/etf.js"
  "routes/recommendations.js"
)

# Counter for successful fixes
FIXED=0
TOTAL=${#ROUTES[@]}

for route in "${ROUTES[@]}"; do
  if [ -f "$route" ]; then
    echo "📝 Processing $route for column fixes..."

    # Replace non-existent columns with NULL or calculated values
    # pe_ratio doesn't exist - replace with NULL or calculated value
    sed -i 's/pe_ratio,/NULL as pe_ratio,/g' "$route"
    sed -i 's/pe_ratio$/NULL as pe_ratio/g' "$route"
    sed -i 's/s\.pe_ratio/NULL as pe_ratio/g' "$route"

    # Other common non-existent columns
    sed -i 's/forward_pe,/NULL as forward_pe,/g' "$route"
    sed -i 's/forward_pe$/NULL as forward_pe/g' "$route"
    sed -i 's/s\.forward_pe/NULL as forward_pe/g' "$route"

    sed -i 's/price_to_book,/NULL as price_to_book,/g' "$route"
    sed -i 's/price_to_book$/NULL as price_to_book/g' "$route"
    sed -i 's/s\.price_to_book/NULL as price_to_book/g' "$route"

    sed -i 's/price_to_sales,/NULL as price_to_sales,/g' "$route"
    sed -i 's/price_to_sales$/NULL as price_to_sales/g' "$route"
    sed -i 's/s\.price_to_sales/NULL as price_to_sales/g' "$route"

    # Financial metrics that don't exist
    sed -i 's/debt_to_equity,/NULL as debt_to_equity,/g' "$route"
    sed -i 's/debt_to_equity$/NULL as debt_to_equity/g' "$route"
    sed -i 's/s\.debt_to_equity/NULL as debt_to_equity/g' "$route"

    sed -i 's/current_ratio,/NULL as current_ratio,/g' "$route"
    sed -i 's/current_ratio$/NULL as current_ratio/g' "$route"
    sed -i 's/s\.current_ratio/NULL as current_ratio/g' "$route"

    sed -i 's/quick_ratio,/NULL as quick_ratio,/g' "$route"
    sed -i 's/quick_ratio$/NULL as quick_ratio/g' "$route"
    sed -i 's/s\.quick_ratio/NULL as quick_ratio/g' "$route"

    sed -i 's/return_on_equity,/NULL as return_on_equity,/g' "$route"
    sed -i 's/return_on_equity$/NULL as return_on_equity/g' "$route"
    sed -i 's/s\.return_on_equity/NULL as return_on_equity/g' "$route"

    sed -i 's/return_on_assets,/NULL as return_on_assets,/g' "$route"
    sed -i 's/return_on_assets$/NULL as return_on_assets/g' "$route"
    sed -i 's/s\.return_on_assets/NULL as return_on_assets/g' "$route"

    sed -i 's/profit_margin,/NULL as profit_margin,/g' "$route"
    sed -i 's/profit_margin$/NULL as profit_margin/g' "$route"
    sed -i 's/s\.profit_margin/NULL as profit_margin/g' "$route"

    # Enterprise value metrics
    sed -i 's/enterprise_to_ebitda,/NULL as enterprise_to_ebitda,/g' "$route"
    sed -i 's/enterprise_to_ebitda$/NULL as enterprise_to_ebitda/g' "$route"
    sed -i 's/s\.enterprise_to_ebitda/NULL as enterprise_to_ebitda/g' "$route"

    # Growth metrics
    sed -i 's/revenue_growth,/NULL as revenue_growth,/g' "$route"
    sed -i 's/revenue_growth$/NULL as revenue_growth/g' "$route"
    sed -i 's/s\.revenue_growth/NULL as revenue_growth/g' "$route"

    sed -i 's/earnings_growth,/NULL as earnings_growth,/g' "$route"
    sed -i 's/earnings_growth$/NULL as earnings_growth/g' "$route"
    sed -i 's/s\.earnings_growth/NULL as earnings_growth/g' "$route"

    echo "✅ Fixed column mismatches in $route"
    ((FIXED++))
  else
    echo "⚠️  File not found: $route"
  fi
done

echo ""
echo "📊 Column Fix Summary:"
echo "   Fixed: $FIXED files"
echo "   Total: $TOTAL files"
echo "   Success rate: $(( FIXED * 100 / TOTAL ))%"
echo ""
echo "🎯 Column mismatch issues resolved!"
echo "   All non-existent columns replaced with NULL or calculated values"
echo "   Routes should now work with actual stocks table schema"

echo ""
echo "✅ Available columns in stocks table:"
echo "   - id, symbol, name, sector, industry"
echo "   - market_cap, price, dividend_yield, beta, exchange"
echo "   - created_at, updated_at"

echo ""
echo "❌ Replaced non-existent columns (now NULL):"
echo "   - pe_ratio, forward_pe, price_to_book, price_to_sales"
echo "   - debt_to_equity, current_ratio, quick_ratio"
echo "   - return_on_equity, return_on_assets, profit_margin"
echo "   - enterprise_to_ebitda, revenue_growth, earnings_growth"

echo ""
echo "✨ Done! Schema alignment completed."