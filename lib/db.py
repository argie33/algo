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
    """Get database configuration from AWS Secrets Manager or local environment.

    Tries AWS first, then falls back to local environment variables for development.

    Returns:
        dict: Database connection config {host, port, user, password, dbname}

    Raises:
        EnvironmentError: If no configuration source is available
    """
    aws_region = os.environ.get("AWS_REGION")
    db_secret_arn = os.environ.get("DB_SECRET_ARN")

    # Try AWS first if configured
    if aws_region and db_secret_arn:
        try:
            secret_str = boto3.client("secretsmanager", region_name=aws_region).get_secret_value(
                SecretId=db_secret_arn
            )["SecretString"]
            sec = json.loads(secret_str)
            logging.info(f"✅ Loaded database credentials from AWS Secrets Manager: {db_secret_arn}")
            return {
                "host": sec["host"],
                "port": int(sec.get("port", 5432)),
                "user": sec["username"],
                "password": sec["password"],
                "dbname": sec["dbname"]
            }
        except Exception as e:
            logging.error(f"AWS Secrets Manager failed: {e}")

    # Fallback to local environment variables for development
    db_host = os.environ.get("DB_HOST") or os.environ.get("PGHOST") or "localhost"
    db_port = os.environ.get("DB_PORT") or os.environ.get("PGPORT") or "5432"
    db_user = os.environ.get("DB_USER") or os.environ.get("PGUSER") or "stocks"
    db_password = os.environ.get("DB_PASSWORD") or os.environ.get("PGPASSWORD") or "stocks"
    db_name = os.environ.get("DB_NAME") or os.environ.get("PGDATABASE") or "stocks"

    if db_host and db_user and db_name:
        logging.info(f"✅ Using local database: {db_user}@{db_host}/{db_name}")
        return {
            "host": db_host,
            "port": int(db_port),
            "user": db_user,
            "password": db_password,
            "dbname": db_name
        }

    raise EnvironmentError(
        "No database configuration found. Set AWS_REGION + DB_SECRET_ARN for AWS, "
        "or DB_HOST, DB_USER, DB_PASSWORD, DB_NAME for local development."
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
