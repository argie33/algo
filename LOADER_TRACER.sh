#!/bin/bash

# ==============================================================================
# LOADER EXECUTION TRACER - Detailed Logging of Data Loader Activity
# ==============================================================================
# Tracks:
# - Loader start/stop times
# - Resource usage (memory, CPU)
# - Error conditions
# - Completion status
# ==============================================================================

TRACE_DIR="/home/arger/algo/logs/loader_traces"
EXECUTION_LOG="$TRACE_DIR/execution_log.txt"
RESOURCE_LOG="$TRACE_DIR/resource_usage.log"
ERROR_LOG="$TRACE_DIR/errors.log"

mkdir -p "$TRACE_DIR"

# Export database credentials
export PGPASSWORD="${DB_PASSWORD:-bed0elAn}"
export DB_HOST="${DB_HOST:-localhost}"
export DB_USER="${DB_USER:-stocks}"
export DB_PASSWORD="${DB_PASSWORD:-bed0elAn}"
export DB_NAME="${DB_NAME:-stocks}"

# ==============================================================================
# FUNCTION: Log loader start
# ==============================================================================
log_loader_start() {
    local loader_name="$1"
    local timestamp=$(date +'%Y-%m-%d %H:%M:%S')
    local mem_before=$(free -h | awk '/^Mem:/ {print $4}')
    local load_before=$(uptime | awk -F'load average:' '{print $2}' | cut -d, -f1 | xargs)

    echo "[$timestamp] START: $loader_name" >> "$EXECUTION_LOG"
    echo "  Memory free before: $mem_before" >> "$EXECUTION_LOG"
    echo "  System load before: $load_before" >> "$EXECUTION_LOG"

    # Create a record file for this loader run
    echo "$timestamp" > "$TRACE_DIR/.$loader_name.start"
}

# ==============================================================================
# FUNCTION: Log loader completion
# ==============================================================================
log_loader_end() {
    local loader_name="$1"
    local exit_code="$2"
    local timestamp=$(date +'%Y-%m-%d %H:%M:%S')
    local mem_after=$(free -h | awk '/^Mem:/ {print $4}')
    local load_after=$(uptime | awk -F'load average:' '{print $2}' | cut -d, -f1 | xargs)

    if [ -f "$TRACE_DIR/.$loader_name.start" ]; then
        local start_time=$(cat "$TRACE_DIR/.$loader_name.start")
        local duration=$(($(date +%s) - $(date -d "$start_time" +%s)))
        local minutes=$((duration / 60))
        local seconds=$((duration % 60))

        echo "[$timestamp] END: $loader_name (exit code: $exit_code)" >> "$EXECUTION_LOG"
        echo "  Duration: ${minutes}m ${seconds}s" >> "$EXECUTION_LOG"
        echo "  Memory free after: $mem_after" >> "$EXECUTION_LOG"
        echo "  System load after: $load_after" >> "$EXECUTION_LOG"

        if [ "$exit_code" -ne 0 ]; then
            echo "  STATUS: FAILED ❌" >> "$EXECUTION_LOG"
        else
            echo "  STATUS: SUCCESS ✅" >> "$EXECUTION_LOG"
        fi
        echo "" >> "$EXECUTION_LOG"

        rm -f "$TRACE_DIR/.$loader_name.start"
    fi
}

# ==============================================================================
# FUNCTION: Run loader with tracing
# ==============================================================================
run_loader_traced() {
    local loader_script="$1"
    local loader_name=$(basename "$loader_script")

    log_loader_start "$loader_name"

    # Run the loader and capture output
    if bash "$loader_script" > "$TRACE_DIR/${loader_name}.log" 2>&1; then
        log_loader_end "$loader_name" 0
        echo "✅ $loader_name completed successfully"
        return 0
    else
        local exit_code=$?
        log_loader_end "$loader_name" "$exit_code"
        echo "❌ $loader_name failed with exit code $exit_code"

        # Log error details
        {
            echo "[$loader_name - $(date +'%Y-%m-%d %H:%M:%S')]"
            echo "Exit code: $exit_code"
            echo "Last 20 lines of output:"
            tail -20 "$TRACE_DIR/${loader_name}.log"
            echo ""
        } >> "$ERROR_LOG"

        return "$exit_code"
    fi
}

# ==============================================================================
# FUNCTION: Monitor resource usage during loader run
# ==============================================================================
monitor_resource_usage() {
    local loader_name="$1"
    local interval="${2:-5}"  # Check every 5 seconds

    {
        echo "=== Resource Usage for $loader_name ($(date +'%Y-%m-%d %H:%M:%S')) ==="
        echo "Timestamp | Mem Used | Mem Free | CPU % | Load Avg"
        echo "-----------|----------|----------|-------|----------"

        while [ -f "$TRACE_DIR/.$loader_name.start" ]; do
            local timestamp=$(date +'%H:%M:%S')
            local mem_used=$(free | awk '/^Mem:/ {printf "%.0f%%", ($3/$2)*100}')
            local mem_free=$(free -h | awk '/^Mem:/ {print $4}')
            local cpu_usage=$(ps aux | grep -E "python.*$loader_name" | grep -v grep | awk '{sum+=$3} END {printf "%.1f%%", sum}')
            local load_avg=$(uptime | awk -F'load average:' '{print $2}' | xargs)

            echo "$timestamp | $mem_used | $mem_free | $cpu_usage | $load_avg"
            sleep "$interval"
        done
    } >> "$RESOURCE_LOG"
}

# ==============================================================================
# FUNCTION: View execution summary
# ==============================================================================
view_summary() {
    echo ""
    echo "=== LOADER EXECUTION SUMMARY ==="
    echo ""
    echo "Total runs logged: $(wc -l < "$EXECUTION_LOG" 2>/dev/null || echo 0)"
    echo "Total errors logged: $(wc -l < "$ERROR_LOG" 2>/dev/null || echo 0)"
    echo ""
    echo "View logs with:"
    echo "  cat $EXECUTION_LOG              # Full execution log"
    echo "  cat $ERROR_LOG                  # Errors only"
    echo "  tail -50 $EXECUTION_LOG         # Recent activity"
    echo ""
}

# ==============================================================================
# MAIN
# ==============================================================================
case "${1:-help}" in
    start)
        log_loader_start "$2"
        ;;
    end)
        log_loader_end "$2" "${3:-0}"
        ;;
    run)
        if [ -z "$2" ]; then
            echo "Usage: $0 run <loader_script>"
            exit 1
        fi
        run_loader_traced "$2"
        ;;
    summary)
        view_summary
        ;;
    *)
        echo "Loader Execution Tracer"
        echo "Usage: $0 <command> [args]"
        echo ""
        echo "Commands:"
        echo "  start <name>           - Log loader start"
        echo "  end <name> [code]      - Log loader completion"
        echo "  run <script>           - Run loader with full tracing"
        echo "  summary                - View execution summary"
        ;;
esac
