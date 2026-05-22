#!/usr/bin/env python3
"""Apply pending schema migrations to the database."""

import sys
import os
from pathlib import Path
sys.path.insert(0, str(Path(__file__).parent.parent))

import psycopg2
from psycopg2.extras import execute_values
import boto3
import json

def get_db_credentials():
    """Retrieve database credentials from AWS Secrets Manager."""
    secret_name = 'algo-db-credentials-dev'
    region = os.environ.get('AWS_REGION', 'us-east-1')

    session = boto3.session.Session()
    client = session.client(service_name='secretsmanager', region_name=region)

    try:
        response = client.get_secret_value(SecretId=secret_name)
        secret = json.loads(response['SecretString'])
        return secret
    except Exception as e:
        print(f"ERROR: Failed to get credentials: {e}")
        return None

def apply_migrations():
    """Apply all pending schema migrations."""

    # Try to get credentials from environment or Secrets Manager
    db_host = os.environ.get('DB_HOST')
    db_name = os.environ.get('DB_NAME')
    db_user = os.environ.get('DB_USER')
    db_password = os.environ.get('DB_PASSWORD')
    db_port = os.environ.get('DB_PORT', '5432')

    if not all([db_host, db_name, db_user]):
        creds = get_db_credentials()
        if creds:
            db_host = os.environ.get('DB_HOST', 'algo-db.cojggi2mkthi.us-east-1.rds.amazonaws.com')
            db_name = 'stocks'
            db_user = creds.get('username')
            db_password = creds.get('password')
        else:
            print("ERROR: Database credentials not found")
            return 1

    try:
        conn = psycopg2.connect(
            host=db_host,
            database=db_name,
            user=db_user,
            password=db_password,
            port=db_port,
            connect_timeout=5
        )
        cursor = conn.cursor()

        # Migration 1: Add rs_percentile to stock_scores
        print("Applying migration: Add rs_percentile to stock_scores...")
        cursor.execute("""
            ALTER TABLE IF EXISTS stock_scores
            ADD COLUMN IF NOT EXISTS rs_percentile DECIMAL(8, 2);
        """)
        conn.commit()
        print("✓ rs_percentile column added")

        # Migration 2: Add updated_at to analyst_sentiment_analysis
        print("Applying migration: Add updated_at to analyst_sentiment_analysis...")
        cursor.execute("""
            ALTER TABLE IF EXISTS analyst_sentiment_analysis
            ADD COLUMN IF NOT EXISTS updated_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP;
        """)
        conn.commit()
        print("✓ updated_at column added")

        cursor.close()
        conn.close()
        return 0

    except Exception as e:
        print(f"ERROR: Migration failed: {e}")
        return 1

if __name__ == '__main__':
    sys.exit(apply_migrations())
