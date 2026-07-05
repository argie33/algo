#!/bin/bash
# Emergency Recovery Script for Data Pipeline Stall (2026-07-04)
# Purpose: Diagnose stuck loaders and restart critical data pipeline
# Usage: bash scripts/emergency_recovery.sh

set -e

echo "=========================================="
echo "ALGO TRADING SYSTEM - EMERGENCY RECOVERY"
echo "=========================================="
echo "Date: $(date)"
echo ""

# Color codes
RED='\033[0;31m'
GREEN='\033[0;32m'
YELLOW='\033[1;33m'
NC='\033[0m' # No Color

# Step 1: Check Database Connectivity
echo -e "${YELLOW}STEP 1: Checking Database Connectivity${NC}"
if [ -z "$DATABASE_URL" ]; then
    echo -e "${RED}ERROR: DATABASE_URL not set${NC}"
    exit 1
fi

echo "Testing connection to: ${DATABASE_URL:0:50}..."
psql "$DATABASE_URL" -c "SELECT version()" > /dev/null 2>&1 && \
    echo -e "${GREEN}✓ Database connection OK${NC}" || \
    { echo -e "${RED}✗ Database connection FAILED${NC}"; exit 1; }

# Step 2: Check Active Database Connections
echo ""
echo -e "${YELLOW}STEP 2: Checking Database Connection Pool${NC}"
psql "$DATABASE_URL" -c "
    SELECT
        state,
        COUNT(*) as connection_count
    FROM pg_stat_activity
    GROUP BY state
    ORDER BY connection_count DESC;
" 2>&1

# Step 3: List Stuck Loaders
echo ""
echo -e "${YELLOW}STEP 3: Checking Stuck Loaders${NC}"
psql "$DATABASE_URL" -c "
    SELECT
        loader_name,
        status,
        started_at,
        CURRENT_TIMESTAMP - started_at as stuck_duration,
        completion_pct
    FROM data_loader_status
    WHERE status IN ('RUNNING', 'SUSPENDED')
    ORDER BY started_at ASC
    LIMIT 15;
" 2>&1

# Step 4: Check Data Freshness
echo ""
echo -e "${YELLOW}STEP 4: Checking Data Freshness${NC}"
psql "$DATABASE_URL" -c "
    SELECT
        'algo_trades' as table_name,
        MAX(created_at) as last_update,
        CURRENT_TIMESTAMP - MAX(created_at) as age
    FROM algo_trades
    UNION ALL
    SELECT 'buy_sell_daily', MAX(created_at), CURRENT_TIMESTAMP - MAX(created_at)
    FROM buy_sell_daily
    UNION ALL
    SELECT 'market_health_daily', MAX(created_at), CURRENT_TIMESTAMP - MAX(created_at)
    FROM market_health_daily
    UNION ALL
    SELECT 'market_exposure_daily', MAX(created_at), CURRENT_TIMESTAMP - MAX(created_at)
    FROM market_exposure_daily
    ORDER BY last_update DESC;
" 2>&1

# Step 5: Check for Database Locks
echo ""
echo -e "${YELLOW}STEP 5: Checking for Blocked Queries/Locks${NC}"
psql "$DATABASE_URL" -c "
    SELECT
        blocked_locks.pid AS blocked_pid,
        blocked_activity.query AS blocked_query,
        blocking_locks.pid AS blocking_pid,
        blocking_activity.query AS blocking_query,
        blocked_activity.application_name AS blocked_app,
        blocking_activity.application_name AS blocking_app
    FROM pg_catalog.pg_locks blocked_locks
    JOIN pg_catalog.pg_stat_activity blocked_activity ON blocked_activity.pid = blocked_locks.pid
    JOIN pg_catalog.pg_locks blocking_locks ON blocking_locks.locktype = blocked_locks.locktype
        AND blocking_locks.database IS NOT DISTINCT FROM blocked_locks.database
        AND blocking_locks.relation IS NOT DISTINCT FROM blocked_locks.relation
        AND blocking_locks.page IS NOT DISTINCT FROM blocked_locks.page
        AND blocking_locks.tuple IS NOT DISTINCT FROM blocked_locks.tuple
        AND blocking_locks.virtualxid IS NOT DISTINCT FROM blocked_locks.virtualxid
        AND blocking_locks.transactionid IS NOT DISTINCT FROM blocked_locks.transactionid
        AND blocking_locks.classid IS NOT DISTINCT FROM blocked_locks.classid
        AND blocking_locks.objid IS NOT DISTINCT FROM blocked_locks.objid
        AND blocking_locks.objsubid IS NOT DISTINCT FROM blocked_locks.objsubid
        AND blocking_locks.pid != blocked_locks.pid
    JOIN pg_catalog.pg_stat_activity blocking_activity ON blocking_activity.pid = blocking_locks.pid
    WHERE NOT blocked_locks.granted;
" 2>&1 || echo "No blocking locks detected (OK)"

echo ""
echo -e "${GREEN}=========================================="
echo "DIAGNOSTIC COMPLETE"
echo "==========================================${NC}"
echo ""
echo "Next Steps:"
echo "1. Review diagnostic output above"
echo "2. If loaders stuck: Run recovery step below"
echo "3. Check AWS CloudWatch/ECS logs for details"
echo ""
echo -e "${YELLOW}RECOVERY: Kill Stuck ECS Tasks${NC}"
echo ""
echo "Command to list running loaders:"
echo "  aws ecs list-tasks --cluster algo-loaders --launch-type EC2"
echo ""
echo "Command to stop a stuck task (e.g., economic_metrics_daily):"
echo "  aws ecs stop-task --cluster algo-loaders --task <TASK_ARN>"
echo ""
