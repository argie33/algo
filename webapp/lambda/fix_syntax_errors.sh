#!/bin/bash

# Fix syntax errors introduced by pe_ratio script

echo "Fixing syntax errors from pe_ratio script..."

find routes/ -name "*.js" -type f | while read file; do
    echo "Processing $file..."

    # Fix broken patterns like "row. NULL as pe_ratio"
    sed -i 's/row\.\s*NULL as pe_ratio/row.pe_ratio/g' "$file"
    sed -i 's/stock\.\s*NULL as pe_ratio/stock.pe_ratio/g' "$file"
    sed -i 's/s\.\s*NULL as pe_ratio/s.pe_ratio/g' "$file"
    sed -i 's/fm\.\s*NULL as pe_ratio/fm.pe_ratio/g' "$file"
    sed -i 's/t\.\s*NULL as pe_ratio/t.pe_ratio/g' "$file"

    # Fix patterns with extra spaces
    sed -i 's/\.\s*NULL as pe_ratio/.pe_ratio/g' "$file"

    # Fix patterns where NULL was inserted incorrectly
    sed -i 's/pe_ratio: NULL as pe_ratio/pe_ratio: null/g' "$file"
    sed -i 's/pe_ratio: row\.pe_ratio/pe_ratio: null/g' "$file"
    sed -i 's/pe_ratio: stock\.pe_ratio/pe_ratio: null/g' "$file"
    sed -i 's/pe_ratio: s\.pe_ratio/pe_ratio: null/g' "$file"
    sed -i 's/pe_ratio: fm\.pe_ratio/pe_ratio: null/g' "$file"

    echo "  ✅ Fixed syntax errors in $file"
done

echo ""
echo "🎯 Summary: Fixed syntax errors from pe_ratio script"
echo "   - Fixed broken table alias patterns"
echo "   - Replaced property access with null values"
echo "   - Maintained proper JavaScript syntax"
echo ""