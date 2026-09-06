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
from typing import Any

import boto3
import psycopg2

logger = logging.getLogger()
logger.setLevel(os.environ.get("LOG_LEVEL", "INFO"))

# Add project root to path for importing config module
sys.path.insert(0, str(Path(__file__).parent.parent.parent))

from utils.data_queries import get_open_portfolio_totals  # noqa: E402

dynamodb = boto3.resource("dynamodb")
sns_client = boto3.client("sns")

SNS_ALERT_TOPIC_ARN = os.environ.get("SNS_ALERT_TOPIC_ARN", "")


def get_db_credentials():
    try:
        from algo.config.credential_manager import get_db_credentials as get_db_creds

        return get_db_creds()
    except ImportError:
        logger.warning("Could not import credential_manager, falling back to direct Secrets Manager fetch")
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

            # Validate port is numeric before converting
            port_str = str(creds.get("port"))
            try:
                port_int = int(port_str)
                if port_int <= 0 or port_int > 65535:
                    raise ValueError(f"Port out of valid range (1-65535): {port_int}")
            except ValueError as e:
                raise ValueError(f"Database port must be numeric (1-65535), got: {port_str}") from e

            return {
                "host": creds.get("host"),
                "port": port_int,
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
            # Use centralized data query (single source of truth)
            portfolio_data = get_open_portfolio_totals(cur)
            total_equity = portfolio_data.get("total_equity")
            current_pnl = portfolio_data.get("current_pnl")
            if total_equity is None or current_pnl is None:
                raise RuntimeError(
                    f"Circuit breaker: Portfolio data unavailable: total_equity={total_equity}, current_pnl={current_pnl} (no open positions or data missing)"
                )
            total_equity = float(total_equity)
            current_pnl = float(current_pnl)

            # Get session opening P&L snapshot (captured at market open).
            # CRITICAL: Do NOT use COALESCE(..., 0) - must detect missing snapshots
            cur.execute("""
                SELECT unrealized_pnl_total as session_open_pnl
                FROM algo_portfolio_snapshots
                WHERE snapshot_date = CURRENT_DATE
                LIMIT 1
            """)
            session_row = cur.fetchone()
            if session_row is None:
                raise RuntimeError(
                    "Circuit breaker: Session opening P&L snapshot not found (market may not have opened yet)"
                )
            if session_row[0] is None:
                raise RuntimeError("Circuit breaker: Session opening P&L value is NULL (data quality issue)")
            open_pnl = float(session_row[0])

            cur.close()
            conn.close()

            intraday_change = current_pnl - open_pnl
            if total_equity <= 0:
                logger.error(f"Cannot calculate portfolio variance: total_equity invalid ({total_equity})")
                variance = None
            else:
                variance = intraday_change / total_equity

            logger.info(
                f"Portfolio variance: current_pnl=${current_pnl:.2f}, open_pnl=${open_pnl:.2f}, "
                f"equity=${total_equity:.2f}, intraday_change=${intraday_change:.2f}, variance={variance if variance is not None else 'INVALID'}"
            )
            return current_pnl, open_pnl, variance

        except (ValueError, ZeroDivisionError, TypeError) as e:
            last_err = e
            logger.warning(f"DB attempt {attempt}/{max_attempts} failed: {e}")
            if attempt < max_attempts:
                time.sleep(3 * attempt)

    logger.error(f"Failed to query portfolio P&L after {max_attempts} attempts: {last_err}")
    raise RuntimeError(
        f"Circuit breaker: Unable to calculate portfolio P&L after {max_attempts} retries. "
        f"Final error: {last_err}. Failing fast to prevent trading on stale variance data."
    ) from last_err


class _NoOpAlerts:
    """Minimal stand-in for the AlertManager HaltFlagManager expects - this Lambda has its
    own SNS-based alerting (_send_alert below) for circuit-breaker-specific messages;
    HaltFlagManager's own escalation alert (repeated-halt-in-one-day) is a nice-to-have,
    not something this narrow caller needs to wire up, but it must not crash if
    HaltFlagManager ever calls it (that call is best-effort/try-except'd internally, but
    only against a narrow exception tuple - see set_halt_flag's own escalation block)."""

    def send_position_alert(self, *args: Any, **kwargs: Any) -> None:
        return None


def _get_halt_flag_manager() -> Any:
    from algo.orchestration.halt_flag_manager import HaltFlagManager

    return HaltFlagManager(alerts=_NoOpAlerts(), log_phase_result=lambda *a, **k: None)


def _set_halt(table, halt: bool, reason: str, check_time: str) -> bool:
    """Set/clear the halt flag via HaltFlagManager - the same origin-aware primitive
    every other halt source in this codebase uses (orchestrator.py's phases, the manual
    operator kill switch).

    SAFETY BUG FOUND (2026-09-06 real-money-readiness dig): this used to write halt_flag
    directly to RDS/DynamoDB via raw UPSERTs (_set_halt_flag_rds/_set_halt_flag_dynamodb,
    both now removed), unconditionally overwriting whatever halt state existed - including
    an unrelated halt set by a completely different source (Phase 9's reconciliation-
    governance halt, a manual operator halt, another phase's data-integrity halt). Every
    scheduled run where THIS circuit breaker's own variance happened to look fine would
    silently clear ANY active halt and send a "TRADING RESUMED" alert, regardless of why
    trading was actually halted - exactly the "origin bug" halt_flag_manager.py's own
    clear_halt_flag() docstring says its origin-check exists to prevent (see
    halt_flag_cleared_by_unrelated_phase_fix_20260810), but this Lambda never adopted that
    primitive in the first place.

    For halt=True: always sets, tagged triggered_by="circuit_breaker" (sticky-to-first-
    trigger semantics in set_halt_flag mean this never clobbers an already-active halt
    from a different origin either).

    For halt=False (the recovery/auto-clear path): only actually clears if the CURRENTLY
    active halt's origin is "circuit_breaker" itself (or nothing is halted) - refuses
    (returns False, halt stays exactly as-is) if some other origin is holding it. The
    `table` parameter is now unused (kept so existing call sites don't all need touching)
    - HaltFlagManager manages its own DynamoDB/RDS access internally.

    Returns: True if the requested state was actually applied; False if a clear was
    refused because a different origin holds the active halt (never raises for that
    case - refusing to clear is always the safe direction, same contract clear_halt_flag
    itself documents).
    """
    manager = _get_halt_flag_manager()
    if halt:
        manager.set_halt_flag(reason=reason, triggered_by="circuit_breaker")
        logger.critical(f"[CIRCUIT_BREAKER] Halt flag set via HaltFlagManager: reason={reason}")
        return True

    current_trigger = manager.get_halt_triggered_by()
    cleared = manager.clear_halt_flag(reason=reason, allowed_triggers=frozenset({"circuit_breaker", None}))
    if cleared:
        logger.critical(f"[CIRCUIT_BREAKER] Halt flag cleared via HaltFlagManager: reason={reason}")
    else:
        logger.warning(
            f"[CIRCUIT_BREAKER] Variance back to safe range, but NOT auto-clearing - active halt was "
            f"triggered_by={current_trigger!r}, not this circuit breaker. Refusing to resume trading "
            "on an unrelated halt's behalf."
        )
    return cleared


def _send_alert(action: str, reason: str, variance: float | None = None, threshold: float | None = None) -> None:
    """Send SNS alert for circuit breaker event."""
    if not SNS_ALERT_TOPIC_ARN:
        logger.warning("SNS_ALERT_TOPIC_ARN not configured - skipping email alert")
        return

    try:
        subject = f"[Portfolio {action}] Circuit Breaker Alert"

        if action == "HALT":
            body = f"""Portfolio Circuit Breaker TRIGGERED

Action: TRADING HALTED
Reason: {reason}
Check Time: {datetime.now(timezone.utc).isoformat()}

Portfolio Variance: {variance:.1%} (Threshold: {threshold:.1%})

All trading activity has been suspended to protect the portfolio.

This circuit breaker will automatically resume trading on its own next scheduled
check once variance returns below the threshold - it does NOT wait for manual
clearance. If you need trading to stay halted regardless of variance (e.g. pending
root-cause review), set an operator-triggered halt via scripts/manage_halt_flag.py
instead of relying on this alert - a plain variance recovery will otherwise
auto-resume as designed."""
        else:
            body = f"""Portfolio Circuit Breaker RESET

Action: TRADING RESUMED
Reason: {reason}
Check Time: {datetime.now(timezone.utc).isoformat()}

Portfolio Variance: {variance:.1%} (Threshold: {threshold:.1%})

Portfolio variance returned to safe levels. Trading has resumed normal operations.
Monitor continuously for any abnormalities."""

        sns_client.publish(
            TopicArn=SNS_ALERT_TOPIC_ARN,
            Subject=subject,
            Message=body,
        )
        logger.info(f"Sent SNS alert: {action}")
    except Exception as e:
        logger.error(f"Failed to send SNS alert: {e}")


def lambda_handler(event, context):
    """Circuit breaker trigger - halt trading if variance too high."""
    check_time = event.get("check_time", "unscheduled")
    table = dynamodb.Table("algo_orchestrator_state")

    try:
        try:
            current_pnl, _, variance = get_portfolio_pnl()
        except RuntimeError as pnl_err:
            logger.error(f"Portfolio P&L calculation failed (fail-closed): {pnl_err}")
            try:
                _set_halt(
                    table,
                    True,
                    f"Portfolio P&L calculation failed: {str(pnl_err)[:80]}",
                    check_time,
                )
            except (RuntimeError, Exception) as halt_err:
                logger.critical(f"CRITICAL: Failed to set halt flag on P&L failure: {halt_err}")
                raise
            return {
                "statusCode": 500,
                "body": json.dumps(
                    {
                        "action": "HALT",
                        "reason": "Portfolio P&L calculation failed - halting for safety",
                        "timestamp": datetime.now(timezone.utc).isoformat(),
                    }
                ),
            }

        if variance is None:
            logger.error("Unable to calculate variance after retries - halting trading (fail-closed)")
            try:
                _set_halt(
                    table,
                    True,
                    "Unable to calculate portfolio variance after retries (fail-closed)",
                    check_time,
                )
            except (RuntimeError, Exception) as halt_err:
                logger.critical(f"CRITICAL: Failed to set halt flag on variance=None: {halt_err}")
                raise
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
        from algo.infrastructure import get_config

        threshold = float(get_config().get("portfolio_variance_threshold"))

        if variance > threshold:
            logger.critical(f"CIRCUIT BREAKER TRIGGERED: variance {variance:.1%} exceeds {threshold:.1%}")
            reason = f"Portfolio variance {variance:.1%} exceeds {threshold:.1%}"
            try:
                _set_halt(table, True, reason, check_time)
                _send_alert("HALT", reason, variance, threshold)
            except (RuntimeError, Exception) as halt_err:
                logger.critical(f"CRITICAL: Failed to set halt flag on threshold breach: {halt_err}")
                raise
            return {
                "statusCode": 200,
                "body": json.dumps(
                    {
                        "action": "HALT",
                        "reason": reason,
                        "timestamp": datetime.now(timezone.utc).isoformat(),
                    }
                ),
            }
        else:
            logger.info(f"Circuit breaker OK: variance {variance:.1%} < threshold {threshold:.1%}")
            reason = f"Circuit breaker reset: variance {variance:.1%} < {threshold:.1%}"
            try:
                # _set_halt(False, ...) only actually clears if THIS circuit breaker is the
                # active halt's origin (or nothing is halted) - see its own docstring. A
                # different origin's halt (e.g. Phase 9 governance, a manual operator halt)
                # is deliberately left in place: this check's own variance recovering must
                # never be read as license to resume trading a human/another system halted
                # for an unrelated reason.
                cleared = _set_halt(table, False, reason, check_time)
                if cleared:
                    _send_alert("CONTINUE", reason, variance, threshold)
                else:
                    logger.info(
                        "[CIRCUIT_BREAKER] Variance recovered but trading remains halted - "
                        "active halt belongs to a different origin, not auto-clearing."
                    )
            except (RuntimeError, Exception) as halt_err:
                logger.critical(f"CRITICAL: Failed to reset halt flag: {halt_err}")
                raise
            return {
                "statusCode": 200,
                "body": json.dumps(
                    {
                        "action": "CONTINUE" if cleared else "VARIANCE_OK_HALT_UNRELATED_ORIGIN",
                        "variance": f"{variance:.1%}",
                        "current_pnl": f"{current_pnl:.2f}",
                        "timestamp": datetime.now(timezone.utc).isoformat(),
                    }
                ),
            }

    except (json.JSONDecodeError, ValueError) as e:
        logger.error(f"Circuit breaker check failed: {e}", exc_info=True)
        try:
            _set_halt(table, True, f"Circuit breaker check failed: {str(e)[:100]}", check_time)
        except (json.JSONDecodeError, ValueError) as ddb_err:
            logger.error(f"Failed to update DynamoDB halt flag: {ddb_err}", exc_info=True)

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
