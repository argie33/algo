#!/usr/bin/env python3
"""
Minimal database connection helper.
Used by all loaders - provides get_db_connection() function.
"""

import os
import json
import psycopg2
import boto3

def get_db_connection(script_name="loader"):
    """
    Get database connection using environment variables or AWS Secrets Manager.
    Fallback chain:
    1. AWS Secrets Manager (if DB_SECRET_ARN set)
    2. Environment variables (DB_HOST, DB_USER, DB_PASSWORD, etc)
    """
    db_secret_arn = os.environ.get("DB_SECRET_ARN")

    # Try AWS Secrets Manager first
    if db_secret_arn:
        try:
            sm = boto3.client("secretsmanager", region_name="us-east-1")
            secret = json.loads(sm.get_secret_value(SecretId=db_secret_arn)["SecretString"])
            conn = psycopg2.connect(
                host=secret["host"],
                port=int(secret.get("port", 5432)),
                user=secret["username"],
                password=secret["password"],
                database=secret["dbname"]
            )
            return conn
        except Exception as e:
            pass  # Fall through to environment variables

    # Fall back to environment variables
    conn = psycopg2.connect(
        host=os.environ.get("DB_HOST", "localhost"),
        port=int(os.environ.get("DB_PORT", "5432")),
        user=os.environ.get("DB_USER", "stocks"),
        password=os.environ.get("DB_PASSWORD", "bed0elAn"),
        database=os.environ.get("DB_NAME", "stocks")
    )
    return conn
