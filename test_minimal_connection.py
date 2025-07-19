#!/usr/bin/env python3
"""
Minimal database connection test to isolate the issue
"""
import psycopg2
import json
import os
import boto3

def get_db_config():
    secret_str = boto3.client("secretsmanager") \
                     .get_secret_value(SecretId=os.environ["DB_SECRET_ARN"])["SecretString"]
    sec = json.loads(secret_str)
    return {
        "host": sec["host"],
        "port": int(sec.get("port", 5432)),
        "user": sec["username"],
        "password": sec["password"],
        "dbname": sec["dbname"]
    }

if __name__ == "__main__":
    cfg = get_db_config()
    
    print(f"Testing connection to {cfg['host']}:{cfg['port']}")
    
    # Test 1: Minimal connection without SSL
    try:
        print("Test 1: Attempting connection with sslmode=disable")
        conn = psycopg2.connect(
            host=cfg["host"],
            port=cfg["port"],
            user=cfg["user"],
            password=cfg["password"],
            dbname=cfg["dbname"],
            sslmode='disable',
            connect_timeout=10
        )
        print("✅ SUCCESS: Non-SSL connection works")
        conn.close()
    except Exception as e:
        print(f"❌ FAILED: Non-SSL connection: {e}")
    
    # Test 2: SSL connection with longer timeout
    try:
        print("Test 2: Attempting SSL connection with 60s timeout")
        conn = psycopg2.connect(
            host=cfg["host"],
            port=cfg["port"],
            user=cfg["user"],
            password=cfg["password"],
            dbname=cfg["dbname"],
            sslmode='require',
            connect_timeout=60
        )
        print("✅ SUCCESS: SSL connection works with longer timeout")
        conn.close()
    except Exception as e:
        print(f"❌ FAILED: SSL connection: {e}")
    
    # Test 3: SSL with prefer mode
    try:
        print("Test 3: Attempting SSL prefer mode")
        conn = psycopg2.connect(
            host=cfg["host"],
            port=cfg["port"],
            user=cfg["user"],
            password=cfg["password"],
            dbname=cfg["dbname"],
            sslmode='prefer',
            connect_timeout=30
        )
        print("✅ SUCCESS: SSL prefer mode works")
        conn.close()
    except Exception as e:
        print(f"❌ FAILED: SSL prefer mode: {e}")