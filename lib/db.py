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
    """
    Fetch database credentials from local env or AWS Secrets Manager

    Priority:
    1. Local environment variables (for development)
    2. AWS Secrets Manager (for production)

    Returns:
        dict: Database connection config {host, port, user, password, dbname}

    Raises:
        KeyError: If neither local env vars nor AWS Secrets Manager credentials are available
    """

    # Check if running locally
    if os.getenv("USE_LOCAL_DB") == "true":
        logging.info("USE_LOCAL_DB=true, using local database configuration from environment variables")
        db_host = os.getenv("DB_HOST", "").strip()
        # Fix for stale endpoint - if env var has old endpoint, use correct one
        if 'c2gujitq3h1b' in db_host:
            db_host = 'stocks.cojggi2mkthi.us-east-1.rds.amazonaws.com'
        db_user = os.getenv("DB_USER")
        db_password = os.getenv("DB_PASSWORD")
        db_name = os.getenv("DB_NAME")

        if not all([db_host, db_user, db_password, db_name]):
            raise KeyError("USE_LOCAL_DB=true but missing DB_HOST, DB_USER, DB_PASSWORD, or DB_NAME environment variables")

        return {
            "host": db_host,
            "port": int(os.getenv("DB_PORT", 5432)),
            "user": db_user,
            "password": db_password,
            "dbname": db_name,
        }

    # Check if all local env vars are provided
    if all(key in os.environ for key in ["DB_HOST", "DB_USER", "DB_PASSWORD", "DB_NAME"]):
        logging.info("Using local database configuration from environment variables")
        db_host = os.getenv("DB_HOST", "").strip()
        # Fix for stale endpoint - if env var has old endpoint, use correct one
        if 'c2gujitq3h1b' in db_host:
            db_host = 'stocks.cojggi2mkthi.us-east-1.rds.amazonaws.com'
        return {
            "host": db_host,
            "port": int(os.getenv("DB_PORT", 5432)),
            "user": os.getenv("DB_USER"),
            "password": os.getenv("DB_PASSWORD"),
            "dbname": os.getenv("DB_NAME"),
        }

    # AWS Secrets Manager for production
    if "DB_SECRET_ARN" not in os.environ:
        raise KeyError(
            "Database credentials not found. Set one of:\n"
            "  1. USE_LOCAL_DB=true + DB_HOST, DB_USER, DB_PASSWORD, DB_NAME (for local testing)\n"
            "  2. DB_HOST, DB_USER, DB_PASSWORD, DB_NAME (direct connection)\n"
            "  3. DB_SECRET_ARN (for AWS Secrets Manager)\n"
            "Current environment: " + str({k: v for k, v in os.environ.items() if 'DB' in k or 'AWS' in k})
        )

    try:
        client = boto3.client("secretsmanager", region_name=os.getenv("AWS_REGION", "us-east-1"))
        resp = client.get_secret_value(SecretId=os.environ["DB_SECRET_ARN"])
        sec = json.loads(resp["SecretString"])
        logging.info(f"Using AWS Secrets Manager for database credentials (ARN: {os.environ['DB_SECRET_ARN'][:50]}...)")
        return {
            "host": sec["host"],
            "port": int(sec.get("port", 5432)),
            "user": sec["username"],
            "password": sec["password"],
            "dbname": sec["dbname"],
        }
    except Exception as e:
        raise KeyError(f"Failed to fetch database credentials from AWS Secrets Manager: {e}")


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
