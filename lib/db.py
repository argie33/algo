"""
Database utilities - shared connection and credential management
Eliminates duplication of get_db_config() across all loaders
"""

import os
import json
import logging
import boto3
import psycopg2
from typing import Dict, Optional


def get_db_config() -> Dict[str, any]:
    """Get database configuration from AWS Secrets Manager.

    REQUIRES AWS_REGION and DB_SECRET_ARN environment variables to be set.
    No fallbacks - fails loudly if AWS is not configured.

    Returns:
        dict: Database connection config {host, port, user, password, dbname}

    Raises:
        EnvironmentError: If AWS_REGION or DB_SECRET_ARN not set, or if Secrets Manager fails
    """
    aws_region = os.environ.get("AWS_REGION")
    db_secret_arn = os.environ.get("DB_SECRET_ARN")

    if not aws_region:
        raise EnvironmentError(
            "FATAL: AWS_REGION not set. Real data requires AWS configuration."
        )
    if not db_secret_arn:
        raise EnvironmentError(
            "FATAL: DB_SECRET_ARN not set. Real data requires AWS Secrets Manager configuration."
        )

    try:
        secret_str = boto3.client("secretsmanager", region_name=aws_region).get_secret_value(
            SecretId=db_secret_arn
        )["SecretString"]
        sec = json.loads(secret_str)
        logging.info(f"Loaded real database credentials from AWS Secrets Manager: {db_secret_arn}")
        return {
            "host": sec["host"],
            "port": int(sec.get("port", 5432)),
            "user": sec["username"],
            "password": sec["password"],
            "dbname": sec["dbname"]
        }
    except Exception as e:
        raise EnvironmentError(
            f"FATAL: Cannot load database credentials from AWS Secrets Manager ({db_secret_arn}). "
            f"Error: {e.__class__.__name__}: {str(e)[:200]}\n"
            f"Ensure AWS credentials are configured and Secrets Manager is accessible.\n"
            f"Real data requires proper AWS setup - no fallbacks allowed."
        )


def get_connection(cfg: Optional[Dict] = None):
    """
    Get a database connection

    Args:
        cfg: Database config dict. If None, uses get_db_config()

    Returns:
        psycopg2 connection object
    """
    if cfg is None:
        cfg = get_db_config()

    conn = psycopg2.connect(
        host=cfg["host"],
        port=cfg["port"],
        user=cfg["user"],
        password=cfg["password"],
        dbname=cfg["dbname"],
    )
    conn.autocommit = False
    return conn


def update_last_updated(cur, conn, script_name: str):
    """
    Update last_updated tracking table

    Args:
        cur: Database cursor
        conn: Database connection
        script_name: Name of the script that ran
    """
    cur.execute("""
        CREATE TABLE IF NOT EXISTS last_updated (
            script_name VARCHAR(255) PRIMARY KEY,
            last_run    TIMESTAMP
        );
    """)
    cur.execute("""
        INSERT INTO last_updated (script_name, last_run)
        VALUES (%s, NOW())
        ON CONFLICT (script_name) DO UPDATE
        SET last_run = EXCLUDED.last_run;
    """, (script_name,))
    conn.commit()
    logging.info(f"✅ Updated last_updated table for {script_name}")
