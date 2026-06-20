"""
Data Freshness Monitor Lambda

Monitors the freshness of critical pipeline tables and halts trading if data becomes stale.
Runs every 6 hours via EventBridge.
"""

import json
import logging
import os
import re
from datetime import datetime, timezone

import boto3
import psycopg2


logger = logging.getLogger()
logger.setLevel(logging.INFO)

_SAFE_TABLE_RE = re.compile(r"^[a-z][a-z0-9_]{1,63}$")


def _safe_table(name: str) -> str:
    if not _SAFE_TABLE_RE.match(name):
        raise ValueError(f"Unsafe table name: {name!r}")
    return name


def _get_db_password() -> str:
    secret_arn = os.environ.get("DATABASE_SECRET_ARN")
    if secret_arn:
        client = boto3.client(
            "secretsmanager",
            region_name=os.environ.get("AWS_REGION", "us-east-1"),
        )
        response = client.get_secret_value(SecretId=secret_arn)
        return json.loads(response["SecretString"]).get("password", "")
    return os.environ.get("DB_PASSWORD", "")


def _get_db_connection():
    db_host = os.environ.get("DB_HOST")
    db_port_str = os.environ.get("DB_PORT")
    db_name = os.environ.get("DB_NAME")
    db_user = os.environ.get("DB_USER")
    db_ssl = os.environ.get("DB_SSL", "require")

    if not db_host:
        raise ValueError("DB_HOST environment variable is REQUIRED")
    if not db_port_str:
        raise ValueError("DB_PORT environment variable is REQUIRED")
    if not db_name:
        raise ValueError("DB_NAME environment variable is REQUIRED")
    if not db_user:
        raise ValueError("DB_USER environment variable is REQUIRED")

    try:
        return psycopg2.connect(
            host=db_host,
            port=int(db_port_str),
            database=db_name,
            user=db_user,
            password=_get_db_password(),
            connect_timeout=10,
            sslmode=db_ssl,
        )
    except (json.JSONDecodeError, ValueError) as e:
        logger.error(f"Database connection failed: {e}")
        raise


# Tables that trigger a halt flag when stale — must match Phase 1 HALT tables exactly.
# swing_trader_scores, trend_template_data, sector_ranking are WARN-only in Phase 1
# and must NOT be here; setting the halt flag for them would block all trading whenever
# these auxiliary tables are more than a few days old (e.g. after a 3-day weekend).
_HALT_TABLES = {
    "price_daily":           ("prices",         2),
    "market_health_daily":   ("market health",  2),
    "market_exposure_daily": ("market exposure", 2),
}

# Warn-only tables — logged for visibility but never trigger a halt flag.
_WARN_TABLES = {
    "swing_trader_scores": ("swing scores",   5),
    "trend_template_data": ("trend template", 5),
    "sector_ranking":      ("sector data",    5),
}

_CRITICAL_TABLES = {**_HALT_TABLES, **_WARN_TABLES}


def _check_critical_table_freshness() -> dict:
    try:
        conn = _get_db_connection()
        cur = conn.cursor()
        now_date = datetime.now(timezone.utc).date()
        # halt_stale: HALT tables (price_daily, market_health_daily, market_exposure_daily)
        # warn_stale: WARN-only tables (swing_trader_scores, trend_template_data, sector_ranking)
        halt_stale = []
        warn_stale = []
        age_details = {}

        for table_name, (description, max_age_days) in _CRITICAL_TABLES.items():
            is_halt_table = table_name in _HALT_TABLES
            try:
                cur.execute(f"SELECT MAX(date) FROM {_safe_table(table_name)}")
                row = cur.fetchone()
                max_date = row[0] if row and row[0] is not None else None
                if max_date is None:
                    msg = f"{description} (empty)"
                    logger.warning(f"[FRESHNESS] {description} table is EMPTY")
                    age_details[table_name] = {"status": "empty"}
                    if is_halt_table:
                        halt_stale.append(msg)
                    else:
                        warn_stale.append(msg)
                    continue
                age_days = (now_date - max_date).days
                if age_days > max_age_days:
                    msg = f"{description} ({age_days}d old)"
                    logger.warning(
                        f"[FRESHNESS] {description}: {age_days}d old (max {max_age_days}d)"
                    )
                    age_details[table_name] = {"status": "stale", "age_days": age_days}
                    if is_halt_table:
                        halt_stale.append(msg)
                    else:
                        warn_stale.append(msg)
                else:
                    age_details[table_name] = {
                        "status": "ok",
                        "age_days": age_days,
                        "latest_date": str(max_date),
                    }
            except (psycopg2.DatabaseError, psycopg2.OperationalError) as table_err:
                logger.warning(f"[FRESHNESS] Could not check {description}: {table_err}")
                age_details[table_name] = {
                    "status": "error",
                    "reason": str(table_err)[:100],
                }

        cur.close()
        conn.close()

        if warn_stale:
            logger.warning(f"[FRESHNESS] Warn-only stale tables (no halt): {'; '.join(warn_stale)}")

        # Status and halt flag are driven by HALT tables only (matching Phase 1 behavior).
        # WARN tables (swing_trader_scores, trend_template_data, sector_ranking) are
        # logged above but never trigger a halt flag — Phase 1 treats them as warnings.
        all_stale = halt_stale + warn_stale
        if len(halt_stale) > 2:
            return {"status": "critical", "stale_tables": all_stale, "halt_stale": halt_stale, "age_details": age_details}
        if halt_stale:
            return {"status": "degraded", "stale_tables": all_stale, "halt_stale": halt_stale, "age_details": age_details}
        return {"status": "ok", "stale_tables": all_stale, "halt_stale": [], "age_details": age_details}

    except Exception as e:
        logger.error(f"Data freshness check failed: {e}")
        return {"status": "error", "error": str(e)[:100], "age_details": {}}


