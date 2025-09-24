#!/bin/bash

# Fix SQL syntax errors caused by the column mismatch script
echo "🔧 Fixing SQL syntax errors from column replacements..."

# Find all .js files in routes and fix syntax issues
find routes -name "*.js" -not -name "*.backup" | while read file; do
  echo "📝 Fixing SQL syntax in $file..."

  # Fix double NULL issues
  sed -i 's/NULL as NULL as /NULL as /g' "$file"
  sed -i 's/row\.NULL as /row\./g' "$file"
  sed -i 's/s\.NULL as /NULL as /g' "$file"
  sed -i 's/ratiosData\.NULL as /ratiosData\./g' "$file"
  sed -i 's/ratioData\.NULL as /ratioData\./g' "$file"
  sed -i 's/metrics\.NULL as /metrics\./g' "$file"

  # Fix specific broken patterns
  sed -i 's/NULL as pe_ratio >= /pe_ratio >= /g' "$file"
  sed -i 's/NULL as pe_ratio <= /pe_ratio <= /g' "$file"
  sed -i 's/NULL as pe_ratio > /pe_ratio > /g' "$file"
  sed -i 's/NULL as pe_ratio IS NOT NULL/pe_ratio IS NOT NULL/g' "$file"
  sed -i 's/\.pe_ratio\./\.pe_ratio/g' "$file"

  # Fix filter comparisons
  sed -i 's/NULL as revenue_growth >= /revenue_growth >= /g' "$file"
  sed -i 's/NULL as revenue_growth <= /revenue_growth <= /g' "$file"
  sed -i 's/NULL as earnings_growth >= /earnings_growth >= /g' "$file"
  sed -i 's/NULL as earnings_growth <= /earnings_growth <= /g' "$file"

  # Fix property access patterns
  sed -i 's/\.NULL as pe_ratio/\.pe_ratio/g' "$file"
  sed -i 's/\.NULL as forward_pe/\.forward_pe/g' "$file"
  sed -i 's/\.NULL as price_to_book/\.price_to_book/g' "$file"
  sed -i 's/\.NULL as price_to_sales/\.price_to_sales/g' "$file"
  sed -i 's/\.NULL as debt_to_equity/\.debt_to_equity/g' "$file"
  sed -i 's/\.NULL as current_ratio/\.current_ratio/g' "$file"
  sed -i 's/\.NULL as quick_ratio/\.quick_ratio/g' "$file"
  sed -i 's/\.NULL as revenue_growth/\.revenue_growth/g' "$file"
  sed -i 's/\.NULL as earnings_growth/\.earnings_growth/g' "$file"

  # Fix specific broken SQL expressions
  sed -i 's/NULL as pe_ratio/pe_ratio/g' "$file"
  sed -i 's/pe_ratio pe_ratio/pe_ratio/g' "$file"

  echo "✅ Fixed SQL syntax in $file"
done

echo ""
echo "🎯 SQL syntax fixes completed!"
echo "✅ Removed double NULL patterns"
echo "✅ Fixed property access patterns"
echo "✅ Fixed comparison operators"
echo ""
echo "📊 Routes should now have valid SQL syntax while maintaining NULL column handling"