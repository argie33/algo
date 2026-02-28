#!/bin/bash
# Real-time loader monitoring

echo "════════════════════════════════════════════════════════════════"
echo "📊 REAL-TIME LOADER MONITOR"
echo "════════════════════════════════════════════════════════════════"
echo "Started: $(date)"
echo ""

while true; do
    clear
    echo "════════════════════════════════════════════════════════════════"
    echo "📊 DATA LOADERS STATUS - $(date '+%H:%M:%S')"
    echo "════════════════════════════════════════════════════════════════"
    echo ""

    # Count running
    running=$(ps aux | grep "python3.*load" | grep -v grep | wc -l)

    if [ $running -gt 0 ]; then
        echo "Active loaders: $running"
        echo ""
        echo "Currently running:"
        ps aux | grep "python3.*load" | grep -v grep | awk '{print "  ⏳", $(NF)}' | sort
        echo ""

        # Show latest progress from major loaders
        echo "Progress Samples:"
        echo "────────────────────────────────────────────────────────────"

        for loader in loadpricedaily loadbuysell_etf_daily loaddailycompanydata loadnews; do
            logfile="/home/arger/algo/loader_logs/${loader}.log"
            if [ -f "$logfile" ]; then
                # Get last relevant line
                line=$(grep -E "Progress:|batch|Successfully|records loaded|complete" "$logfile" | tail -1)
                if [ ! -z "$line" ]; then
                    echo "  $loader:"
                    echo "    $line" | sed 's/^[0-9-]* [0-9:,]* - [A-Z]* - /    /'
                fi
            fi
        done

        echo "────────────────────────────────────────────────────────────"
        echo ""
        echo "Press Ctrl+C to exit, or wait for completion..."
        sleep 10
    else
        echo "✅ ALL LOADERS COMPLETED!"
        echo ""
        echo "📋 FINAL SUMMARY:"
        echo "────────────────────────────────────────────────────────────"

        completed=0
        failed=0

        for logfile in /home/arger/algo/loader_logs/load*.log; do
            name=$(basename "$logfile" .log)
            lines=$(wc -l < "$logfile")

            if grep -q "successfully\|Successfully\|SUCCESS\|complete\|Complete\|loaded\|Loaded" "$logfile" 2>/dev/null; then
                echo "✅ $name ($lines lines)"
                completed=$((completed + 1))
            elif [ $lines -lt 5 ]; then
                echo "❌ $name (ERROR - $lines lines)"
                failed=$((failed + 1))
            else
                echo "⚠️  $name ($lines lines)"
                completed=$((completed + 1))
            fi
        done

        echo "────────────────────────────────────────────────────────────"
        echo "✅ Completed: $completed"
        echo "❌ Failed: $failed"
        echo ""
        echo "All logs in: /home/arger/algo/loader_logs/"
        echo "════════════════════════════════════════════════════════════════"
        break
    fi
done
