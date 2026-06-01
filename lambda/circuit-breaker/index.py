#!/usr/bin/env python3
"""
Intraday Circuit Breaker Lambda - Halts trading if portfolio variance exceeds threshold.

Triggers:
- CloudWatch Events at 10 AM and 12 PM ET (market hours)

Action:
- Check current portfolio P&L via database
- Calculate daily variance as (current_P&L - open_P&L) / portfolio_value
- If variance > threshold (e.g., 15%), set orchestrator_dry_run = true in Secrets Manager
- Orchestrator Phase 1 checks this flag and fails-closed

Resets:
- Manually reset via AWS Console or CLI after market close
"""

import json
import os
import boto3
import logging
from datetime import datetime, timezone

logger = logging.getLogger()
logger.setLevel(os.environ.get("LOG_LEVEL", "INFO"))

dynamodb = boto3.resource('dynamodb')
secretsmanager = boto3.client("secretsmanager")

def get_portfolio_pnl(db_connection):
    """Query current portfolio P&L from positions table."""
    import psycopg2
    try:
        with db_connection.cursor() as cur:
            # Get current portfolio snapshot: total equity and P&L
            cur.execute("""
                SELECT total_equity, unrealized_pnl
                FROM algo_portfolio_snapshots
                ORDER BY snapshot_date DESC, snapshot_time DESC
                LIMIT 1
            """)
            snapshot = cur.fetchone()
            if not snapshot:
                logger.warning("No portfolio snapshot found")
                return None, None, None

            total_equity = float(snapshot[0]) if snapshot[0] else 0
            current_pnl = float(snapshot[1]) if snapshot[1] else 0

            # Get open P&L from session start (market open)
            cur.execute("""
                SELECT SUM(unrealized_pnl) as session_pnl
                FROM algo_positions
                WHERE status = 'open'
            """)
            session_row = cur.fetchone()
            open_pnl = float(session_row[0]) if session_row and session_row[0] else 0

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
        import psycopg2
        from config.credential_manager import get_credential_manager

        # Get current orchestrator state from Secrets Manager
        secret = secretsmanager.get_secret_value(SecretId="algo/orchestrator")
        state = json.loads(secret["SecretString"])

        # Query database for portfolio P&L
        cred_mgr = get_credential_manager()
        db_creds = cred_mgr.get_db_credentials()

        db_connection = psycopg2.connect(
            host=db_creds['host'],
            port=db_creds['port'],
            database=db_creds['database'],
            user=db_creds['username'],
            password=db_creds['password']
        )

        current_pnl, open_pnl, variance = get_portfolio_pnl(db_connection)
        db_connection.close()

        if variance is None:
            logger.error("Unable to calculate variance — halting trading to be safe (fail-closed)")
            # Fail-closed: update DynamoDB halt flag
            table_name = os.getenv('HALT_FLAG_TABLE', 'algo_orchestrator_state')
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

        threshold = 0.15  # 15% threshold
        if variance > threshold:
            logger.critical(f"CIRCUIT BREAKER TRIGGERED: variance {variance:.1%} exceeds threshold {threshold:.1%}")

            # Update DynamoDB halt flag (Orchestrator checks this, not Secrets Manager)
            table_name = os.getenv('HALT_FLAG_TABLE', 'algo_orchestrator_state')
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
            # Clear halt flag when variance is within safe range
            table_name = os.getenv('HALT_FLAG_TABLE', 'algo_orchestrator_state')
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
        # Fail-closed: on any error, halt trading and update DynamoDB
        try:
            table_name = os.getenv('HALT_FLAG_TABLE', 'algo_orchestrator_state')
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
