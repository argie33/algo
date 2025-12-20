#!/bin/bash
export DB_HOST=localhost
export DB_USER=stocks
export DB_PASSWORD=bed0elAn
export DB_NAME=stocks

echo "=============================================="
echo "🚀 FINANCIAL DATA LOADERS - COMPREHENSIVE RUN"
echo "=============================================="
echo "Time: $(date)"
echo "DB: $DB_USER@$DB_HOST:$DB_NAME"
echo ""

LOADERS=(
    "loadannualincomestatement.py"
    "loadquarterlyincomestatement.py"
    "loadannualcashflow.py"
    "loadquarterlycashflow.py"
    "loadannualbalancesheet.py"
    "loadquarterlybalancesheet.py"
    "loadearningshistory.py"
    "loadttmincomestatement.py"
    "loadttmcashflow.py"
)

declare -A results
for loader in "${LOADERS[@]}"; do
    if [ -f "$loader" ]; then
        echo ""
        echo "━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━"
        echo "▶️  $(date '+%H:%M:%S') - Running: $loader"
        echo "━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━"
        
        if timeout 600 python3 "$loader" 2>&1 | tee "/tmp/${loader%.py}.log"; then
            results[$loader]="✅ SUCCESS"
            echo "✅ $loader completed successfully"
        else
            results[$loader]="❌ FAILED (exit: $?)"
            echo "❌ $loader failed with exit code $?"
        fi
    else
        results[$loader]="⚠️  NOT FOUND"
        echo "⚠️  Loader not found: $loader"
    fi
done

echo ""
echo "=============================================="
echo "📊 SUMMARY"
echo "=============================================="
for loader in "${LOADERS[@]}"; do
    echo "${results[$loader]} - $loader"
done
echo ""
echo "Completed at: $(date)"
