"""
Phase 1 Enhancement: Data Freshness Alert Circuit Breaker

PROBLEM (Session 100-101): Data became stale, but orchestrator silently halted
Phase 7 with no external alerts. Operators were unaware until manual database
query revealed data staleness.

SOLUTION: Add SNS alert when data freshness check fails, so ops team knows
immediately that data pipeline has broken.

This module sends alerts to SNS topic when data is stale, enabling:
1. Immediate ops notification
2. Automated remediation triggers (could invoke recovery pipeline)
3. Audit trail of when data staleness occurred
"""

import json
import logging
from datetime import datetime, date
from typing import Dict, List, Tuple

import psycopg2
import boto3

logger = logging.getLogger(__name__)

# SNS topic for data staleness alerts (ops team)
SNS_TOPIC_ARN = "arn:aws:sns:us-east-1:626216981288:algo-data-alerts-dev"

# Data freshness thresholds (hours)
FRESHNESS_THRESHOLDS = {
    "price_daily": 4,  # Trading hours: must be within 4 hours
    "technical_data_daily": 24,  # Within 1 day (computed overnight)
    "market_exposure_daily": 24,  # Within 1 day
    "buy_sell_daily": 24,  # Computed overnight
    "stock_scores": 24,  # Computed overnight
}


def check_data_freshness() -> Dict[str, Tuple[int, bool]]:
    """
    Check freshness of critical data tables.

    Returns:
        {table_name: (hours_old, is_fresh)}
        is_fresh=True if within threshold, False if stale
    """
    conn = psycopg2.connect('dbname=stocks user=stocks host=localhost')
    cur = conn.cursor()

    results = {}
    today = date.today()

    try:
        for table, threshold_hours in FRESHNESS_THRESHOLDS.items():
            try:
                # Get most recent row timestamp for this table
                if table == "stock_scores":
                    # stock_scores has created_at, not date
                    query = f"SELECT EXTRACT(EPOCH FROM (NOW() - MAX(created_at)))/3600 FROM {table}"
                else:
                    query = f"SELECT EXTRACT(EPOCH FROM (NOW() - MAX(date::timestamp)))/3600 FROM {table}"

                cur.execute(query)
                hours_old = cur.fetchone()[0]

                if hours_old is None:
                    hours_old = 999  # No data at all = stale

                is_fresh = hours_old <= threshold_hours
                results[table] = (hours_old, is_fresh)

            except Exception as e:
                logger.error(f"Error checking {table}: {e}")
                results[table] = (999, False)  # Treat errors as stale

        return results

    finally:
        cur.close()
        conn.close()


def send_staleness_alert(stale_tables: Dict[str, Tuple[int, bool]]) -> None:
    """Send SNS alert for stale data."""
    sns = boto3.client('sns', region_name='us-east-1')

    # Build alert message
    alert_lines = [
        f"[ALERT] Data Staleness Detected at {datetime.now().isoformat()}",
        "",
        "Stale Tables:",
    ]

    for table, (hours_old, is_fresh) in stale_tables.items():
        if not is_fresh:
            threshold = FRESHNESS_THRESHOLDS[table]
            alert_lines.append(
                f"  - {table}: {hours_old:.1f} hours old (threshold: {threshold}h)"
            )

    alert_lines.extend([
        "",
        "ACTION REQUIRED:",
        "1. Check if loaders are running: aws stepfunctions list-executions --state-machine-arn ...",
        "2. If not, trigger recovery: python3 scripts/monitor_loader_pipeline.py",
        "3. Monitor data to confirm freshness restored",
        "",
        "For details, see: steering/DATA_LOADERS.md",
    ])

    message = "\n".join(alert_lines)

    try:
        sns.publish(
            TopicArn=SNS_TOPIC_ARN,
            Subject="[ALGO] Data Staleness Alert - Manual Action Required",
            Message=message,
        )
        logger.info(f"Staleness alert published to SNS")
    except Exception as e:
        logger.error(f"Failed to publish SNS alert: {e}")


def validate_data_freshness() -> bool:
    """
    Check if data is fresh enough for orchestrator to proceed.

    Returns:
        True if all critical data is fresh
        False if any data is stale (orchestrator should halt and alert)
    """
    stale_tables = check_data_freshness()

    # Check if any table is stale
    any_stale = any(not is_fresh for _, is_fresh in stale_tables.values())

    if any_stale:
        logger.warning("Data freshness check FAILED - some tables are stale")
        send_staleness_alert(stale_tables)
        return False

    logger.info("Data freshness check PASSED - all tables fresh")
    return True


if __name__ == "__main__":
    # Test alert system
    logging.basicConfig(level=logging.INFO)

    print("Testing data freshness check and alert system...")
    freshness = check_data_freshness()

    print("\nData Freshness Status:")
    for table, (hours_old, is_fresh) in freshness.items():
        status = "OK" if is_fresh else "STALE"
        threshold = FRESHNESS_THRESHOLDS[table]
        print(f"  {table:<30} {hours_old:>6.1f}h old (threshold: {threshold}h) [{status}]")

    # Would trigger alert if any stale
    is_valid = validate_data_freshness()
    print(f"\nOrchestrator can proceed: {is_valid}")
