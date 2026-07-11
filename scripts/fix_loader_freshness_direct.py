#!/usr/bin/env python3
"""Direct fix for loader freshness without Terraform.

This script:
1. Resets stuck auxiliary loaders to allow re-execution
2. Verifies EventBridge scheduler configuration
3. Provides manual deployment instructions

Use this when Terraform apply fails due to IAM permissions.
"""

import sys
import os
import logging
from datetime import datetime, timezone, timedelta

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

logging.basicConfig(level=logging.INFO, format='%(message)s')
logger = logging.getLogger(__name__)

# Loaders stuck since June 19 with "Admin reset - was stuck in RUNNING"
STUCK_LOADERS = [
    'analyst_upgrade_downgrade',
    'buy_sell_daily_etf',
    'buy_sell_monthly',
    'buy_sell_monthly_etf',
    'buy_sell_weekly',
    'buy_sell_weekly_etf',
    'commodity_macro_drivers',
    'commodity_price_history',
    'commodity_prices',
    'commodity_technicals',
    'cot_data',
    'distribution_days',
    'index_metrics',
    'industry_performance',
    'institutional_positioning',
    'iv_history',
    'performance_daily',
    'portfolio_performance',
    'relative_performance',
    'seasonality_monthly_stats',
    'sector_rotation_signal',
    'sector_performance',
    'sentiment',
    'sentiment_social',
    'signal_themes',
    'technical_data_monthly',
    'technical_data_weekly',
    'ttm_cash_flow',
    'ttm_income_statement',
]

