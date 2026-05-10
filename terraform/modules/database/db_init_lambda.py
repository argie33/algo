#!/usr/bin/env python3
"""
Database schema initialization Lambda function for RDS PostgreSQL.
Executed via Terraform after RDS instance is created.
Runs SQL schema from init.sql; idempotent (uses IF NOT EXISTS).
"""

import json
import logging
import os
import psycopg2
from psycopg2 import OperationalError

logger = logging.getLogger()
logger.setLevel(logging.INFO)


def lambda_handler(event, context):
    """Initialize RDS database schema."""

    # Get database connection parameters
    db_host = os.environ.get('DB_HOST')
    db_port = int(os.environ.get('DB_PORT', 5432))
    db_name = os.environ.get('DB_NAME')
    db_user = os.environ.get('DB_USER')
    db_password = os.environ.get('DB_PASSWORD')

    if not all([db_host, db_name, db_user, db_password]):
        return {
            'statusCode': 400,
            'body': json.dumps('Missing required database connection parameters')
        }

    try:
        # Connect to RDS instance
        logger.info(f"Connecting to RDS: {db_host}:{db_port}/{db_name}")
        conn = psycopg2.connect(
            host=db_host,
            port=db_port,
            database=db_name,
            user=db_user,
            password=db_password,
            connect_timeout=10
        )

        # Read and execute schema SQL
        logger.info("Reading schema.sql from Lambda package")
        try:
            with open('schema.sql', 'r') as f:
                sql_script = f.read()
        except FileNotFoundError:
            # Fallback: embedded schema (init.sql content via templatefile)
            sql_script = """
${sql_content}
"""

        if not sql_script.strip():
            logger.warning("No SQL script found; skipping initialization")
            return {
                'statusCode': 200,
                'body': json.dumps('No SQL script to execute')
            }

        # Execute SQL with autocommit enabled
        conn.autocommit = True
        cursor = conn.cursor()

        logger.info("Executing database schema initialization")
        cursor.execute(sql_script)

        cursor.close()
        conn.close()

        logger.info("Database initialization completed successfully")
        return {
            'statusCode': 200,
            'body': json.dumps('Database schema initialized successfully')
        }

    except OperationalError as e:
        logger.error(f"Database connection failed: {str(e)}")
        return {
            'statusCode': 503,
            'body': json.dumps(f'Database connection failed: {str(e)}')
        }

    except Exception as e:
        logger.error(f"Database initialization failed: {str(e)}")
        return {
            'statusCode': 500,
            'body': json.dumps(f'Database initialization failed: {str(e)}')
        }


if __name__ == '__main__':
    # For local testing
    result = lambda_handler({}, None)
    print(json.dumps(result, indent=2))
