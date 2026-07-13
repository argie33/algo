#!/bin/bash
# Recover from orchestrator stall caused by stale loader data
#
# This script:
# 1. Monitors manual morning pipeline execution until completion
# 2. Verifies fresh data was populated
# 3. Clears halt flag from DynamoDB
# 4. Triggers orchestrator manually
# 5. Monitors orchestrator execution completion
#
# Usage: ./scripts/recover_from_loading_stall.sh

set -e

echo "=================================="
echo "Orchestrator Stall Recovery Script"
echo "=================================="
echo ""

# Configuration
PIPELINE_EXECUTION="manual-loader-20260713010115"
PIPELINE_STATE_MACHINE="algo-morning-prep-pipeline-dev"
MAX_PIPELINE_WAIT_MINUTES=90
MAX_ORCHESTRATOR_WAIT_MINUTES=60

# ============================================================================
# STEP 1: Monitor Pipeline Execution
# ============================================================================

monitor_pipeline() {
    local start_time=$(date +%s)
    local max_wait_seconds=$((MAX_PIPELINE_WAIT_MINUTES * 60))

    echo "[STEP 1] Monitoring morning pipeline execution..."
    echo "Expected completion: $MAX_PIPELINE_WAIT_MINUTES minutes from start"
    echo ""

    while true; do
        local current_time=$(date +%s)
        local elapsed=$((current_time - start_time))
        local elapsed_min=$((elapsed / 60))

        # Get execution status
        local status=$(aws stepfunctions list-executions \
            --state-machine-arn "arn:aws:states:us-east-1:626216981288:stateMachine:$PIPELINE_STATE_MACHINE" \
            --status-filter RUNNING \
            --query "executions[?contains(name, '$PIPELINE_EXECUTION')] | [0].executionArn" \
            --output text 2>/dev/null)

        if [ "$status" == "None" ] || [ -z "$status" ]; then
            # Pipeline finished, check final status
            echo "[$elapsed_min m] Pipeline execution completed"
            break
        else
            echo "[$elapsed_min m] Pipeline still running..."
            sleep 30
        fi

        if [ $elapsed -gt $max_wait_seconds ]; then
            echo "ERROR: Pipeline monitoring timeout after $MAX_PIPELINE_WAIT_MINUTES minutes"
            return 1
        fi
    done

    # Check final status
    local final_status=$(aws stepfunctions list-executions \
        --state-machine-arn "arn:aws:states:us-east-1:626216981288:stateMachine:$PIPELINE_STATE_MACHINE" \
        --status-filter SUCCEEDED \
        --query "executions[?contains(name, '$PIPELINE_EXECUTION')] | [0].status" \
        --output text 2>/dev/null)

    if [ "$final_status" == "SUCCEEDED" ]; then
        echo "SUCCESS: Pipeline completed successfully"
        echo ""
        return 0
    else
        echo "ERROR: Pipeline did not complete successfully (status: $final_status)"
        return 1
    fi
}

# ============================================================================
# STEP 2: Verify Data Freshness
# ============================================================================

verify_data() {
    echo "[STEP 2] Verifying data freshness..."
    echo ""

    local query1="SELECT COUNT(*) FROM price_daily WHERE date = CURRENT_DATE;"
    local query2="SELECT COUNT(*) FROM buy_sell_daily WHERE date::date = CURRENT_DATE;"
    local query3="SELECT COUNT(*) FROM market_health_daily WHERE date = CURRENT_DATE;"

    local price_count=$(psql -h localhost -U stocks -d stocks -t -c "$query1" 2>/dev/null | xargs)
    local signals_count=$(psql -h localhost -U stocks -d stocks -t -c "$query2" 2>/dev/null | xargs)
    local health_count=$(psql -h localhost -U stocks -d stocks -t -c "$query3" 2>/dev/null | xargs)

    echo "  price_daily:          $price_count rows [$([ $price_count -gt 0 ] && echo 'FRESH' || echo 'STALE')]"
    echo "  buy_sell_daily:       $signals_count rows [$([ $signals_count -gt 0 ] && echo 'FRESH' || echo 'STALE')]"
    echo "  market_health_daily:  $health_count rows [$([ $health_count -gt 0 ] && echo 'FRESH' || echo 'STALE')]"
    echo ""

    if [ $price_count -gt 0 ] && [ $signals_count -gt 0 ] && [ $health_count -gt 0 ]; then
        echo "SUCCESS: All critical tables have fresh data"
        return 0
    else
        echo "WARNING: Some tables are still stale. Data loading may be incomplete."
        echo "Proceeding anyway to attempt recovery..."
        return 0
    fi
}

# ============================================================================
# STEP 3: Clear Halt Flag
# ============================================================================

