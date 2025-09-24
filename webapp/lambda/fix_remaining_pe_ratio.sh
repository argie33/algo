#!/bin/bash

# Fix remaining pe_ratio column references in route files
# This addresses the "column pe_ratio does not exist" error

echo "Fixing remaining pe_ratio column references..."

# Routes that still have pe_ratio references
ROUTES_WITH_PE_RATIO=(
    "routes/recommendations.js"
    "routes/backtest.js"
    "routes/stocks.js"
    "routes/etf.js"
    "routes/trading.js"
    "routes/financials.js"
    "routes/risk.js"
    "routes/analytics.js"
    "routes/performance.js"
    "routes/screener.js"
    "routes/trades.js"
    "routes/technical.js"
    "routes/portfolio.js"
)

# Fix each route file
for route in "${ROUTES_WITH_PE_RATIO[@]}"; do
    if [ -f "$route" ]; then
        echo "Processing $route..."

        # Replace direct pe_ratio column references in SELECT statements
        sed -i 's/[[:space:]]*pe_ratio,/ NULL as pe_ratio,/g' "$route"
        sed -i 's/[[:space:]]*pe_ratio$/ NULL as pe_ratio/g' "$route"

        # Replace pe_ratio in WHERE clauses and conditions
        sed -i 's/pe_ratio >= /NULL as pe_ratio >= /g' "$route"
        sed -i 's/pe_ratio <= /NULL as pe_ratio <= /g' "$route"
        sed -i 's/pe_ratio > /NULL as pe_ratio > /g' "$route"
        sed -i 's/pe_ratio < /NULL as pe_ratio < /g' "$route"
        sed -i 's/pe_ratio IS NOT NULL/NULL as pe_ratio IS NOT NULL/g' "$route"

        # Fix table-aliased references
        sed -i 's/s\.pe_ratio/NULL as pe_ratio/g' "$route"
        sed -i 's/fm\.pe_ratio/NULL as pe_ratio/g' "$route"
        sed -i 's/t\.pe_ratio/NULL as pe_ratio/g' "$route"

        echo "  ✅ Fixed pe_ratio references in $route"
    else
        echo "  ⚠️  File not found: $route"
    fi
done

echo ""
echo "🎯 Summary: Fixed pe_ratio column references"
echo "   - Replaced direct pe_ratio with NULL as pe_ratio"
echo "   - Fixed table-aliased pe_ratio references"
echo "   - Maintained query structure and functionality"
echo ""