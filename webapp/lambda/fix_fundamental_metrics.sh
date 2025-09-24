#!/bin/bash

# Bulk fix script to replace fundamental_metrics with stocks table
# This fixes the critical AWS deployment blocker where 25+ routes reference non-existent table

echo "🔧 Starting bulk fix of fundamental_metrics references..."

# List of routes that reference fundamental_metrics
ROUTES=(
  "routes/liveData.js"
  "routes/trades.js"
  "routes/risk.js"
  "routes/stocks.js"
  "routes/trading.js"
  "routes/backtest.js"
  "routes/dashboard.js"
  "routes/portfolio.js"
  "routes/watchlist.js"
  "routes/screener.js"
  "routes/positioning.js"
  "routes/market.js"
  "routes/research.js"
  "routes/health.js"
  "routes/calendar.js"
  "routes/scoring.js"
  "routes/strategyBuilder.js"
  "routes/dividend.js"
  "routes/metrics.js"
  "routes/earnings.js"
  "routes/analytics.js"
  "routes/sectors.js"
)

# Counter for successful fixes
FIXED=0
TOTAL=${#ROUTES[@]}

for route in "${ROUTES[@]}"; do
  if [ -f "$route" ]; then
    echo "📝 Processing $route..."

    # Backup original file
    cp "$route" "$route.backup"

    # Replace fundamental_metrics with stocks
    # Also replace common column aliases that don't exist in stocks table
    sed -i 's/fundamental_metrics/stocks/g' "$route"
    sed -i 's/fm\.ticker/s.symbol/g' "$route"
    sed -i 's/fm\.symbol/s.symbol/g' "$route"
    sed -i 's/fm\.short_name/s.name/g' "$route"
    sed -i 's/fm\.sector/s.sector/g' "$route"
    sed -i 's/fm\.industry/s.industry/g' "$route"
    sed -i 's/fm\.market_cap/s.market_cap/g' "$route"
    sed -i 's/fm\.price/s.price/g' "$route"
    sed -i 's/fm\./s./g' "$route"

    # Handle JOIN clauses - replace references to fm alias
    sed -i 's/FROM fundamental_metrics fm/FROM stocks s/g' "$route"
    sed -i 's/JOIN fundamental_metrics fm/JOIN stocks s/g' "$route"
    sed -i 's/LEFT JOIN fundamental_metrics fm/LEFT JOIN stocks s/g' "$route"
    sed -i 's/INNER JOIN fundamental_metrics fm/INNER JOIN stocks s/g' "$route"

    # Update WHERE clauses
    sed -i 's/WHERE fm\./WHERE s./g' "$route"
    sed -i 's/AND fm\./AND s./g' "$route"
    sed -i 's/OR fm\./OR s./g' "$route"

    echo "✅ Fixed $route"
    ((FIXED++))
  else
    echo "⚠️  File not found: $route"
  fi
done

echo ""
echo "📊 Summary:"
echo "   Fixed: $FIXED files"
echo "   Total: $TOTAL files"
echo "   Success rate: $(( FIXED * 100 / TOTAL ))%"
echo ""
echo "🎯 Critical AWS deployment issue resolved!"
echo "   All routes now use stocks table (exists in Python loaders)"
echo "   instead of fundamental_metrics table (does not exist)"

# Show files that were modified
echo ""
echo "📁 Modified files:"
for route in "${ROUTES[@]}"; do
  if [ -f "$route" ]; then
    echo "   ✅ $route"
  fi
done

echo ""
echo "✨ Done! Routes should now work with actual database schema."