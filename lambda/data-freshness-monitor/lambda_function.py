"""
Data Freshness Monitor Lambda

Monitors the freshness of critical data tables and halts trading if data becomes stale.
Runs every 6 hours to check: price_daily, buy_sell_daily, technical_data_daily,
swing_trader_scores, signal_quality_scores, market_exposure_daily.
"""

import json
import logging
import os
from datetime import datetime, timezone
from typing import Dict, List

import psycopg2
from algo.reporting import AlertManager
from utils.db.sql_safety import assert_safe_table

logger = logging.getLogger()
logger.setLevel(logging.INFO)

def get_db_connection():
    try:
        conn = psycopg2.connect(
            host=os.environ.get('DB_HOST'),
            port=int(os.environ.get('DB_PORT', '5432')),
            database=os.environ.get('DB_NAME'),
            user=os.environ.get('DB_USER'),
            password=os.environ.get('DB_PASSWORD'),
            connect_timeout=10
        )
        return conn
    except Exception as e:
        logger.error(f"Database connection failed: {e}")
        raise

def check_critical_table_freshness() -> Dict:
    """Check freshness of all critical trading tables.

    Returns: {status: 'ok'|'degraded'|'critical', stale_tables: [...], age_details: {...}}
    """
    try:
        conn = get_db_connection()
        cur = conn.cursor()

        critical_tables = {
            'price_daily': 'prices',
            'buy_sell_daily': 'buy/sell signals',
            'technical_data_daily': 'technical indicators',
            'swing_trader_scores': 'swing scores',
            'signal_quality_scores': 'signal quality',
            'market_exposure_daily': 'market exposure limits',
            'sector_ranking': 'sector data',
        }

        now_utc = datetime.now(timezone.utc)
        stale_tables = []
        age_details = {}

        for table_name, description in critical_tables.items():
            try:
                # Get most recent date in table
                table_safe = assert_safe_table(table_name)
                cur.execute(f"SELECT MAX(date) FROM {table_safe}")
                max_date = cur.fetchone()[0]

                if max_date is None:
                    logger.critical(f"[FRESHNESS] {description} table is EMPTY")
                    stale_tables.append(f'{description} (empty)')
                    age_details[table_name] = {'status': 'empty', 'reason': 'no data'}
                    continue

                # For date-based tables, check staleness
                from datetime import timedelta
                age_days = (datetime.now(timezone.utc).date() - max_date).days

                # Max acceptable age: 2 days for prices, 1 day for signals
                max_age = 2 if table_name == 'price_daily' else 1

                if age_days > max_age:
                    logger.warning(f"[FRESHNESS] {description}: {age_days} days old (max {max_age})")
                    stale_tables.append(f'{description} ({age_days}d old)')
                    age_details[table_name] = {'status': 'stale', 'age_days': age_days, 'max_days': max_age}
                else:
                    age_details[table_name] = {'status': 'ok', 'age_days': age_days, 'latest_date': str(max_date)}

                # For time-based freshness (swing/quality scores)
                if table_name in ['swing_trader_scores', 'signal_quality_scores']:
                    cur.execute(f"SELECT MAX(created_at) FROM {table_safe}")
                    max_created = cur.fetchone()[0]
                    if max_created:
                        if max_created.tzinfo is None:
                            max_created = max_created.replace(tzinfo=timezone.utc)
                        age_hours = (now_utc - max_created).total_seconds() / 3600
                        if age_hours > 24:
                            logger.critical(f"[FRESHNESS] {description}: {age_hours:.1f}h old (max 24h)")
                            stale_tables.append(f'{description} ({age_hours:.1f}h old)')
                            age_details[table_name]['status'] = 'stale'
                            age_details[table_name]['age_hours'] = age_hours

            except Exception as table_err:
                logger.warning(f"[FRESHNESS] Could not check {description}: {table_err}")
                age_details[table_name] = {'status': 'error', 'reason': str(table_err)[:50]}

        cur.close()
        conn.close()

        # Determine overall status
        if stale_tables:
            return {
                'status': 'critical' if len(stale_tables) > 2 else 'degraded',
                'stale_tables': stale_tables,
                'age_details': age_details
            }

        return {'status': 'ok', 'stale_tables': [], 'age_details': age_details}

    except Exception as e:
        logger.error(f"Data freshness check failed: {e}")
        return {
            'status': 'error',
            'error': str(e)[:100],
            'age_details': {}
        }

def lambda_handler(event, context):
    """Monitor data freshness and set halt flag if critical."""
    logger.info("Starting data freshness monitor check")

    freshness = check_critical_table_freshness()

    if freshness['status'] in ['degraded', 'critical']:
        logger.critical(f"[FRESHNESS] Data quality degraded: {freshness['stale_tables']}")

        # Set halt flag so orchestrator can detect and stop trading
        # Uses HaltFlagManager for dual-storage (DynamoDB + RDS redundancy)
        try:
            from utils.db.halt_flag import get_halt_flag_manager
            halt_manager = get_halt_flag_manager()
            reason = f"Data freshness degraded: {'; '.join(freshness['stale_tables'][:3])}"
            halt_manager.set_halt_flag(reason)
            logger.info(f"[FRESHNESS] Set halt flag: {reason}")
        except Exception as db_err:
            logger.error(f"[FRESHNESS] Could not set halt flag: {db_err}")

    return {
        'statusCode': 200 if freshness['status'] == 'ok' else 202,
        'body': json.dumps({
            'status': freshness['status'],
            'stale_tables': freshness.get('stale_tables', []),
            'age_details': freshness.get('age_details', {}),
            'timestamp': datetime.now(timezone.utc).isoformat()
        })
    }
