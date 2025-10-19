#!/bin/bash

cd /home/stocks/algo/webapp/lambda

# Find all integration test files with jest.mock() and remove duplicate query declarations
find tests/integration -name "*.test.js" -type f | while read file; do
  # Check if file has jest.mock and const { query } = require
  if grep -q "jest.mock" "$file" && grep -q "const.*query.*require.*database" "$file"; then
    # Remove the const { query } = require line(s)
    sed -i '/const.*{\s*query\s*}\s*=\s*require.*database/d' "$file"
    echo "Fixed: $file"
  fi
done

echo "✅ Removed duplicate query declarations"
