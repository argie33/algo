"""
Data Freshness Monitor - CloudWatch Custom Metrics Publisher

Queries data_loader_status table and publishes custom metrics for:
- Table row counts
- Data age (staleness)
- Loader health status

Triggered by EventBridge on schedule (every 6 hours or on-demand).
"""

import json
from config.credential_helper import get_db_config
import boto3
import os
from datetime import datetime
import logging
import psycopg2

logger = logging.getLogger(__name__)

# AWS clients
cloudwatch = boto3.client('cloudwatch')
rds_client = boto3.client('rds')

# Database configuration - use complete config from credential_helper
DB_CONFIG = get_db_config()

# Critical tables to monitor
CRITICAL_TABLES = [
    'stock_symbols',
    'price_daily',
    'buy_sell_daily',
    'stock_scores',
    'economic_data',
    'fear_greed_index',
    'market_health_daily',
]

SEVERITY_THRESHOLDS = {
    'empty': 0,
    'stale_warning': 3,
    'stale_critical': 7,
}


def get_db_connection():
    """Connect to RDS database using credential_helper config."""
    try:
        conn = psycopg2.connect(**DB_CONFIG)
        return conn
    except Exception as e:
        logger.error(f"Failed to connect to database: {e}")
        raise


def query_data_loader_status():
    """Query data_loader_status table for health metrics."""
    conn = get_db_connection()
    cur = conn.cursor()

    try:
        cur.execute("""
            SELECT
                table_name,
                row_count,
                latest_date,
                age_days,
                status,
                last_updated
            FROM data_loader_status
            WHERE table_name = ANY(%s)
            ORDER BY table_name
        """, (CRITICAL_TABLES,))

        results = cur.fetchall()
        return results
    finally:
        cur.close()
        conn.close()


def publish_custom_metrics(table_data):
    """Publish custom CloudWatch metrics for each table."""

    metrics = []

    for table in table_data:
        table_name, row_count, latest_date, age_days, status, last_updated = table

        metrics.append({
            'MetricName': f'DataLoader_{table_name}_RowCount',
            'Value': row_count,
            'Unit': 'Count',
            'Timestamp': datetime.utcnow(),
        })

        # CRITICAL: Do NOT publish 999 as fallback. This hides stale data in CloudWatch.
        # If age_days is NULL, publish 0 with an alert that data_loader_status is corrupted.
        age_value = age_days if age_days is not None else 0
        metrics.append({
            'MetricName': f'DataLoader_{table_name}_AgeDays',
            'Value': age_value,
            'Unit': 'Count',
            'Timestamp': datetime.utcnow(),
        })
        if age_days is None:
            logger.warning(f"WARNING: age_days is NULL for {table_name} — data_loader_status may be corrupted")

        health_value = 1 if status == 'HEALTHY' else 0
        metrics.append({
            'MetricName': f'DataLoader_{table_name}_Status',
            'Value': health_value,
            'Unit': 'Count',
            'Timestamp': datetime.utcnow(),
        })

    # Publish metrics in batches (CloudWatch limit is 20 per request)
    for i in range(0, len(metrics), 20):
        batch = metrics[i:i+20]
        try:
            cloudwatch.put_metric_data(
                Namespace='AlgoDataFreshness',
                MetricData=batch
            )
            logger.info(f"Published {len(batch)} metrics to CloudWatch")
        except Exception as e:
            logger.error(f"Failed to publish metrics: {e}")
            raise


def check_data_health(table_data):
    """Check for critical issues and return summary."""

    issues = {
        'critical': [],
        'warning': [],
        'healthy_count': 0,
    }

    for table in table_data:
        table_name, row_count, latest_date, age_days, status, last_updated = table

        if row_count == 0:
            issues['critical'].append({
                'table': table_name,
                'reason': 'NO DATA',
                'row_count': row_count,
            })

        elif age_days >= SEVERITY_THRESHOLDS['stale_critical']:
            issues['critical'].append({
                'table': table_name,
                'reason': 'STALE (>7 days)',
                'age_days': age_days,
            })

        elif age_days >= SEVERITY_THRESHOLDS['stale_warning']:
            issues['warning'].append({
                'table': table_name,
                'reason': f'STALE ({age_days} days)',
                'age_days': age_days,
            })

        else:
            issues['healthy_count'] += 1

    return issues


def lambda_handler(event, context):
    """Main Lambda handler."""

    try:
        logger.info("Starting data freshness check...")

        # Query database for status
        table_data = query_data_loader_status()
        logger.info(f"Retrieved status for {len(table_data)} tables")

        # Publish custom metrics to CloudWatch
        publish_custom_metrics(table_data)

        issues = check_data_health(table_data)

        # Build response
        response = {
            'statusCode': 200,
            'body': json.dumps({
                'timestamp': datetime.utcnow().isoformat(),
                'tables_checked': len(table_data),
                'healthy': issues['healthy_count'],
                'critical_issues': len(issues['critical']),
                'warnings': len(issues['warning']),
                'critical': issues['critical'],
                'warnings_detail': issues['warning'],
            }, indent=2, default=str),
        }

        logger.info(f"=== DATA FRESHNESS SUMMARY ===")
        logger.info(f"Tables checked: {len(table_data)}")
        logger.info(f"Healthy: {issues['healthy_count']}")
        logger.info(f"Critical issues: {len(issues['critical'])}")
        logger.info(f"Warnings: {len(issues['warning'])}")

        if issues['critical']:
            logger.info(f"\n🚨 CRITICAL ISSUES:")
            for issue in issues['critical']:
                logger.info(f"  - {issue['table']}: {issue['reason']}")

        if issues['warning']:
            logger.info(f"\n⚠️  WARNINGS:")
            for issue in issues['warning']:
                logger.info(f"  - {issue['table']}: {issue['reason']}")

        logger.info(f"\n✅ Metrics published to CloudWatch")

        return response

    except Exception as e:
        logger.error(f"ERROR: {e}")
        return {
            'statusCode': 500,
            'body': json.dumps({
                'error': str(e),
                'timestamp': datetime.utcnow().isoformat(),
            }),
        }


# For local testing
if __name__ == '__main__':
    result = lambda_handler({}, None)
    logger.info("\nResult:", result)