def _set_halt_flag_atomically(reason: str) -> bool:
    """Set halt flag atomically in RDS (source of truth) and DynamoDB (cache).

    RDS is the source of truth. DynamoDB write failure is tolerable since reads
    fall back to RDS. This prevents split-brain where one store succeeds and the
    other fails, causing inconsistent state across orchestrator runs.
    """
    now_utc = datetime.now(timezone.utc)

    # Write to RDS first (source of truth)
    rds_success = _set_halt_flag_rds(reason, now_utc)

    # Write to DynamoDB (cache) as best-effort if RDS succeeded
    if rds_success:
        ddb_success = _set_halt_flag_dynamodb(reason, now_utc)
        logger.critical(
            f"[FRESHNESS] Halt flag set: RDS=True, DynamoDB={ddb_success}, reason={reason}"
        )
        return True

    logger.error(f"[FRESHNESS] Failed to set halt flag in RDS (source of truth): {reason}")
    return False


def _set_halt_flag_rds(reason: str, now_utc: datetime) -> bool:
    """Set halt flag in RDS. Returns True if successful."""
    try:
        conn = _get_db_connection()
        cur = conn.cursor()
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
            json.dumps({"halt_flag": True, "triggered_at": now_utc.isoformat(), "reason": reason}),
            True,
            now_utc.isoformat(),
            reason,
            1,
            "data_freshness_monitor",
            (now_utc.timestamp() + 86400),  # 24 hours from now
        ))
        conn.commit()
        cur.close()
        conn.close()
        logger.debug(f"[FRESHNESS] Set halt flag in RDS: {reason}")
        return True
    except Exception as e:
        logger.warning(f"[FRESHNESS] Failed to set halt flag in RDS: {e}")
        return False


def _set_halt_flag_dynamodb(reason: str, now_utc: datetime) -> bool:
    """Set halt flag in DynamoDB (cache). Returns True if successful."""
    table_name = os.environ.get("HALT_FLAG_TABLE", "algo_orchestrator_state")
    try:
        ddb = boto3.resource("dynamodb", region_name=os.environ.get("AWS_REGION", "us-east-1"))
        table = ddb.Table(table_name)
        table.put_item(Item={
            "key": "orchestrator_halt",
            "halt_flag": True,
            "halt_reason": reason,
            "halt_triggered_at": now_utc.isoformat(),
            "source": "data_freshness_monitor",
        })
        logger.debug(f"[FRESHNESS] Set halt flag in DynamoDB: {reason}")
        return True
    except Exception as e:
        logger.warning(f"[FRESHNESS] Failed to set halt flag in DynamoDB: {e}")
        return False


def lambda_handler(event, context):
    logger.info("Starting data freshness monitor check")
    freshness = _check_critical_table_freshness()

    # Only set halt flag for HALT-table staleness (price_daily, market_health_daily,
    # market_exposure_daily). WARN tables are already logged in _check_critical_table_freshness
    # but must never trigger the halt flag — Phase 1 treats them as non-blocking warnings.
    halt_stale = freshness.get("halt_stale", [])
    if halt_stale:
        logger.critical(
            f"[FRESHNESS] HALT-table staleness detected: {halt_stale}"
        )
        reason = f"Critical pipeline data stale: {'; '.join(halt_stale[:3])}"
        _set_halt_flag_atomically(reason)
    elif freshness["status"] in ["degraded", "critical"]:
        logger.warning(
            f"[FRESHNESS] Warn-only staleness (no halt): {freshness.get('stale_tables', [])}"
        )

    return {
        "statusCode": 200 if freshness["status"] == "ok" else 202,
        "body": json.dumps({
            "status": freshness["status"],
            "stale_tables": freshness.get("stale_tables", []),
            "age_details": freshness.get("age_details", {}),
            "timestamp": datetime.now(timezone.utc).isoformat(),
        }),
    }
