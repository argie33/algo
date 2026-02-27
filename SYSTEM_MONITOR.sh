#!/bin/bash

# ==============================================================================
# SYSTEM MONITOR - Comprehensive Tracing for WSL Stability
# ==============================================================================
# Monitors:
# - System crashes/reboots
# - Memory usage trends
# - Loader execution and status
# - Service health
# - Kernel errors
# ==============================================================================

MONITOR_DIR="/home/arger/algo/logs/system_monitoring"
CRASH_LOG="$MONITOR_DIR/crash_detection.log"
MEMORY_LOG="$MONITOR_DIR/memory_history.log"
HEALTH_LOG="$MONITOR_DIR/system_health.log"
ALERTS_LOG="$MONITOR_DIR/alerts.log"

# Create monitoring directory
mkdir -p "$MONITOR_DIR"

# Color codes for alerts
RED='\033[0;31m'
YELLOW='\033[1;33m'
GREEN='\033[0;32m'
NC='\033[0m' # No Color

# ==============================================================================
# FUNCTION: Check for unexpected reboots
# ==============================================================================
check_for_crashes() {
    local current_boot=$(systemctl show -p KernelBootTime --value)
    local last_boot_file="$MONITOR_DIR/.last_boot_time"

    if [ -f "$last_boot_file" ]; then
        local last_boot=$(cat "$last_boot_file")
        if [ "$current_boot" != "$last_boot" ]; then
            echo "[$(date +'%Y-%m-%d %H:%M:%S')] SYSTEM REBOOT DETECTED" >> "$CRASH_LOG"
            echo "  Previous boot: $last_boot" >> "$CRASH_LOG"
            echo "  Current boot:  $current_boot" >> "$CRASH_LOG"

            # Check if it was unclean
            if journalctl -b -1 2>/dev/null | grep -q "uncleanly shut down"; then
                echo "  Status: UNCLEAN SHUTDOWN (potential crash)" >> "$CRASH_LOG"
                alert "CRASH DETECTED" "System had unclean shutdown. Check $CRASH_LOG"
            else
                echo "  Status: Clean boot" >> "$CRASH_LOG"
            fi
            echo "" >> "$CRASH_LOG"
        fi
    fi

    echo "$current_boot" > "$last_boot_file"
}

# ==============================================================================
# FUNCTION: Monitor memory usage
# ==============================================================================
monitor_memory() {
    local timestamp=$(date +'%Y-%m-%d %H:%M:%S')
    local mem_total=$(free -h | awk '/^Mem:/ {print $2}')
    local mem_used=$(free -h | awk '/^Mem:/ {print $3}')
    local mem_free=$(free -h | awk '/^Mem:/ {print $4}')
    local mem_percent=$(free | awk '/^Mem:/ {printf "%.1f", ($3/$2)*100}')
    local load_avg=$(uptime | awk -F'load average:' '{print $2}' | xargs)

    # Log memory metrics
    echo "$timestamp | Total: $mem_total | Used: $mem_used | Free: $mem_free | Usage: $mem_percent% | Load: $load_avg" >> "$MEMORY_LOG"

    # Alert if memory usage is critical (>80%)
    local mem_used_mb=$(free | awk '/^Mem:/ {print $3}')
    local mem_total_mb=$(free | awk '/^Mem:/ {print $2}')
    local threshold=$((mem_total_mb * 80 / 100))

    if [ "$mem_used_mb" -gt "$threshold" ]; then
        alert "HIGH MEMORY USAGE" "Memory usage is $mem_percent% ($(echo "scale=0; $mem_used_mb / 1024" | bc)GB). Free: $(echo "scale=0; $(free | awk '/^Mem:/ {print $4}') / 1024" | bc)GB"
    fi
}

