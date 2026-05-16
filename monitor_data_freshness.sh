#!/bin/bash
#
# Data Freshness Monitoring Script
#
# Monitors database table freshness continuously and alerts on stale data.
# Run in background: nohup ./monitor_data_freshness.sh > data_monitor.log 2>&1 &
#
# Configuration:
DB_HOST="${DB_HOST:-localhost}"
DB_USER="${DB_USER:-stocks}"
DB_NAME="${DB_NAME:-stocks}"
DB_PASSWORD="${DB_PASSWORD:-postgres}"
CHECK_INTERVAL=3600  # Check every hour (3600 seconds)

# Tables to monitor
declare -A TABLE_THRESHOLDS=(
    ["price_daily"]=24
    ["technical_data_daily"]=24
    ["stock_scores"]=48
    ["buy_sell_daily"]=24
    ["market_health_daily"]=24
    ["analyst_sentiment_analysis"]=48
    ["market_sentiment"]=48
    ["sector_performance"]=48
)

# Colors for output
RED='\033[0;31m'
YELLOW='\033[1;33m'
GREEN='\033[0;32m'
NC='\033[0m'  # No Color

check_table_freshness() {
    local table=$1
    local max_age_hours=$2

    # Get max date from table
    local result=$(PGPASSWORD=$DB_PASSWORD psql -h $DB_HOST -U $DB_USER -d $DB_NAME -tc "
        SELECT EXTRACT(EPOCH FROM (NOW() - MAX(date)))::INTEGER / 3600 as age_hours
        FROM $table;
    " 2>/dev/null)

    if [ -z "$result" ]; then
        echo -e "${RED}[ERROR]${NC} $table: Cannot query table"
        return 2
    fi

    local age_hours=$(echo $result | grep -oE '[0-9]+' | head -1)

    if [ -z "$age_hours" ]; then
        echo -e "${RED}[ERROR]${NC} $table: No data found"
        return 2
    fi

    if [ "$age_hours" -gt "$max_age_hours" ]; then
        echo -e "${RED}[STALE]${NC} $table: Age=$age_hours hours (max=$max_age_hours)"
        # TODO: Send alert (email, Slack, etc.)
        return 1
    else
        echo -e "${GREEN}[OK]${NC} $table: Age=$age_hours hours"
        return 0
    fi
}

main() {
    echo "Data Freshness Monitor Started"
    echo "Check interval: ${CHECK_INTERVAL}s"
    echo ""

    while true; do
        echo "==================================="
        echo "Check at: $(date)"
        echo "==================================="

        total=0
        stale=0

        for table in "${!TABLE_THRESHOLDS[@]}"; do
            max_age=${TABLE_THRESHOLDS[$table]}
            check_table_freshness "$table" "$max_age"
            status=$?

            ((total++))
            if [ $status -ne 0 ]; then
                ((stale++))
            fi
        done

        echo ""
        echo "Summary: $stale/$total tables stale"
        echo ""

        # Alert if any are stale
        if [ $stale -gt 0 ]; then
            echo -e "${RED}⚠️  DATA FRESHNESS ALERT: $stale tables are stale${NC}"
            # TODO: Send notification
            # Example: aws sns publish --topic-arn arn:aws:sns:... --message "..."
        fi

        # Sleep until next check
        sleep $CHECK_INTERVAL
    done
}

main
