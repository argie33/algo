#!/bin/bash

# ==============================================================================
# SAFE SEQUENTIAL LOADER - Prevents System Crashes from Resource Exhaustion
# ==============================================================================
# Problem: Running multiple loaders in parallel (4 daily + 1 weekly + signal with 5 workers)
#          caused system thrashing with only 99MB free RAM on 3.8GB system
# Solution: Run loaders SEQUENTIALLY with memory monitoring
# ==============================================================================

set -e  # Exit on any error

SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
cd "$SCRIPT_DIR"

# Export database credentials
export PGPASSWORD="${DB_PASSWORD:-bed0elAn}"
export DB_HOST="${DB_HOST:-localhost}"
export DB_USER="${DB_USER:-stocks}"
export DB_PASSWORD="${DB_PASSWORD:-bed0elAn}"
export DB_NAME="${DB_NAME:-stocks}"

# ==============================================================================
# SAFETY CHECKS & MONITORING
# ==============================================================================

check_system_resources() {
    local min_free_mb=300
    local free_mb=$(free -h | awk '/^Mem:/ {print int($7)}')
    local load_avg=$(uptime | awk -F'load average:' '{print $2}' | cut -d, -f1 | xargs)

    echo "════════════════════════════════════════════════════════════════"
    echo "System Resources Check:"
    echo "  Free RAM: ${free_mb}MB (minimum required: ${min_free_mb}MB)"
    echo "  Load Average: ${load_avg}"
    echo "════════════════════════════════════════════════════════════════"

    if (( $(echo "$load_avg > 5" | bc -l) )); then
        echo "⚠️  WARNING: System load average is high (${load_avg} on 8 cores)"
        echo "   Waiting 30 seconds for system to cool down..."
        sleep 30
    fi

    if [[ $free_mb -lt $min_free_mb ]]; then
        echo "❌ ERROR: Insufficient free memory (${free_mb}MB < ${min_free_mb}MB)"
        echo "   Please free up some memory and try again"
        return 1
    fi

    return 0
}

monitor_loader_start() {
    local loader_name=$1
    echo ""
    echo "═══════════════════════════════════════════════════════════════════"
    echo "▶️  Starting: $loader_name"
    echo "═══════════════════════════════════════════════════════════════════"
    check_system_resources
}

monitor_loader_end() {
    local loader_name=$1
    local start_time=$2
    local end_time=$(date +%s)
    local duration=$((end_time - start_time))

    echo "✅ Completed: $loader_name (${duration}s)"
    free -h | grep "Mem:" | awk '{print "   RAM: " $2 " total, " $3 " used, " $4 " free"}'
    echo ""
}

# ==============================================================================
# MAIN LOADER SEQUENCE
# ==============================================================================

main() {
    echo "🚀 Starting SAFE SEQUENTIAL DATA LOADERS - $(date)"

    # Check baseline system state
    check_system_resources

    # LOADER 1: Stock Symbols (fast, required first)
    if [[ ! -f ".loader_symbols_done" ]]; then
        start=$(date +%s)
        monitor_loader_start "Stock Symbols (loadstocksymbols.py)"
        python3 loadstocksymbols.py 2>&1 | tee /tmp/symbols.log
        monitor_loader_end "Stock Symbols" $start
        touch ".loader_symbols_done"
    else
        echo "⊘ Skipping Stock Symbols (already loaded)"
    fi

    # LOADER 2: Technical Indicators (moderate, required before scores)
    if [[ ! -f ".loader_technical_done" ]]; then
        start=$(date +%s)
        monitor_loader_start "Technical Indicators (loadtechnicalindicators.py)"
        python3 loadtechnicalindicators.py 2>&1 | tee /tmp/technical.log
        monitor_loader_end "Technical Indicators" $start
        touch ".loader_technical_done"
    else
        echo "⊘ Skipping Technical Indicators (already loaded)"
    fi

    # LOADER 3: Daily Prices (LARGEST - run single instance only)
    start=$(date +%s)
    monitor_loader_start "Daily Prices (loadpricedaily.py) - SINGLE INSTANCE ONLY"
    python3 loadpricedaily.py 2>&1 | tee /tmp/price_daily.log
    monitor_loader_end "Daily Prices" $start

    # LOADER 4: Weekly Prices (sequential, after daily completes)
    start=$(date +%s)
    monitor_loader_start "Weekly Prices (loadpriceweekly.py)"
    python3 loadpriceweekly.py 2>&1 | tee /tmp/price_weekly.log
    monitor_loader_end "Weekly Prices" $start

    # LOADER 5: Monthly Prices (sequential)
    start=$(date +%s)
    monitor_loader_start "Monthly Prices (loadpricemonthly.py)"
    python3 loadpricemonthly.py 2>&1 | tee /tmp/price_monthly.log
    monitor_loader_end "Monthly Prices" $start

    # LOADER 6: Stock Scores (requires prices & technical data)
    start=$(date +%s)
    monitor_loader_start "Stock Scores (loadstockscores.py)"
    python3 loadstockscores.py 2>&1 | tee /tmp/scores.log
    monitor_loader_end "Stock Scores" $start

    # LOADER 7: Buy/Sell Signals (RESOURCE INTENSIVE - 5 workers max)
    start=$(date +%s)
    monitor_loader_start "Buy/Sell Signals (loadbuyselldaily.py) - REDUCED TO 3 WORKERS"
    python3 loadbuyselldaily.py 2>&1 | tee /tmp/signals.log
    monitor_loader_end "Buy/Sell Signals" $start

    # ==============================================================================
    # SUMMARY
    # ==============================================================================
    echo "════════════════════════════════════════════════════════════════════"
    echo "✅ ALL LOADERS COMPLETED SUCCESSFULLY - $(date)"
    echo "════════════════════════════════════════════════════════════════════"
    free -h | grep "Mem:" | awk '{print "Final RAM: " $2 " total, " $3 " used, " $4 " free"}'

    echo ""
    echo "📊 Loader Status:"
    echo "  ✅ Stock Symbols"
    echo "  ✅ Technical Indicators"
    echo "  ✅ Daily Prices"
    echo "  ✅ Weekly Prices"
    echo "  ✅ Monthly Prices"
    echo "  ✅ Stock Scores"
    echo "  ✅ Buy/Sell Signals"
    echo ""
    echo "📁 Log files:"
    ls -lh /tmp/*.log 2>/dev/null | awk '{print "  " $9 " (" $5 ")"}'
    echo ""
    echo "🎯 Next step: Monitor GitHub Actions deployment at:"
    echo "   https://github.com/argie33/algo/actions"
}

main "$@"