# ==============================================================================
# FUNCTION: Check system health
# ==============================================================================
check_system_health() {
    local timestamp=$(date +'%Y-%m-%d %H:%M:%S')

    {
        echo "=== SYSTEM HEALTH CHECK: $timestamp ==="

        # Check if PostgreSQL is running
        if pgrep postgres > /dev/null; then
            echo "[OK] PostgreSQL is running"
        else
            echo "[WARN] PostgreSQL is NOT running"
        fi

        # Check disk space
        local disk_usage=$(df -h / | awk 'NR==2 {print $5}')
        echo "[INFO] Disk usage: $disk_usage"

        # Check systemd journal for errors in last hour
        local recent_errors=$(journalctl -p err --since "1 hour ago" 2>/dev/null | wc -l)
        if [ "$recent_errors" -gt 0 ]; then
            echo "[WARN] $recent_errors errors in systemd journal (last hour)"
        else
            echo "[OK] No recent errors in systemd journal"
        fi

        # Check for failed services
        local failed_services=$(systemctl list-units --type=service --state=failed --no-pager 2>&1 | grep -c FAILED)
        if [ "$failed_services" -gt 0 ]; then
            echo "[WARN] $failed_services failed services detected"
        else
            echo "[OK] No failed services"
        fi

        # Check kernel logs for warnings
        local kernel_warns=$(dmesg | tail -100 | grep -i "warn\|error" | wc -l)
        if [ "$kernel_warns" -gt 0 ]; then
            echo "[WARN] $kernel_warns kernel warnings/errors in dmesg"
        fi

        echo ""
    } | tee -a "$HEALTH_LOG"
}

# ==============================================================================
# FUNCTION: Check loader processes
# ==============================================================================
check_loaders() {
    local timestamp=$(date +'%Y-%m-%d %H:%M:%S')
    local loader_count=$(ps aux | grep -E "python.*load" | grep -v grep | wc -l)

    if [ "$loader_count" -gt 0 ]; then
        echo "[$timestamp] LOADERS ACTIVE: $loader_count processes" >> "$MONITOR_DIR/loader_activity.log"
        ps aux | grep -E "python.*load" | grep -v grep >> "$MONITOR_DIR/loader_activity.log"
        echo "" >> "$MONITOR_DIR/loader_activity.log"
    fi
}

# ==============================================================================
# FUNCTION: Send alert
# ==============================================================================
alert() {
    local title="$1"
    local message="$2"
    local timestamp=$(date +'%Y-%m-%d %H:%M:%S')

    echo -e "${RED}[ALERT] $timestamp - $title${NC}"
    echo "$message" | sed 's/^/  /'

    # Log to alerts file
    echo "[$timestamp] $title: $message" >> "$ALERTS_LOG"
}

# ==============================================================================
# FUNCTION: Print current status
# ==============================================================================
print_status() {
    echo ""
    echo -e "${GREEN}=== SYSTEM MONITORING STATUS ===${NC}"
    echo "Monitoring directory: $MONITOR_DIR"
    echo ""
    echo "Recent logs:"
    echo "  Crash detection: $(tail -1 "$CRASH_LOG" 2>/dev/null || echo 'No crashes detected')"
    echo "  Memory usage: $(tail -1 "$MEMORY_LOG" 2>/dev/null || echo 'No data')"
    echo "  Alerts: $(wc -l < "$ALERTS_LOG" 2>/dev/null || echo 0) total"
    echo ""
    echo "View logs with:"
    echo "  tail -f $MEMORY_LOG          # Memory trends"
    echo "  tail -f $CRASH_LOG           # Crash history"
    echo "  tail -f $ALERTS_LOG          # All alerts"
    echo "  tail -f $HEALTH_LOG          # System health"
    echo ""
}

# ==============================================================================
# MAIN LOOP
# ==============================================================================
main() {
    echo "Starting System Monitor at $(date +'%Y-%m-%d %H:%M:%S')"

    # Run checks immediately
    check_for_crashes
    monitor_memory
    check_system_health
    check_loaders
    print_status

    # Run continuous monitoring
    if [ "$1" == "--continuous" ]; then
        echo ""
        echo -e "${YELLOW}Running continuous monitoring (check every 60 seconds)${NC}"
        echo "Press Ctrl+C to stop"
        echo ""

        while true; do
            sleep 60
            clear
            check_for_crashes
            monitor_memory
            check_system_health
            check_loaders
            print_status
        done
    fi
}

main "$@"
