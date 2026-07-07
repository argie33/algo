#!/usr/bin/env python3
"""
Lambda function to sync fresh data from local PostgreSQL to AWS RDS.

This is a workaround until EventBridge Scheduler IAM permissions are granted.

Trigger via:
  aws lambda invoke \
    --function-name algo-sync-data-to-rds \
    --region us-east-1 \
    --payload '{}' \
    /tmp/response.json
"""

import json
import logging
import os
import psycopg2
import psycopg2.extras

logger = logging.getLogger()
logger.setLevel("INFO")

# Tables to sync (critical tables with fresh data)
CRITICAL_TABLES = [
    "stock_scores",
    "algo_trades",
    "algo_portfolio_snapshots",
    "algo_orchestrator_runs",
    "technical_data_daily",
    "price_daily",
    "buy_sell_daily",
]

OPTIONAL_TABLES = [
    "growth_metrics",
    "quality_metrics",
    "stability_metrics",
    "positioning_metrics",
    "value_metrics",
    "momentum_metrics",
    "market_exposure_daily",
]


def get_local_connection():
    """Get connection to local development database."""
    try:
        conn = psycopg2.connect(
            host="127.0.0.1",
            port=5432,
            user="stocks",
            password="stocks",
            database="stocks",
            connect_timeout=5,
        )
        return conn
    except Exception as e:
        logger.error(f"Failed to connect to local DB: {e}")
        raise


def get_aws_connection():
    """Get connection to AWS RDS using Secrets Manager."""
    import boto3
    import json as json_mod

    try:
        sm = boto3.client("secretsmanager", region_name=os.getenv("AWS_REGION", "us-east-1"))
        secret = sm.get_secret_value(SecretId="algo/database")
        creds = json_mod.loads(secret["SecretString"])

        conn = psycopg2.connect(
            host=creds["host"],
            port=creds["port"],
            user=creds["username"],
            password=creds["password"],
            database=creds["dbname"],
            connect_timeout=10,
        )
        return conn
    except Exception as e:
        logger.error(f"Failed to connect to AWS RDS: {e}")
        raise


def sync_table(src_conn, tgt_conn, table):
    """Sync a single table."""
    try:
        src_cur = src_conn.cursor(cursor_factory=psycopg2.extras.DictCursor)
        tgt_cur = tgt_conn.cursor()

        # Get row count
        src_cur.execute(f"SELECT COUNT(*) FROM {table}")
        src_count = src_cur.fetchone()[0]

        if src_count == 0:
            logger.warning(f"{table}: source is empty, skipping")
            return False

        logger.info(f"{table}: syncing {src_count} rows")

        # Get all data
        src_cur.execute(f"SELECT * FROM {table}")
        rows = src_cur.fetchall()
        col_names = [desc[0] for desc in src_cur.description]

        # Truncate target
        try:
            tgt_cur.execute(f"TRUNCATE TABLE {table}")
        except Exception as e:
            logger.warning(f"Could not truncate {table}: {e}")

        # Copy data
        for i, row in enumerate(rows):
            placeholders = ",".join(["%s"] * len(col_names))
            insert_sql = f"INSERT INTO {table} ({','.join(col_names)}) VALUES ({placeholders})"
            try:
                tgt_cur.execute(insert_sql, tuple(row.values() if isinstance(row, dict) else row))
            except Exception as e:
                logger.error(f"Failed to insert row {i} into {table}: {e}")
                tgt_conn.rollback()
                return False

        tgt_conn.commit()
        logger.info(f"{table}: synced successfully")
        return True

    except Exception as e:
        logger.error(f"Failed to sync {table}: {e}")
        return False


def lambda_handler(event, context):
    """Lambda entry point."""
    logger.info("Starting data sync from local to AWS RDS")

    try:
        src_conn = get_local_connection()
        tgt_conn = get_aws_connection()

        tables = CRITICAL_TABLES + OPTIONAL_TABLES
        successful = 0
        failed = 0

        for table in tables:
            try:
                if sync_table(src_conn, tgt_conn, table):
                    successful += 1
                else:
                    failed += 1
            except Exception as e:
                logger.error(f"{table}: {e}")
                failed += 1

        src_conn.close()
        tgt_conn.close()

        result = {"successful": successful, "failed": failed, "total": len(tables)}
        logger.info(f"Sync complete: {successful}/{len(tables)} successful")

        return {"statusCode": 200 if failed == 0 else 206, "body": json.dumps(result)}

    except Exception as e:
        logger.error(f"Sync failed: {e}")
        return {"statusCode": 500, "body": json.dumps({"error": str(e)})}
