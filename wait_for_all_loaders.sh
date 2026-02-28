#!/bin/bash
# Wait for ALL loaders to complete and report final status

echo "════════════════════════════════════════════════════════════════"
echo "🚀 WAITING FOR ALL DATA LOADERS TO COMPLETE"
echo "════════════════════════════════════════════════════════════════"
echo ""

# Function to check if a loader is running
is_loader_running() {
    ps aux | grep "python3.*load" | grep -v grep | grep -q "$1"
}

# Get all loaders
loaders=(
    "loadstockscores"
    "loadpricedaily"
    "loadfactormetrics"
    "loadbuysell_etf_daily"
    "loadannualincomestatement"
    "loadannualbalancesheet"
    "loadannualcashflow"
    "loadearningshistory"
    "loadearningsrevisions"
    "loadanalystsentiment"
    "loadanalystupgradedowngrade"
    "loadmarket"
    "loadmarketindices"
    "loadbenchmark"
    "loadsectorranking"
    "loaddailycompanydata"
    "loadfeargreed"
    "loadecondata"
    "loadnews"
    "loadsecfilings"
    "loadaaiidata"
)

start_time=$(date +%s)

while true; do
    running=0
    completed=()
    failed=()

    for loader in "${loaders[@]}"; do
        if is_loader_running "$loader"; then
            running=$((running + 1))
            echo -n "⏳"
        elif [ -f "/home/arger/algo/loader_logs/${loader}.log" ]; then
            completed+=("$loader")
            echo -n "✅"
        else
            failed+=("$loader")
            echo -n "❌"
        fi
    done

    current_time=$(date +%s)
    elapsed=$((current_time - start_time))
    elapsed_mins=$((elapsed / 60))

    if [ $running -eq 0 ]; then
        echo ""
        echo ""
        echo "════════════════════════════════════════════════════════════════"
        echo "✅ ALL LOADERS COMPLETE - $(date)"
        echo "════════════════════════════════════════════════════════════════"
        echo "Elapsed time: ${elapsed_mins} minutes"
        echo ""
        echo "Completed: ${#completed[@]}"
        for c in "${completed[@]}"; do
            echo "  ✅ $c"
        done
        echo ""
        break
    fi

    echo " [$running running | ${elapsed_mins}m]"
    sleep 30
done

echo ""
echo "════════════════════════════════════════════════════════════════"
echo "📊 DATA LOAD SUMMARY"
echo "════════════════════════════════════════════════════════════════"

for f in /home/arger/algo/loader_logs/load*.log; do
    name=$(basename "$f" .log)
    lines=$(wc -l < "$f")

    # Check for errors or success
    if grep -q "successfully\|Successfully\|SUCCESS\|Complete\|complete" "$f" 2>/dev/null; then
        status="✅"
    elif grep -q "ERROR\|error\|Error\|FAILED\|failed" "$f" 2>/dev/null; then
        status="⚠️"
    else
        status="⏳"
    fi

    printf "%s %-40s (%4d lines)\n" "$status" "$name" "$lines"
done

echo ""
echo "Detailed logs: /home/arger/algo/loader_logs/"
echo "════════════════════════════════════════════════════════════════"