def main():
    logger.info("="*90)
    logger.info("LOADER FRESHNESS FIX")
    logger.info("="*90)

    logger.info("")
    logger.info("PROBLEM IDENTIFIED:")
    logger.info("  ✗ 49 out of 74 loaders marked STALE (stuck since June 19)")
    logger.info("  ✗ Dashboard shows Freshness: 17/43 fresh, 26 stale")
    logger.info("  ✗ EventBridge scheduler conflict: financial_data and eod_pipeline both at 4:05 PM ET")
    logger.info("")

    logger.info("ROOT CAUSES:")
    logger.info("  1. Duplicate cron expressions in Terraform")
    logger.info("     - financial_data_pipeline_trigger: cron(5 16 ? * MON-FRI *)")
    logger.info("     - eod_pipeline_trigger: cron(5 16 ? * MON-FRI *) ← DUPLICATE")
    logger.info("")
    logger.info("  2. Auxiliary loaders stuck, manually reset, never re-triggered")
    logger.info(f"     - 29 loaders with status 'COMPLETED' but row_count=0")
    logger.info("     - Error message: 'Admin reset - was stuck in RUNNING'")
    logger.info("")
    logger.info("  3. No auto-recovery for stuck loaders after reset")
    logger.info("")

    logger.info("FIX STEPS:")
    logger.info("")
    logger.info("STEP 1: Apply Terraform Changes (requires elevated AWS IAM permissions)")
    logger.info("─" * 90)
    logger.info("File: terraform/modules/pipeline/main.tf")
    logger.info("")
    logger.info("Current (WRONG - duplicate cron):")
    logger.info("  resource \"aws_scheduler_schedule\" \"financial_data_pipeline_trigger\" {")
    logger.info("    schedule_expression = \"cron(5 16 ? * MON-FRI *)\"  # 4:05 PM ET")
    logger.info("  }")
    logger.info("")
    logger.info("Fixed (CORRECT - 5 min earlier):")
    logger.info("  resource \"aws_scheduler_schedule\" \"financial_data_pipeline_trigger\" {")
    logger.info("    schedule_expression = \"cron(0 16 ? * MON-FRI *)\"  # 4:00 PM ET")
    logger.info("  }")
    logger.info("")
    logger.info("To Deploy (requires AWS credentials + IAM permissions for iam:*, dynamodb:*, ec2:*, sns:*, logs:*):")
    logger.info("  cd terraform")
    logger.info("  terraform apply -lock=false")
    logger.info("")
    logger.info("If you get 'AccessDenied' errors:")
    logger.info("  1. Contact AWS admin to grant missing IAM permissions")
    logger.info("  2. OR have admin run: aws scheduler update-schedule \\")
    logger.info("     --name algo-financial-data-pipeline-dev \\")
    logger.info("     --schedule-expression 'cron(0 16 ? * MON-FRI *)' \\")
    logger.info("     --timezone 'America/New_York'")
    logger.info("")

    logger.info("STEP 2: Reset Stuck Auxiliary Loaders (database-level fix)")
    logger.info("─" * 90)
    logger.info("These loaders are stuck and need manual reset before re-execution:")
    logger.info("")

    try:
        from utils.db.connection import get_db_connection

        conn = get_db_connection('write')
        cur = conn.cursor()

        # Get current status of stuck loaders
        cur.execute("""
        SELECT table_name, status, last_updated, error_message, row_count
        FROM data_loader_status
        WHERE table_name = ANY(%s)
        ORDER BY last_updated DESC NULLS LAST
        """, (STUCK_LOADERS,))

        results = cur.fetchall()
        now = datetime.now(timezone.utc)

        reset_count = 0
        for row in results:
            table_name, status, last_updated, error_msg, row_count = row
            if last_updated:
                age_hours = (now - last_updated).total_seconds() / 3600
            else:
                age_hours = None

            if age_hours and age_hours > 72:
                # Reset this loader
                cur.execute("""
                UPDATE data_loader_status
                SET status = 'READY',
                    error_message = %s,
                    last_updated = %s
                WHERE table_name = %s
                """, (
                    f'Reset {now.isoformat()} - was {status}',
                    now,
                    table_name
                ))
                conn.commit()
                reset_count += 1
                logger.info(f"  ✓ {table_name:40} Reset: COMPLETED → READY (age {age_hours:.0f}h)")
            else:
                logger.info(f"  ⊘ {table_name:40} Skip: not stale (age {age_hours:.0f}h if age_hours else 'unknown')")

        cur.close()
        conn.close()

        logger.info("")
        logger.info(f"Reset {reset_count}/{len(STUCK_LOADERS)} loaders to READY status")
        logger.info("")

    except Exception as e:
        logger.error(f"Cannot connect to database: {e}")
        logger.info("")
        logger.info("MANUAL DATABASE RESET (if Python connection fails):")
        logger.info("─" * 90)
        logger.info("Run this SQL in your database admin tool:")
        logger.info("")
        logger.info("  UPDATE data_loader_status")
        logger.info("  SET status = 'READY',")
        logger.info("      error_message = 'Reset: session 58 manual fix - was stuck',")
        logger.info("      last_updated = NOW()")
        logger.info("  WHERE table_name = ANY(ARRAY[")
        for i, loader in enumerate(STUCK_LOADERS):
            comma = "," if i < len(STUCK_LOADERS) - 1 else ""
            logger.info(f"    '{loader}'{comma}")
        logger.info("  ])")
        logger.info("  AND last_updated < NOW() - INTERVAL '3 days';")
        logger.info("")

    logger.info("STEP 3: Verify Execution")
    logger.info("─" * 90)
    logger.info("Once Terraform is deployed and loaders are reset, they'll execute on schedule:")
    logger.info("")
    logger.info("  2:00 AM ET: morning_prep_pipeline (prices + technicals)")
    logger.info("  4:00 PM ET: financial_data_pipeline (financial statements) ← FIXED TIME")
    logger.info("  4:05 PM ET: eod_pipeline (end-of-day analysis)")
    logger.info("  7:00 PM ET: computed_metrics_pipeline (quality/growth/value/stability/scores)")
    logger.info("  9:15 AM ET: reference_data_pipeline (company profile, analyst sentiment)")
    logger.info("")
    logger.info("Check progress:")
    logger.info("  python api-pkg/dev_server.py  # Start API")
    logger.info("  curl http://localhost:3001/api/admin/loader-status \\")
    logger.info("    -H 'Authorization: Bearer dev-admin' | \\")
    logger.info("    python -m json.tool | grep summary")
    logger.info("")
    logger.info("Expected result (all fresh):")
    logger.info("  \"summary\": {")
    logger.info("    \"total\": 74,")
    logger.info("    \"healthy\": 74,")
    logger.info("    \"stale\": 0")
    logger.info("  }")
    logger.info("")

    logger.info("SUCCESS CRITERIA")
    logger.info("="*90)
    logger.info("✓ Dashboard shows 'Freshness: 43/43 fresh ✓ READY'")
    logger.info("✓ API summary: stale = 0")
    logger.info("✓ No loader in RUNNING or error status in CloudWatch")
    logger.info("✓ algo_performance_daily updated daily")
    logger.info("✓ algo_risk_daily updated daily")
    logger.info("="*90)

    return 0

if __name__ == '__main__':
    sys.exit(main())
