#!/bin/bash
# Daily Health Check Script
# Runs every morning before trading to verify system is healthy
# Sends alerts if any critical checks fail

set -e

SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
LOG_FILE="${SCRIPT_DIR}/logs/daily_health_check.log"
ALERT_EMAIL="${ALERT_EMAIL:-}"
SLACK_WEBHOOK="${SLACK_WEBHOOK:-}"

# Ensure log directory exists
mkdir -p "${SCRIPT_DIR}/logs"

echo "========================================" | tee -a "$LOG_FILE"
echo "DAILY HEALTH CHECK — $(date)" | tee -a "$LOG_FILE"
echo "========================================" | tee -a "$LOG_FILE"

# Color output helpers
RED='\033[0;31m'
GREEN='\033[0;32m'
YELLOW='\033[1;33m'
NC='\033[0m' # No Color

FAILED_CHECKS=0
WARNINGS=0

# Function to log and alert
check_result() {
    local status=$1
    local check=$2
    local details=$3

    if [ "$status" = "PASS" ]; then
        echo -e "${GREEN}✓${NC} $check" | tee -a "$LOG_FILE"
    elif [ "$status" = "FAIL" ]; then
        echo -e "${RED}✗${NC} $check — $details" | tee -a "$LOG_FILE"
        FAILED_CHECKS=$((FAILED_CHECKS + 1))
    else
        echo -e "${YELLOW}⚠${NC} $check — $details" | tee -a "$LOG_FILE"
        WARNINGS=$((WARNINGS + 1))
    fi
}

# 1. Database connectivity
echo "" | tee -a "$LOG_FILE"
echo "=== DATABASE ===" | tee -a "$LOG_FILE"

if python3 -c "import psycopg2; psycopg2.connect(host='localhost', port=5432, user='stocks', password='postgres', database='stocks')" 2>/dev/null; then
    check_result "PASS" "Database Connection"
else
    check_result "FAIL" "Database Connection" "Cannot connect to PostgreSQL"
fi

# 2. Run system readiness verification
echo "" | tee -a "$LOG_FILE"
echo "=== SYSTEM READINESS ===" | tee -a "$LOG_FILE"

if [ -f "${SCRIPT_DIR}/verify_system_ready.py" ]; then
    if python3 "${SCRIPT_DIR}/verify_system_ready.py" 2>&1 | tee -a "$LOG_FILE" | grep -q "PRODUCTION READINESS: PASS"; then
        check_result "PASS" "System Readiness"
    elif grep -q "PRODUCTION READINESS: CAUTION" "$LOG_FILE"; then
        check_result "WARN" "System Readiness" "Check logs for warnings"
    else
        check_result "FAIL" "System Readiness" "Check logs for details"
    fi
else
    check_result "WARN" "System Readiness" "verify_system_ready.py not found"
fi

# 3. Verify latest data loader completed
echo "" | tee -a "$LOG_FILE"
echo "=== DATA LOADERS ===" | tee -a "$LOG_FILE"

# Check if data was loaded in last 24 hours
if python3 << 'EOF' 2>/dev/null
import psycopg2
from datetime import datetime, timedelta
import os

try:
    conn = psycopg2.connect(
        host='localhost', port=5432, user='stocks',
        password='postgres', database='stocks'
    )
    cur = conn.cursor()

    # Check if price_daily has today's data
    cur.execute("SELECT MAX(date) FROM price_daily")
    max_date = cur.fetchone()[0]

    from datetime import date as d
    if max_date and max_date >= d.today() - timedelta(days=1):
        print("LOADER_OK")
    else:
        print(f"LOADER_STALE:{max_date}")

    cur.close()
    conn.close()
except Exception as e:
    print(f"LOADER_ERROR:{e}")
EOF
then
    LOADER_STATUS=$(python3 << 'EOF'
import psycopg2
from datetime import datetime, timedelta, date as d
try:
    conn = psycopg2.connect(host='localhost', port=5432, user='stocks', password='postgres', database='stocks')
    cur = conn.cursor()
    cur.execute("SELECT MAX(date) FROM price_daily")
    max_date = cur.fetchone()[0]
    if max_date and max_date >= d.today() - timedelta(days=1):
        print("LOADER_OK")
    else:
        print(f"LOADER_STALE")
    cur.close()
    conn.close()
except:
    print("LOADER_ERROR")
EOF
)

    if [ "$LOADER_STATUS" = "LOADER_OK" ]; then
        check_result "PASS" "Data Loader"
    else
        check_result "WARN" "Data Loader" "Data may be stale"
    fi
fi

# 4. Performance metrics
echo "" | tee -a "$LOG_FILE"
echo "=== PERFORMANCE METRICS ===" | tee -a "$LOG_FILE"

if [ -f "${SCRIPT_DIR}/calc_performance_metrics.py" ]; then
    if python3 "${SCRIPT_DIR}/calc_performance_metrics.py" 2>&1 | tee -a "$LOG_FILE" | grep -q "Calculation complete"; then
        check_result "PASS" "Performance Metrics"
    else
        check_result "WARN" "Performance Metrics" "Calculation had issues"
    fi
else
    check_result "WARN" "Performance Metrics" "calc_performance_metrics.py not found"
fi

# Summary
echo "" | tee -a "$LOG_FILE"
echo "========================================" | tee -a "$LOG_FILE"
echo "SUMMARY" | tee -a "$LOG_FILE"
echo "========================================" | tee -a "$LOG_FILE"
echo "Failed Checks: ${FAILED_CHECKS}" | tee -a "$LOG_FILE"
echo "Warnings: ${WARNINGS}" | tee -a "$LOG_FILE"

if [ $FAILED_CHECKS -gt 0 ]; then
    echo -e "${RED}HEALTH STATUS: FAILED${NC}" | tee -a "$LOG_FILE"

    # Send alert
    if [ -n "$SLACK_WEBHOOK" ]; then
        curl -X POST "$SLACK_WEBHOOK" \
            -H 'Content-Type: application/json' \
            -d "{\"text\": \"⚠️ Daily Health Check FAILED — $FAILED_CHECKS failures, $WARNINGS warnings\"}" 2>/dev/null || true
    fi

    exit 1
elif [ $WARNINGS -gt 0 ]; then
    echo -e "${YELLOW}HEALTH STATUS: CAUTION${NC}" | tee -a "$LOG_FILE"
    exit 0
else
    echo -e "${GREEN}HEALTH STATUS: HEALTHY${NC}" | tee -a "$LOG_FILE"
    exit 0
fi
