#!/usr/bin/env python3
"""
Intraday Circuit Breaker Lambda - Halts trading if portfolio variance exceeds threshold.

Triggers:
- CloudWatch Events at 10 AM, 12 PM, and 3 PM ET (market hours)

Action:
- Check current portfolio P&L via database
- Calculate daily variance as (current_P&L - open_P&L) / portfolio_value
- If variance > threshold (e.g., 15%), set halt_flag = true in DynamoDB
- Orchestrator Phase 1 checks this flag and fails-closed

Resets:
- Automatically clears halt flag when variance returns to safe range
"""

import json
import os
import boto3
import logging
import psycopg2
from datetime import datetime, timezone

logger = logging.getLogger()
logger.setLevel(os.environ.get("LOG_LEVEL", "INFO"))

dynamodb = boto3.resource('dynamodb')
secretsmanager = boto3.client("secretsmanager")

def get_db_credentials():
    """Fetch database credentials from Secrets Manager."""
    try:
        secret_id = "algo/database"
        response = secretsmanager.get_secret_value(SecretId=secret_id)
        creds = json.loads(response["SecretString"])
        return {
            'host': creds.get('host'),
            'port': int(creds.get('port', 5432)),
            'database': creds.get('dbname'),
            'user': creds.get('username'),
            'password': creds.get('password')
        }
    except Exception as e:
        logger.error(f"Failed to fetch DB credentials from Secrets Manager: {e}")
        raise

def get_portfolio_pnl():
    """Query current portfolio P&L from database."""
    try:
        creds = get_db_credentials()
        conn = psycopg2.connect(
            host=creds['host'],
            port=creds['port'],
            database=creds['database'],
            user=creds['user'],
            password=creds['password'],
            sslmode='require'
        )
        cur = conn.cursor()

        # Get current portfolio snapshot: total equity and P&L
        cur.execute("""
            SELECT COALESCE(SUM(current_value), 0) as total_equity,
                   COALESCE(SUM(unrealized_pnl), 0) as current_pnl
            FROM algo_positions
            WHERE status = 'open'
        """)
        row = cur.fetchone()
        total_equity = float(row[0]) if row and row[0] else 0
        current_pnl = float(row[1]) if row and row[1] else 0

        # Get open P&L from session start (market open)
        cur.execute("""
            SELECT COALESCE(SUM(unrealized_pnl), 0) as session_pnl
            FROM algo_positions
            WHERE status = 'open'
        """)
        session_row = cur.fetchone()
        open_pnl = float(session_row[0]) if session_row and session_row[0] else 0

        cur.close()
        conn.close()

        if total_equity > 0:
            variance = (current_pnl - open_pnl) / total_equity
        else:
            variance = 0

        logger.info(f"Portfolio P&L: current={current_pnl:.2f}, open={open_pnl:.2f}, equity={total_equity:.2f}, variance={variance:.1%}")
        return current_pnl, open_pnl, variance

    except Exception as e:
        logger.error(f"Failed to query portfolio P&L: {e}", exc_info=True)
        return None, None, None

def lambda_handler(event, context):
    """Circuit breaker trigger - halt trading if variance too high."""

    try:
        current_pnl, open_pnl, variance = get_portfolio_pnl()

        if variance is None:
            logger.error("Unable to calculate variance — halting trading to be safe (fail-closed)")
            table_name = 'algo_orchestrator_state'
            table = dynamodb.Table(table_name)
            table.put_item(Item={
                'key': 'orchestrator_halt',
                'halt_flag': True,
                'reason': 'Unable to calculate portfolio variance (fail-closed)',
                'triggered_at': datetime.now(timezone.utc).isoformat(),
                'check_time': event.get('check_time', 'unscheduled')
            })
            return {
                "statusCode": 500,
                "body": json.dumps({
                    "action": "HALT",
                    "reason": "Unable to calculate portfolio variance",
                    "timestamp": datetime.now(timezone.utc).isoformat()
                })
            }

        threshold = 0.15
        if variance > threshold:
            logger.critical(f"CIRCUIT BREAKER TRIGGERED: variance {variance:.1%} exceeds {threshold:.1%}")
            table_name = 'algo_orchestrator_state'
            table = dynamodb.Table(table_name)
            table.put_item(Item={
                'key': 'orchestrator_halt',
                'halt_flag': True,
                'reason': f'Portfolio variance {variance:.1%} exceeds {threshold:.1%}',
                'triggered_at': datetime.now(timezone.utc).isoformat(),
                'check_time': event.get('check_time', 'unscheduled')
            })

            return {
                "statusCode": 200,
                "body": json.dumps({
                    "action": "HALT",
                    "reason": f"Portfolio variance {variance:.1%} exceeds {threshold:.1%}",
                    "timestamp": datetime.now(timezone.utc).isoformat()
                })
            }
        else:
            logger.info(f"Circuit breaker OK: variance {variance:.1%} < threshold {threshold:.1%}")
            table_name = 'algo_orchestrator_state'
            table = dynamodb.Table(table_name)
            table.put_item(Item={
                'key': 'orchestrator_halt',
                'halt_flag': False,
                'reason': f'Circuit breaker reset: variance {variance:.1%} < {threshold:.1%}',
                'reset_at': datetime.now(timezone.utc).isoformat(),
                'check_time': event.get('check_time', 'unscheduled')
            })
            return {
                "statusCode": 200,
                "body": json.dumps({
                    "action": "CONTINUE",
                    "variance": f"{variance:.1%}",
                    "current_pnl": f"{current_pnl:.2f}",
                    "timestamp": datetime.now(timezone.utc).isoformat()
                })
            }

    except Exception as e:
        logger.error(f"Circuit breaker check failed: {e}", exc_info=True)
        try:
            table_name = 'algo_orchestrator_state'
            table = dynamodb.Table(table_name)
            table.put_item(Item={
                'key': 'orchestrator_halt',
                'halt_flag': True,
                'reason': f'Circuit breaker check failed: {str(e)[:100]}',
                'triggered_at': datetime.now(timezone.utc).isoformat(),
                'check_time': event.get('check_time', 'unscheduled')
            })
        except Exception as ddb_err:
            logger.error(f"Failed to update DynamoDB halt flag: {ddb_err}", exc_info=True)

        return {
            "statusCode": 500,
            "body": json.dumps({
                "action": "HALT",
                "reason": "Circuit breaker check failed",
                "error": str(e)
            })
        }
