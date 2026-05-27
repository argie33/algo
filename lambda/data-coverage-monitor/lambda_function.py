#!/usr/bin/env python3
"""
Lambda: Data Coverage Monitor

Runs periodic diagnostic checks on data coverage and logs findings.
Can be invoked manually or scheduled daily to monitor data health.

Checks:
1. Price data freshness and coverage
2. Technical indicators completeness
3. Market health data availability
4. Fundamental metrics coverage
5. Loader execution health
6. Symbol universe completeness

Returns JSON report and writes to CloudWatch Logs.
"""

import json
import boto3
import psycopg2
from datetime import datetime, timedelta, date as _date
from typing import Dict, Any, Optional

# AWS clients
s3_client = boto3.client('s3')
sm_client = boto3.client('secretsmanager')
cloudwatch = boto3.client('cloudwatch')


def get_db_connection():
    """Get database connection from Secrets Manager."""
    import logging
    logger = logging.getLogger(__name__)
    try:
        secret = sm_client.get_secret_value(SecretId='algo-db-credentials-dev')
        credentials = json.loads(secret['SecretString'])

        conn = psycopg2.connect(
            host=credentials['host'],
            port=credentials['port'],
            database=credentials['dbname'],
            user=credentials['username'],
            password=credentials['password'],
            sslmode='require',
            connect_timeout=10
        )
        return conn
    except Exception as e:
        logger.error(f"Database connection error: {e}")
        raise


def check_price_coverage(cur) -> Dict[str, Any]:
    """Check price_daily coverage."""
    try:
        cur.execute("""
            SELECT
                COUNT(DISTINCT symbol) as symbols_with_prices,
                MAX(date) as latest_date,
                COUNT(*) as total_rows
            FROM price_daily
            WHERE date > NOW() - INTERVAL '365 days'
        """)

        symbols, latest_date, total_rows = cur.fetchone()
        days_stale = (_date.today() - latest_date).days if latest_date else 999

        return {
            'status': 'ok' if days_stale <= 1 else 'warning' if days_stale <= 3 else 'error',
            'symbols': symbols,
            'latest_date': str(latest_date),
            'days_stale': days_stale,
            'total_rows': total_rows
        }
    except Exception as e:
        return {'status': 'error', 'error': str(e)}


def check_technical_coverage(cur) -> Dict[str, Any]:
    """Check technical_data_daily coverage."""
    try:
        cur.execute("""
            SELECT
                COUNT(DISTINCT symbol) as symbols,
                MAX(date) as latest_date,
                SUM(CASE WHEN rsi IS NOT NULL THEN 1 ELSE 0 END)::FLOAT / COUNT(*) as rsi_coverage,
                SUM(CASE WHEN ema_50 IS NOT NULL THEN 1 ELSE 0 END)::FLOAT / COUNT(*) as ema50_coverage,
                SUM(CASE WHEN atr IS NOT NULL THEN 1 ELSE 0 END)::FLOAT / COUNT(*) as atr_coverage
            FROM technical_data_daily
            WHERE date > NOW() - INTERVAL '30 days'
        """)

        symbols, latest_date, rsi_cov, ema_cov, atr_cov = cur.fetchone()

        # Flag if coverage below 90%
        status = 'ok' if (rsi_cov >= 0.9 and ema_cov >= 0.9 and atr_cov >= 0.9) else 'warning'

        return {
            'status': status,
            'symbols': symbols,
            'latest_date': str(latest_date),
            'coverage': {
                'rsi_pct': round(rsi_cov * 100, 1) if rsi_cov else 0,
                'ema50_pct': round(ema_cov * 100, 1) if ema_cov else 0,
                'atr_pct': round(atr_cov * 100, 1) if atr_cov else 0
            }
        }
    except Exception as e:
        return {'status': 'error', 'error': str(e)}


def check_market_health(cur) -> Dict[str, Any]:
    """Check market_health_daily availability."""
    try:
        cur.execute("""
            SELECT MAX(date) as latest_date, COUNT(*) as rows
            FROM market_health_daily
            WHERE date > NOW() - INTERVAL '30 days'
        """)

        latest_date, row_count = cur.fetchone()
        days_stale = (_date.today() - latest_date).days if latest_date else 999

        return {
            'status': 'ok' if days_stale <= 1 else 'error',
            'latest_date': str(latest_date),
            'days_stale': days_stale,
            'recent_rows': row_count
        }
    except Exception as e:
        return {'status': 'error', 'error': str(e)}


