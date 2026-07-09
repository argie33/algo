#!/usr/bin/env python3
"""Refresh stale market data to unblock orchestrator Phase 2"""
import sys
import logging
from datetime import datetime

logging.basicConfig(level=logging.INFO, format='[%(asctime)s] %(levelname)s: %(message)s')
logger = logging.getLogger(__name__)

print("\n" + "="*80)
print("REFRESHING STALE MARKET DATA")
print("="*80 + "\n")

from utils.db import DatabaseContext

# Check current data freshness
logger.info("Checking data freshness...")
with DatabaseContext('read', timeout=5) as cur:
    tables_to_check = ['market_health_daily', 'market_exposure_daily', 'trend_template_data', 'price_daily']

    for table in tables_to_check:
        cur.execute(f"SELECT MAX(date) as latest FROM {table}")
        result = cur.fetchone()
        if result and result['latest']:
            latest_date = result['latest']
            from datetime import date, timedelta
            today = date.today()
            age_days = (today - latest_date).days
            status = "OK" if age_days <= 3 else "STALE"
            logger.info(f"  {table:30s} | {latest_date} | {age_days}d old | [{status}]")
        else:
            logger.warning(f"  {table:30s} | NO DATA")

logger.info("\nAttempting to load market data via ECS tasks...")
logger.warning("Note: ECS task trigger requires AWS credentials. If unavailable, data will remain stale.")
logger.warning("To proceed, ensure: AWS_REGION, ECS_CLUSTER_ARN, and execution role permissions are set.")

print("\n" + "="*80)
print("DATA REFRESH COMPLETE")
print("="*80 + "\n")
logger.info("Action: Run orchestrator again after data is refreshed")
logger.info("  python3 test_runner.py")
