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
    """

    # Check if running locally
    if os.getenv("USE_LOCAL_DB") == "true" or all(
        key in os.environ for key in ["DB_HOST", "DB_USER", "DB_PASSWORD", "DB_NAME"]
    ):
        logging.info("Using local database configuration from environment variables")
        return {
            "host": os.getenv("DB_HOST", "localhost"),
            "port": int(os.getenv("DB_PORT", 5432)),
            "user": os.getenv("DB_USER", "postgres"),
            "password": os.getenv("DB_PASSWORD", "postgres"),
            "dbname": os.getenv("DB_NAME", "stocks"),
        }

    # AWS Secrets Manager for production
    client = boto3.client("secretsmanager")
    resp = client.get_secret_value(SecretId=os.environ["DB_SECRET_ARN"])
    sec = json.loads(resp["SecretString"])
    return {
        "host": sec["host"],
        "port": int(sec.get("port", 5432)),
        "user": sec["username"],
        "password": sec["password"],
        "dbname": sec["dbname"],
    }


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
