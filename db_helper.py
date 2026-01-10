#!/usr/bin/env python3
"""
Shared database connection helper with robust AWS Secrets Manager fallback
Used by all loaders to ensure consistent error handling and fallback logic
"""

import os
import json
import logging
import psycopg2
import boto3

logger = logging.getLogger(__name__)

def get_db_connection(script_name="loader"):
    """
    Get database connection with multiple fallback strategies:
    1. AWS Secrets Manager (if DB_SECRET_ARN set and IAM permissions OK)
    2. Local socket connection (peer authentication)
    3. Environment variables (DB_HOST, DB_PORT, DB_USER, DB_PASSWORD, DB_NAME)
    """
    db_secret_arn = os.environ.get("DB_SECRET_ARN")
    db_host = os.environ.get("DB_HOST", "localhost")
    db_port = os.environ.get("DB_PORT", "5432")
    db_user = os.environ.get("DB_USER", "stocks")
    db_password = os.environ.get("DB_PASSWORD", "bed0elAn")
    db_name = os.environ.get("DB_NAME", "stocks")
    
    # Strategy 1: Try AWS Secrets Manager if ARN is provided
    if db_secret_arn:
        try:
            logger.info(f"[{script_name}] Attempting AWS Secrets Manager connection...")
            secret_str = boto3.client("secretsmanager", region_name="us-east-1") \
                             .get_secret_value(SecretId=db_secret_arn)["SecretString"]
            sec = json.loads(secret_str)
            conn = psycopg2.connect(
                host=sec["host"],
                port=int(sec.get("port", 5432)),
                user=sec["username"],
                password=sec["password"],
                database=sec["dbname"]
            )
            logger.info(f"[{script_name}] ✅ Connected via AWS Secrets Manager")
            return conn
        except Exception as e:
            logger.warning(f"[{script_name}] AWS Secrets Manager failed ({type(e).__name__}): {e}")
            logger.warning(f"[{script_name}] Falling back to local connection methods...")
    
    # Strategy 2: Try local socket connection (peer authentication)
    try:
        logger.info(f"[{script_name}] Attempting local socket connection...")
        conn = psycopg2.connect(dbname=db_name, user=db_user)
        logger.info(f"[{script_name}] ✅ Connected via local socket")
        return conn
    except Exception as e:
        logger.debug(f"[{script_name}] Local socket failed: {e}")
    
    # Strategy 3: Use environment variables
    try:
        logger.info(f"[{script_name}] Attempting environment variable connection...")
        conn = psycopg2.connect(
            host=db_host,
            port=int(db_port),
            user=db_user,
            password=db_password,
            database=db_name
        )
        logger.info(f"[{script_name}] ✅ Connected via environment variables")
        return conn
    except psycopg2.Error as e:
        logger.error(f"[{script_name}] ❌ All connection strategies failed: {e}")
        return None
