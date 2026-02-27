#!/bin/bash

# ==============================================================================
# TRACE AND LOAD - Safe Sequential Loader with Comprehensive Tracing
# ==============================================================================
# Combines safe sequential loading with detailed system and loader tracing
# ==============================================================================

set -e

SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
cd "$SCRIPT_DIR"

# Initialize tracing
source "$SCRIPT_DIR/LOADER_TRACER.sh" start 2>/dev/null || true
source "$SCRIPT_DIR/SYSTEM_MONITOR.sh" 2>/dev/null || true

# Export database credentials
export PGPASSWORD="${DB_PASSWORD:-bed0elAn}"
export DB_HOST="${DB_HOST:-localhost}"
export DB_USER="${DB_USER:-stocks}"
export DB_PASSWORD="${DB_PASSWORD:-bed0elAn}"
export DB_NAME="${DB_NAME:-stocks}"

# Logging
TRACE_DIR="/home/arger/algo/logs/loader_traces"
EXECUTION_LOG="$TRACE_DIR/execution_log.txt"
mkdir -p "$TRACE_DIR"

echo "=== TRACE AND LOAD SESSION ===" | tee -a "$EXECUTION_LOG"
echo "Started: $(date +'%Y-%m-%d %H:%M:%S')" | tee -a "$EXECUTION_LOG"
echo "" | tee -a "$EXECUTION_LOG"

# ==============================================================================
# SAFETY CHECKS
# ==============================================================================

check_system_resources() {
    local min_free_mb=300
    local free_mb=$(free -h | awk '/^Mem:/ {print int($7)}')
    local load_avg=$(uptime | awk -F'load average:' '{print $2}' | cut -d, -f1 | xargs)
    local load_cores=$(grep -c "^processor" /proc/cpuinfo)

    echo "[$(date +'%H:%M:%S')] System Check: ${free_mb}MB free, load ${load_avg}, cores ${load_cores}"

    if [ "$free_mb" -lt "$min_free_mb" ]; then
        echo "❌ ERROR: Only ${free_mb}MB free RAM (need ${min_free_mb}MB)" | tee -a "$EXECUTION_LOG"
        return 1
    fi

    return 0
}

# ==============================================================================
# RUN LOADER WITH TRACING
# ==============================================================================

run_with_trace() {
    local loader_script="$1"
    local loader_name=$(basename "$loader_script" .py)

    if [ ! -f "$loader_script" ]; then
        echo "❌ Loader not found: $loader_script"
        return 1
    fi

    echo ""
    echo "━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━"
    echo "▶ Running: $loader_name"
    echo "━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━"

    # Log start
    local start_time=$(date +%s)
    echo "[$start_time] START $loader_name" >> "$EXECUTION_LOG"

    # Run loader
    local exit_code=0
    if python "$loader_script" 2>&1 | tee -a "$TRACE_DIR/${loader_name}.log"; then
        exit_code=0
        echo "✅ $loader_name completed successfully"
    else
        exit_code=$?
        echo "⚠️  $loader_name completed with exit code $exit_code"
    fi

    # Log end
    local end_time=$(date +%s)
    local duration=$((end_time - start_time))
    local minutes=$((duration / 60))
    local seconds=$((duration % 60))

    echo "[$end_time] END $loader_name (duration: ${minutes}m ${seconds}s, exit: $exit_code)" >> "$EXECUTION_LOG"
    echo "" >> "$EXECUTION_LOG"

    return "$exit_code"
}

# ==============================================================================
# MAIN EXECUTION
# ==============================================================================

main() {
    echo "Checking system resources..."
    if ! check_system_resources; then
        echo "❌ System check failed. Aborting."
        exit 1
    fi

    # Define loader sequence (safest order, lowest memory first)
    local loaders=(
        "./loadstocksymbols.py"
        "./loadstockscores.py"
        "./loadpriceweekly.py"
        "./loadpricemonthly.py"
        "./loadpricedaily.py"
        "./loadbuyselldaily.py"
        "./loadtechnicalindicators.py"
    )

    local total_loaders=${#loaders[@]}
    local completed=0
    local failed=0

    # Run each loader sequentially
    for loader_script in "${loaders[@]}"; do
        if [ -f "$loader_script" ]; then
            ((completed++))
            if ! run_with_trace "$loader_script"; then
                ((failed++))
            fi

            # Check resources between loaders
            if ! check_system_resources; then
                echo "⚠️  Warning: Low resources after loader. Waiting before next..."
                sleep 10
            fi
        fi
    done

    # Summary
    echo ""
    echo "━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━"
    echo "📊 EXECUTION SUMMARY"
    echo "━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━"
    echo "Total loaders run: $completed"
    echo "Failed loaders: $failed"
    echo "Success rate: $((100 * (completed - failed) / completed))%"
    echo ""
    echo "Completed: $(date +'%Y-%m-%d %H:%M:%S')"
    echo ""
    echo "View detailed logs:"
    echo "  cat $EXECUTION_LOG"
    echo "  cat $TRACE_DIR/*.log"
    echo ""

    # Log summary
    {
        echo "=== SESSION SUMMARY ==="
        echo "Total loaders: $completed"
        echo "Failed: $failed"
        echo "Completed: $(date +'%Y-%m-%d %H:%M:%S')"
        echo ""
    } >> "$EXECUTION_LOG"

    if [ "$failed" -eq 0 ]; then
        echo "✅ All loaders completed successfully!"
        return 0
    else
        echo "⚠️  Some loaders failed. Check logs for details."
        return 1
    fi
}

main "$@"