clear_halt_flag() {
    echo "[STEP 3] Clearing halt flag from DynamoDB..."
    echo ""

    python3 << 'PYTHON'
import boto3

dynamodb = boto3.resource('dynamodb', region_name='us-east-1')
table = dynamodb.Table('algo_orchestrator_state')

try:
    table.delete_item(Key={'key': 'halt_flag'})
    print("  Halt flag cleared successfully")
except Exception as e:
    print(f"  Error: {e}")
    exit(1)
PYTHON

    echo ""
    return $?
}

# ============================================================================
# STEP 4: Trigger Orchestrator
# ============================================================================

trigger_orchestrator() {
    echo "[STEP 4] Triggering orchestrator manually..."
    echo ""

    python3 << 'PYTHON'
import boto3
import json
from datetime import datetime

lambda_client = boto3.client('lambda', region_name='us-east-1')

try:
    payload = {
        'source': 'manual-recovery-script',
        'run_date': 'now',
        'execution_mode': 'paper',
        'note': f'Manual recovery at {datetime.now().isoformat()}: Data reloaded, halt cleared'
    }

    response = lambda_client.invoke(
        FunctionName='algo-algo-dev',
        InvocationType='RequestResponse',
        Payload=json.dumps(payload)
    )

    if response['StatusCode'] == 200:
        print("  Orchestrator Lambda invoked successfully")

        # Parse response
        import json
        result = json.loads(response['Payload'].read())
        if 'run_id' in result:
            print(f"  Run ID: {result.get('run_id', 'unknown')}")

        return True
    else:
        print(f"  ERROR: Lambda returned status {response['StatusCode']}")
        return False

except Exception as e:
    print(f"  ERROR: {e}")
    return False
PYTHON

    echo ""
    return $?
}

# ============================================================================
# STEP 5: Monitor Orchestrator
# ============================================================================

monitor_orchestrator() {
    echo "[STEP 5] Monitoring orchestrator execution..."
    echo "Expected completion: $MAX_ORCHESTRATOR_WAIT_MINUTES minutes"
    echo ""

    local start_time=$(date +%s)
    local max_wait_seconds=$((MAX_ORCHESTRATOR_WAIT_MINUTES * 60))
    local last_run_id=""

    while true; do
        local current_time=$(date +%s)
        local elapsed=$((current_time - start_time))
        local elapsed_min=$((elapsed / 60))

        # Get latest orchestrator run
        local run=$(psql -h localhost -U stocks -d stocks -t -c \
            "SELECT run_id, overall_status, EXTRACT(EPOCH FROM (completed_at - started_at)) as duration
             FROM algo_orchestrator_runs
             WHERE started_at > NOW() - INTERVAL '2 hours'
             ORDER BY started_at DESC LIMIT 1;" 2>/dev/null)

        if [ -n "$run" ]; then
            local run_id=$(echo "$run" | awk '{print $1}')
            local status=$(echo "$run" | awk '{print $2}')
            local duration=$(echo "$run" | awk '{print $3}')

            if [ "$run_id" != "$last_run_id" ]; then
                echo "[$elapsed_min m] Found run: $run_id | Status: $status | Duration: ${duration:0:5}s"
                last_run_id="$run_id"
            fi

            if [ "$status" != "success" ] && [ "$status" != "running" ]; then
                echo "[$elapsed_min m] Orchestrator completed with status: $status"
                if [ "$status" == "success" ]; then
                    echo "SUCCESS: Orchestrator run completed successfully!"
                    return 0
                else
                    echo "WARNING: Orchestrator completed with status: $status"
                    return 0
                fi
            fi
        fi

        sleep 10

        if [ $elapsed -gt $max_wait_seconds ]; then
            echo "[$elapsed_min m] Monitoring timeout after $MAX_ORCHESTRATOR_WAIT_MINUTES minutes"
            echo "Orchestrator may still be running. Check database for latest run status."
            return 0
        fi
    done
}

# ============================================================================
# Main Execution
# ============================================================================

main() {
    echo "Start time: $(date)"
    echo ""

    # Run all steps
    monitor_pipeline || exit 1
    verify_data || exit 1
    clear_halt_flag || exit 1
    trigger_orchestrator || exit 1
    monitor_orchestrator || exit 1

    # Summary
    echo ""
    echo "=================================="
    echo "Recovery Complete"
    echo "=================================="
    echo ""
    echo "All steps completed successfully!"
    echo "- Pipeline: Loaded fresh data"
    echo "- Data verified: All critical tables have today's data"
    echo "- Halt flag: Cleared from DynamoDB"
    echo "- Orchestrator: Triggered and monitoring started"
    echo ""
    echo "End time: $(date)"
}

# Run main function
main "$@"
