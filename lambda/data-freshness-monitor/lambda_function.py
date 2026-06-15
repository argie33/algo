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
    try:
        return psycopg2.connect(
            host=os.environ.get("DB_HOST"),
            port=int(os.environ.get("DB_PORT", "5432")),
            database=os.environ.get("DB_NAME"),
            user=os.environ.get("DB_USER"),
            password=_get_db_password(),
            connect_timeout=10,
            sslmode=os.environ.get("DB_SSL", "require"),
        )
    except Exception as e:
        logger.error(f"Database connection failed: {e}")
        raise


# Active pipeline tables only. buy_sell_daily, technical_data_daily, and
# signal_quality_scores were removed from all pipelines. swing_trader_scores
# runs weekly (Mon AM), so stale threshold is 5 days.
_CRITICAL_TABLES = {
    "price_daily":          ("prices",         2),
    "market_health_daily":  ("market health",  2),
    "market_exposure_daily": ("market exposure", 2),
    "swing_trader_scores":  ("swing scores",   5),
    "trend_template_data":  ("trend template", 5),
    "sector_ranking":       ("sector data",    5),
}


def _check_critical_table_freshness() -> dict:
    try:
        conn = _get_db_connection()
        cur = conn.cursor()
        now_date = datetime.now(timezone.utc).date()
        stale_tables = []
        age_details = {}

        for table_name, (description, max_age_days) in _CRITICAL_TABLES.items():
            try:
                cur.execute(f"SELECT MAX(date) FROM {_safe_table(table_name)}")
                max_date = cur.fetchone()[0]
                if max_date is None:
                    logger.warning(f"[FRESHNESS] {description} table is EMPTY")
                    stale_tables.append(f"{description} (empty)")
                    age_details[table_name] = {"status": "empty"}
                    continue
                age_days = (now_date - max_date).days
                if age_days > max_age_days:
                    logger.warning(
                        f"[FRESHNESS] {description}: {age_days}d old (max {max_age_days}d)"
                    )
                    stale_tables.append(f"{description} ({age_days}d old)")
                    age_details[table_name] = {"status": "stale", "age_days": age_days}
                else:
                    age_details[table_name] = {
                        "status": "ok",
                        "age_days": age_days,
                        "latest_date": str(max_date),
                    }
            except Exception as table_err:
                logger.warning(f"[FRESHNESS] Could not check {description}: {table_err}")
                age_details[table_name] = {
                    "status": "error",
                    "reason": str(table_err)[:100],
                }

        cur.close()
        conn.close()

        if len(stale_tables) > 2:
            return {"status": "critical", "stale_tables": stale_tables, "age_details": age_details}
        if stale_tables:
            return {"status": "degraded", "stale_tables": stale_tables, "age_details": age_details}
        return {"status": "ok", "stale_tables": [], "age_details": age_details}

    except Exception as e:
        logger.error(f"Data freshness check failed: {e}")
        return {"status": "error", "error": str(e)[:100], "age_details": {}}


def _set_halt_flag_dynamodb(reason: str) -> bool:
    """Set halt flag in DynamoDB so the orchestrator stops trading."""
    table_name = os.environ.get("HALT_FLAG_TABLE", "algo_orchestrator_state")
    now_utc = datetime.now(timezone.utc)
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
        logger.info(f"[FRESHNESS] Set DynamoDB halt flag: {reason}")
        return True
    except Exception as e:
        logger.error(f"[FRESHNESS] Could not set DynamoDB halt flag: {e}")
        return False


def lambda_handler(event, context):
    logger.info("Starting data freshness monitor check")
    freshness = _check_critical_table_freshness()

    if freshness["status"] in ["degraded", "critical"]:
        logger.critical(
            f"[FRESHNESS] Data quality {freshness['status']}: {freshness.get('stale_tables', [])}"
        )
        reason = f"Data freshness {freshness['status']}: {'; '.join(freshness.get('stale_tables', [])[:3])}"
        _set_halt_flag_dynamodb(reason)

    return {
        "statusCode": 200 if freshness["status"] == "ok" else 202,
        "body": json.dumps({
            "status": freshness["status"],
            "stale_tables": freshness.get("stale_tables", []),
            "age_details": freshness.get("age_details", {}),
            "timestamp": datetime.now(timezone.utc).isoformat(),
        }),
    }