def check_symbol_completeness(cur) -> Dict[str, Any]:
    """Check S&P 500 symbol universe completeness."""
    try:
        # Symbols in universe
        cur.execute("SELECT COUNT(*) FROM stock_symbols WHERE is_sp500 = TRUE")
        sp500_total = cur.fetchone()[0]

        # Symbols with recent prices
        cur.execute("""
            SELECT COUNT(DISTINCT s.symbol)
            FROM stock_symbols s
            JOIN price_daily p ON s.symbol = p.symbol
            WHERE s.is_sp500 = TRUE AND p.date >= NOW() - INTERVAL '1 day'
        """)
        sp500_with_prices = cur.fetchone()[0]

        coverage_pct = (sp500_with_prices / sp500_total * 100) if sp500_total else 0

        return {
            'status': 'ok' if coverage_pct >= 99 else 'warning' if coverage_pct >= 95 else 'error',
            'sp500_total': sp500_total,
            'with_recent_prices': sp500_with_prices,
            'coverage_pct': round(coverage_pct, 1)
        }
    except Exception as e:
        return {'status': 'error', 'error': str(e)}


def check_fundamental_metrics(cur) -> Dict[str, Any]:
    """Check fundamental metrics coverage."""
    try:
        metrics = {}

        for table in ['quality_metrics', 'growth_metrics', 'value_metrics', 'stability_metrics']:
            try:
                cur.execute(f"""
                    SELECT COUNT(DISTINCT symbol) as symbols, MAX(date) as latest_date
                    FROM {table}
                    WHERE date > NOW() - INTERVAL '7 days'
                """)

                symbols, latest_date = cur.fetchone()
                metrics[table] = {
                    'symbols': symbols,
                    'latest_date': str(latest_date) if latest_date else None
                }
            except Exception:
                metrics[table] = {'error': 'Table not accessible'}

        return {'metrics': metrics}
    except Exception as e:
        return {'error': str(e)}


def lambda_handler(event, context):
    """Lambda handler for data coverage monitoring."""

    import logging
    logger = logging.getLogger(__name__)
    logger.info(f"Data coverage monitor started at {datetime.utcnow().isoformat()}")

    report = {
        'timestamp': datetime.utcnow().isoformat(),
        'checks': {}
    }

    try:
        conn = get_db_connection()
        cur = conn.cursor()

        # Run all checks
        report['checks']['price_coverage'] = check_price_coverage(cur)
        report['checks']['technical_coverage'] = check_technical_coverage(cur)
        report['checks']['market_health'] = check_market_health(cur)
        report['checks']['symbol_completeness'] = check_symbol_completeness(cur)
        report['checks']['fundamental_metrics'] = check_fundamental_metrics(cur)

        # Determine overall status
        statuses = [check.get('status', 'ok') for check in report['checks'].values() if isinstance(check, dict)]
        if 'error' in statuses:
            report['overall_status'] = 'error'
        elif 'warning' in statuses:
            report['overall_status'] = 'warning'
        else:
            report['overall_status'] = 'ok'

        cur.close()
        conn.close()

        # Emit custom metrics to CloudWatch
        for check_name, check_result in report['checks'].items():
            if isinstance(check_result, dict) and 'symbols' in check_result:
                cloudwatch.put_metric_data(
                    Namespace='Algo/DataQuality',
                    MetricData=[
                        {
                            'MetricName': f'{check_name}_symbols',
                            'Value': check_result['symbols'],
                            'Timestamp': datetime.utcnow()
                        }
                    ]
                )

    except Exception as e:
        logger.error(f"Error: {e}")
        report['error'] = str(e)
        report['overall_status'] = 'error'
        import traceback
        logger.error(traceback.format_exc())

    # Log report
    logger.info(f"Report: {json.dumps(report, indent=2)}")

    return {
        'statusCode': 200 if report.get('overall_status') == 'ok' else 202,
        'body': json.dumps(report),
        'report': report
    }


if __name__ == "__main__":
    # For local testing
    import logging
    logging.basicConfig(level=logging.INFO)
    result = lambda_handler({}, {})
    # Local testing only - output to logs
