#!/bin/bash
export DB_HOST=localhost
export DB_USER=stocks
export DB_PASSWORD=bed0elAn
export DB_NAME=stocks

echo "=========================================="
echo "Running Financial Data Loaders"
echo "=========================================="

for loader in loadannualincomestatement.py loadquarterlyincomestatement.py loadearningshistory.py; do
    if [ -f "$loader" ]; then
        echo ""
        echo "▶️  Running: $loader"
        timeout 300 python3 "$loader" 2>&1 | tail -30 &
    fi
done

wait
echo ""
echo "All loaders completed!"
