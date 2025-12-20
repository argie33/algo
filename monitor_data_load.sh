#!/bin/bash
################################################################################
# Data Load Monitor - Real-time progress tracking
#
# Shows live progress of data loading in multiple terminal windows:
#   - Growth metrics count
#   - Memory usage
#   - Process status
#   - Detailed logs
#
# Usage:
#   ./monitor_data_load.sh          # Start monitoring
#
################################################################################

SCRIPT_DIR="$( cd "$( dirname "${BASH_SOURCE[0]}" )" && pwd )"
cd "$SCRIPT_DIR"

# Load environment
if [ ! -f ".env.local" ]; then
    echo "❌ .env.local not found"
    exit 1
fi

source .env.local

# Colors
GREEN='\033[0;32m'
YELLOW='\033[1;33m'
BLUE='\033[0;34m'
NC='\033[0m'

print_header() {
    clear
    echo -e "${BLUE}╔════════════════════════════════════════════════════════════╗${NC}"
    echo -e "${BLUE}║  DATA LOAD MONITOR - $(date '+%Y-%m-%d %H:%M:%S')                 ║${NC}"
    echo -e "${BLUE}╚════════════════════════════════════════════════════════════╝${NC}"
    echo ""
}

show_database_status() {
    echo -e "${GREEN}📊 DATABASE STATUS${NC}"
    echo "────────────────────────────────────────────"

    # Growth metrics count
    count=$(psql -h "$DB_HOST" -U "$DB_USER" -d "$DB_NAME" -t -c \
        "SELECT COUNT(*) FROM growth_metrics WHERE date = CURRENT_DATE;" 2>/dev/null || echo "?")
    echo "Growth Metrics Today: $count rows"

    # Coverage by metric
    echo ""
    echo "Coverage by Metric:"
    psql -h "$DB_HOST" -U "$DB_USER" -d "$DB_NAME" -t -c "
        SELECT
            CONCAT('  ', metric, ': ') ||
            COUNT(CASE WHEN value IS NOT NULL THEN 1 END) || '/' || COUNT(*) ||
            ' (' || ROUND(100.0*COUNT(CASE WHEN value IS NOT NULL THEN 1 END)/COUNT(*), 1) || '%)'
        FROM (
            SELECT 'revenue_growth' as metric, revenue_growth_3y_cagr as value FROM growth_metrics WHERE date = CURRENT_DATE
            UNION ALL
            SELECT 'eps_growth', eps_growth_3y_cagr FROM growth_metrics WHERE date = CURRENT_DATE
            UNION ALL
            SELECT 'fcf_growth', fcf_growth_yoy FROM growth_metrics WHERE date = CURRENT_DATE
            UNION ALL
            SELECT 'quarterly_momentum', quarterly_growth_momentum FROM growth_metrics WHERE date = CURRENT_DATE
        ) t
        GROUP BY metric
        ORDER BY metric;
    " 2>/dev/null || echo "  (could not connect to database)"

    echo ""
}

show_process_status() {
    echo -e "${GREEN}🔄 PROCESS STATUS${NC}"
    echo "────────────────────────────────────────────"

    count=$(pgrep -f "python3 load" | wc -l)
    if [ "$count" -gt 0 ]; then
        echo "Running: $count python processes"
        echo ""
        ps aux | grep "python3 load" | grep -v grep | awk '{
            printf "  PID %-7d %s %s\n", $2, $11, (length($12) > 30 ? substr($12, 1, 30) "..." : $12)
        }'
    else
        echo "No loading processes running"
    fi

    echo ""
}

show_system_status() {
    echo -e "${GREEN}💾 SYSTEM RESOURCES${NC}"
    echo "────────────────────────────────────────────"

    # Memory
    mem=$(free -h | grep Mem | awk '{print $3 "/" $2}')
    mem_pct=$(free | grep Mem | awk '{printf "%.1f", ($3/$2)*100}')
    echo "Memory: $mem ($mem_pct%)"

    # Disk
    disk=$(df -h "$SCRIPT_DIR" | tail -1 | awk '{print $3 "/" $2}')
    disk_pct=$(df "$SCRIPT_DIR" | tail -1 | awk '{printf "%.1f", ($3/$2)*100}')
    echo "Disk: $disk ($disk_pct%)"

    # CPU
    cpu=$(top -bn1 | grep "Cpu(s)" | awk '{print $2}' | cut -d'%' -f1)
    echo "CPU: ${cpu}% used"

    echo ""
}

show_log_summary() {
    echo -e "${GREEN}📋 RECENT LOG ACTIVITY${NC}"
    echo "────────────────────────────────────────────"

    if [ -f "load_pipeline.log" ]; then
        tail -10 load_pipeline.log | sed 's/^/  /'
    elif [ -f "load_all_growth_data_execution.json" ]; then
        echo "  Execution summary available in execution.json"
    else
        echo "  No logs available yet"
    fi

    echo ""
}

show_next_steps() {
    echo -e "${YELLOW}📌 NEXT STEPS${NC}"
    echo "────────────────────────────────────────────"
    echo "  1. Monitor this output automatically: watch -n 5 ./monitor_data_load.sh"
    echo "  2. View detailed logs: tail -f load_pipeline.log"
    echo "  3. When complete, analyze: python3 analyze_growth_gaps.py"
    echo ""
}

# Main loop
print_header
show_database_status
show_process_status
show_system_status
show_log_summary
show_next_steps

echo -e "${BLUE}Last updated: $(date '+%Y-%m-%d %H:%M:%S')${NC}"
echo ""
