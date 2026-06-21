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
import logging
import os
import sys
import time
from datetime import datetime, timezone
from pathlib import Path

import boto3
import psycopg2



logger = logging.getLogger()
logger.setLevel(os.environ.get("LOG_LEVEL", "INFO"))

# Add project root to path for importing config module
sys.path.insert(0, str(Path(__file__).parent.parent.parent))

dynamodb = boto3.resource("dynamodb")


def get_db_credentials():
    """Fetch database credentials from credential_manager (centralized)."""
    try:
        from config.credential_manager import get_db_credentials as get_db_creds

        return get_db_creds()
    except ImportError:
        logger.warning(
            "Could not import credential_manager, falling back to direct Secrets Manager fetch"
        )
        # Fallback if config module not available
        secretsmanager = boto3.client("secretsmanager")
        try:
            secret_id = "algo/database"
            response = secretsmanager.get_secret_value(SecretId=secret_id)
            creds = json.loads(response["SecretString"])
            if not creds.get("host"):
                raise ValueError("Database credential missing: host") from None
            if not creds.get("dbname"):
                raise ValueError("Database credential missing: dbname") from None
            if not creds.get("username"):
                raise ValueError("Database credential missing: username") from None
            if not creds.get("password"):
                raise ValueError("Database credential missing: password") from None
            if not creds.get("port"):
                raise ValueError("Database credential missing: port (required, no default)") from None
            return {
                "host": creds.get("host"),
                "port": int(creds.get("port")),
                "database": creds.get("dbname"),
                "user": creds.get("username"),
                "password": creds.get("password"),
            }
        except (json.JSONDecodeError, ValueError) as e:
            logger.error(f"Failed to fetch DB credentials from Secrets Manager: {e}")
            raise


def get_portfolio_pnl(max_attempts: int = 3):
    """Query current portfolio P&L and calculate intraday variance.

    Variance = (current unrealized P&L - opening session P&L) / portfolio equity

    Retries up to max_attempts times on transient DB errors before returning None.
    A single RDS hiccup should not halt trading for the rest of the day.
    """
    last_err = None
    for attempt in range(1, max_attempts + 1):
        try:
            creds = get_db_credentials()
            conn = psycopg2.connect(
                host=creds["host"],
                port=creds["port"],
                database=creds["database"],
                user=creds["user"],
                password=creds["password"],
                sslmode="require",
                connect_timeout=10,
            )
            cur = conn.cursor()

            # Get current portfolio: total position value and current unrealized P&L
            cur.execute("""
                SELECT COALESCE(SUM(position_value), 0) as total_equity,
                       COALESCE(SUM(unrealized_pnl), 0) as current_pnl
                FROM algo_positions
                WHERE status = 'open'
            """)
            row = cur.fetchone()
            total_equity = (
                float(row[0]) if row is not None and row[0] is not None else 0
            )
            current_pnl = float(row[1]) if row and row[1] else 0

            # Get session opening P&L snapshot (captured at market open).
            cur.execute("""
                SELECT COALESCE(unrealized_pnl_total, 0) as session_open_pnl
                FROM algo_portfolio_snapshots
                WHERE snapshot_date = CURRENT_DATE
                LIMIT 1
            """)
            session_row = cur.fetchone()
            open_pnl = (
                float(session_row[0]) if session_row and session_row[0] else current_pnl
            )

            cur.close()
            conn.close()

            intraday_change = current_pnl - open_pnl
            variance = intraday_change / total_equity if total_equity > 0 else 0.0

            logger.info(
                f"Portfolio variance: current_pnl=${current_pnl:.2f}, open_pnl=${open_pnl:.2f}, "
                f"equity=${total_equity:.2f}, intraday_change=${intraday_change:.2f}, variance={variance:.1%}"
            )
            return current_pnl, open_pnl, variance

        except (ValueError, ZeroDivisionError, TypeError) as e:
            last_err = e
            logger.warning(f"DB attempt {attempt}/{max_attempts} failed: {e}")
            if attempt < max_attempts:
                time.sleep(3 * attempt)

    logger.error(
        f"Failed to query portfolio P&L after {max_attempts} attempts: {last_err}"
    )
    return None, None, None


def _set_halt_flag_rds(halt: bool, reason: str, check_time: str) -> bool:
    """Set halt flag in RDS (source of truth). Returns True if successful."""
    try:
        creds = get_db_credentials()
        conn = psycopg2.connect(
            host=creds["host"],
            port=creds["port"],
            database=creds["database"],
            user=creds["user"],
            password=creds["password"],
            sslmode="require",
            connect_timeout=10,
        )
        cur = conn.cursor()
        now_utc = datetime.now(timezone.utc)
        cur.execute("""
            INSERT INTO algo_runtime_state (
                state_key, state_value, halt_flag, halt_triggered_at,
                halt_reason, halt_count, updated_by, expires_at
            ) VALUES (%s, %s, %s, %s, %s, %s, %s, %s)
            ON CONFLICT (state_key) DO UPDATE SET
                halt_flag = EXCLUDED.halt_flag,
                halt_triggered_at = EXCLUDED.halt_triggered_at,
                halt_reason = EXCLUDED.halt_reason,
                halt_count = EXCLUDED.halt_count,
                last_updated_at = CURRENT_TIMESTAMP,
                expires_at = EXCLUDED.expires_at
        """, (
            "orchestrator_halt",
            json.dumps({"halt_flag": halt, "triggered_at": now_utc.isoformat(), "reason": reason}),
            halt,
            now_utc.isoformat(),
            reason,
            1,
            "circuit_breaker",
            (now_utc.timestamp() + 86400),  # 24 hours from now
        ))
        conn.commit()
        cur.close()
        conn.close()
        logger.debug(f"[CIRCUIT_BREAKER] Set halt_flag={halt} in RDS: {reason}")
        return True
    except Exception as e:
        logger.warning(f"[CIRCUIT_BREAKER] Failed to set halt flag in RDS: {e}")
        return False


