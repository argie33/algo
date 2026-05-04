#!/usr/bin/env python3
"""
Monitor algo orchestrator deployment progress
Checks database connectivity and table row counts
"""

import os
import sys
import time
import psycopg2
from datetime import datetime
from dotenv import load_dotenv

load_dotenv('.env.local')

# Database config
DB_HOST = os.getenv('DB_HOST', 'localhost')
DB_PORT = int(os.getenv('DB_PORT', 5432))
DB_USER = os.getenv('DB_USER', 'stocks')
DB_PASSWORD = os.getenv('DB_PASSWORD', '')
DB_NAME = os.getenv('DB_NAME', 'stocks')

# Critical tables to monitor
CRITICAL_TABLES = [
    'price_daily',
    'technical_data_daily',
    'buy_sell_daily',
    'earnings_estimates',
    'balance_sheet_annual',
    'algo_trades',
    'algo_positions',
    'algo_audit_log'
]

def get_db_connection():
    """Connect to PostgreSQL database"""
    try:
        conn = psycopg2.connect(
            host=DB_HOST,
            port=DB_PORT,
            user=DB_USER,
            password=DB_PASSWORD,
            database=DB_NAME
        )
        return conn
    except Exception as e:
        return None

def get_table_count(conn, table_name):
    """Get row count for a table"""
    try:
        cursor = conn.cursor()
        cursor.execute(f"SELECT COUNT(*) FROM {table_name}")
        count = cursor.fetchone()[0]
        cursor.close()
        return count
    except Exception as e:
        return None

def check_database():
    """Check database connectivity and get table stats"""
    print("\n" + "="*70)
    print("DATABASE CONNECTIVITY CHECK - " + datetime.now().strftime('%Y-%m-%d %H:%M:%S'))
    print("="*70)

    conn = get_db_connection()

    if not conn:
        print("[FAIL] Cannot connect to " + str(DB_HOST) + ":" + str(DB_PORT))
        print("   Check: DB_HOST=" + str(DB_HOST) + ", DB_PORT=" + str(DB_PORT) + ", DB_USER=" + str(DB_USER))
        return False

    print("[OK] Connected to " + DB_HOST + ":" + str(DB_PORT) + "/" + DB_NAME)

    # Get table row counts
    print("\n" + "-"*70)
    print("CRITICAL TABLE ROW COUNTS")
    print("-"*70)

    table_stats = {}
    for table in CRITICAL_TABLES:
        count = get_table_count(conn, table)
        if count is not None:
            table_stats[table] = count
            status = "[OK]" if count > 0 else "[WARN]"
            print(status + " " + table.ljust(30) + " " + str(count).rjust(10) + " rows")
        else:
            print("[FAIL] " + table.ljust(30) + " (table not found)")

    conn.close()
    return True

def show_workflow_timeline():
    """Display expected workflow timeline"""
    print("\n" + "="*70)
    print("EXPECTED WORKFLOW TIMELINE")
    print("="*70)
    print("1. validate-algo                  [1 min]")
    print("   - Verify algo components exist")
    print("2. build-dependencies             [2 min]")
    print("   - Install Python packages")
    print("3. deploy-lambda                  [3 min]")
    print("   - Create S3 bucket (if needed)")
    print("   - Package Lambda function")
    print("   - Upload to S3")
    print("   - Deploy CloudFormation stack")
    print("4. manual-test (if workflow_dispatch)  [1 min]")
    print("   - Test Lambda invocation")
    print("5. summary                        [1 min]")
    print("   - Show deployment details")
    print("\nTOTAL: ~7-10 minutes")

def show_monitoring_locations():
    """Show where to monitor progress"""
    print("\n" + "="*70)
    print("WHERE TO MONITOR PROGRESS")
    print("="*70)
    print("1. GITHUB ACTIONS (Real-time)")
    print("   https://github.com/argie33/algo/actions/workflows/deploy-algo-orchestrator.yml")
    print("   - Watch: Job status, logs per step")
    print("")
    print("2. AWS CONSOLE (After deployment)")
    print("   - Lambda: https://console.aws.amazon.com/lambda/home")
    print("     Search for: algo-orchestrator")
    print("   - EventBridge: https://console.aws.amazon.com/events/home")
    print("     Rule: algo-eod-orchestrator")
    print("   - CloudWatch Logs: /aws/lambda/algo-orchestrator")
    print("")
    print("3. DATABASE (Every check)")
    print("   - This script monitors: Row counts in critical tables")
    print("   - Indicates: Data loading is active")
    print("")
    print("4. SNS ALERTS (After 5:30pm ET)")
    print("   - Topic: algo-orchestrator-alerts-dev")
    print("   - Notifications: Success/failure")

def show_next_steps():
    """Show next steps after deployment"""
    print("\n" + "="*70)
    print("NEXT STEPS")
    print("="*70)
    print("[OK] Deployment Successful:")
    print("   1. Verify Lambda function exists in AWS Console")
    print("   2. Check EventBridge rule is ENABLED")
    print("   3. First execution: Daily 5:30pm ET (automatic)")
    print("   4. Test manually: aws lambda invoke --function-name algo-orchestrator /tmp/out.json")
    print("")
    print("[FAIL] If Deployment Fails:")
    print("   1. Check GitHub Actions logs for error")
    print("   2. Verify AWS_ACCOUNT_ID secret is set")
    print("   3. Verify database credentials in AWS Secrets Manager")
    print("   4. Check CloudFormation stack events in AWS Console")

def main():
    """Main monitoring loop"""
    print("\n" + "="*70)
    print("ALGO ORCHESTRATOR DEPLOYMENT MONITOR".center(70))
    print("="*70)

    # Check database
    db_ok = check_database()

    # Show timeline
    show_workflow_timeline()

    # Show monitoring locations
    show_monitoring_locations()

    # Show next steps
    show_next_steps()

    print("\n" + "="*70)
    print("Monitoring active. Press Ctrl+C to stop.")
    print("="*70)

if __name__ == "__main__":
    main()