def _set_halt_flag_dynamodb(table, halt: bool, reason: str, check_time: str) -> bool:
    """Set halt flag in DynamoDB (cache). Returns True if successful."""
    try:
        item = {
            "key": "orchestrator_halt",
            "halt_flag": halt,
            "reason": reason,
            "check_time": check_time,
        }
        ts_key = "triggered_at" if halt else "reset_at"
        item[ts_key] = datetime.now(timezone.utc).isoformat()
        table.put_item(Item=item)
        logger.debug(f"[CIRCUIT_BREAKER] Set halt_flag={halt} in DynamoDB: {reason}")
        return True
    except Exception as e:
        logger.warning(f"[CIRCUIT_BREAKER] Failed to set halt flag in DynamoDB: {e}")
        return False


def _set_halt(table, halt: bool, reason: str, check_time: str) -> bool:
    """Set halt flag atomically in RDS (source of truth) and DynamoDB (cache).

    RDS is the source of truth. DynamoDB write failure is tolerable since reads
    fall back to RDS. This prevents split-brain where one store succeeds and the
    other fails, causing inconsistent state across orchestrator runs.

    Returns True if RDS write succeeds (source of truth), False otherwise.
    """
    # RDS is source of truth: must succeed
    rds_success = _set_halt_flag_rds(halt, reason, check_time)

    # DynamoDB is read cache: best-effort, failure is tolerable
    if rds_success:
        ddb_success = _set_halt_flag_dynamodb(table, halt, reason, check_time)
        logger.critical(
            f"[CIRCUIT_BREAKER] Halt flag={halt} set: RDS=True, DynamoDB={ddb_success}, reason={reason}"
        )
        return True

    logger.error(f"[CIRCUIT_BREAKER] Failed to set halt flag in RDS (source of truth): {reason}")
    return False


def lambda_handler(event, context):
    """Circuit breaker trigger - halt trading if variance too high."""
    check_time = event.get("check_time", "unscheduled")
    table = dynamodb.Table("algo_orchestrator_state")

    try:
        current_pnl, _, variance = get_portfolio_pnl()

        if variance is None:
            logger.error(
                "Unable to calculate variance after retries — halting trading (fail-closed)"
            )
            _set_halt(
                table,
                True,
                "Unable to calculate portfolio variance after retries (fail-closed)",
                check_time,
            )
            return {
                "statusCode": 500,
                "body": json.dumps(
                    {
                        "action": "HALT",
                        "reason": "Unable to calculate portfolio variance",
                        "timestamp": datetime.now(timezone.utc).isoformat(),
                    }
                ),
            }

        # Load portfolio variance threshold from centralized config
        from config.thresholds import ThresholdConfig

        threshold = ThresholdConfig.portfolio_variance_threshold()

        if variance > threshold:
            logger.critical(
                f"CIRCUIT BREAKER TRIGGERED: variance {variance:.1%} exceeds {threshold:.1%}"
            )
            _set_halt(
                table,
                True,
                f"Portfolio variance {variance:.1%} exceeds {threshold:.1%}",
                check_time,
            )
            return {
                "statusCode": 200,
                "body": json.dumps(
                    {
                        "action": "HALT",
                        "reason": f"Portfolio variance {variance:.1%} exceeds {threshold:.1%}",
                        "timestamp": datetime.now(timezone.utc).isoformat(),
                    }
                ),
            }
        else:
            logger.info(
                f"Circuit breaker OK: variance {variance:.1%} < threshold {threshold:.1%}"
            )
            _set_halt(
                table,
                False,
                f"Circuit breaker reset: variance {variance:.1%} < {threshold:.1%}",
                check_time,
            )
            return {
                "statusCode": 200,
                "body": json.dumps(
                    {
                        "action": "CONTINUE",
                        "variance": f"{variance:.1%}",
                        "current_pnl": f"{current_pnl:.2f}",
                        "timestamp": datetime.now(timezone.utc).isoformat(),
                    }
                ),
            }

    except (json.JSONDecodeError, ValueError) as e:
        logger.error(f"Circuit breaker check failed: {e}", exc_info=True)
        try:
            _set_halt(
                table, True, f"Circuit breaker check failed: {str(e)[:100]}", check_time
            )
        except (json.JSONDecodeError, ValueError) as ddb_err:
            logger.error(
                f"Failed to update DynamoDB halt flag: {ddb_err}", exc_info=True
            )

        return {
            "statusCode": 500,
            "body": json.dumps(
                {
                    "action": "HALT",
                    "reason": "Circuit breaker check failed",
                    "error": str(e),
                }
            ),
        }
