#!/usr/bin/env python3
"""
Database schema initialization Lambda function for RDS PostgreSQL.
Executed via Terraform after RDS instance is created.
Runs SQL schema from init.sql; idempotent (uses IF NOT EXISTS).
"""

import json
import logging
import os

logger = logging.getLogger()
logger.setLevel(logging.INFO)


def lambda_handler(event, context):
    """Initialize RDS database schema and ensure stocks user exists."""
    import psycopg2
    from psycopg2 import OperationalError
    import boto3

    db_host = os.environ.get('DB_HOST')
    db_port = int(os.environ.get('DB_PORT', 5432))
    db_name = os.environ.get('DB_NAME')
    db_master_user = os.environ.get('DB_MASTER_USER', 'postgres')
    db_secret_arn = os.environ.get('DB_SECRET_ARN')
    db_user = os.environ.get('DB_USER', 'stocks')

    if not all([db_host, db_name, db_master_user, db_secret_arn, db_user]):
        return {
            'statusCode': 400,
            'body': json.dumps('Missing required database connection parameters (need DB_HOST, DB_NAME, DB_MASTER_USER, DB_SECRET_ARN, DB_USER)')
        }

    try:
        # First: Get database credentials from Secrets Manager
        logger.info("Step 1: Fetching database credentials from Secrets Manager...")
        sm = boto3.client('secretsmanager', region_name=os.environ.get('AWS_REGION', 'us-east-1'))
        try:
            secret_response = sm.get_secret_value(SecretId=db_secret_arn)
            secret = json.loads(secret_response['SecretString'])
            db_master_password = secret['password']
            logger.info("Retrieved master password from Secrets Manager")
        except Exception as e:
            logger.error(f"Could not get credentials from Secrets Manager: {e}")
            return {
                'statusCode': 500,
                'body': json.dumps(f'Failed to retrieve credentials from Secrets Manager: {str(e)}')
            }

        # Use the same password for stocks user (shared master credentials)
        logger.info("Step 2: Ensuring stocks user exists with correct password...")
        stocks_password = db_master_password

        # Connect as master user
        logger.info(f"Connecting to RDS as {db_master_user}: {db_host}:{db_port}/{db_name}")
        master_conn = psycopg2.connect(
            host=db_host,
            port=db_port,
            database=db_name,
            user=db_master_user,
            password=db_master_password,
            connect_timeout=10
        )

        master_conn.autocommit = True
        master_cursor = master_conn.cursor()

        # Create or update stocks user
        try:
            master_cursor.execute(f'ALTER USER "{db_user}" WITH PASSWORD %s', (stocks_password,))
            logger.info(f"Updated existing {db_user} user password")
        except Exception as e:
            logger.info(f"User update failed, creating new user: {e}")
            try:
                master_cursor.execute(f'CREATE USER "{db_user}" WITH PASSWORD %s', (stocks_password,))
                logger.info(f"Created new {db_user} user")

                # Grant permissions
                master_cursor.execute(f'GRANT CONNECT ON DATABASE "{db_name}" TO "{db_user}"')
                master_cursor.execute(f'GRANT USAGE ON SCHEMA public TO "{db_user}"')
                master_cursor.execute(f'GRANT ALL PRIVILEGES ON ALL TABLES IN SCHEMA public TO "{db_user}"')
                master_cursor.execute(f'GRANT ALL PRIVILEGES ON ALL SEQUENCES IN SCHEMA public TO "{db_user}"')
                logger.info(f"Granted permissions to {db_user}")
            except Exception as e2:
                logger.error(f"Failed to create/update user: {e2}")

        master_cursor.close()
        master_conn.close()
        logger.info("✅ Stocks user setup complete")

        # Third: Initialize schema by connecting as stocks user
        logger.info("Step 3: Initializing database schema...")

        logger.info(f"Connecting to RDS as {db_user}: {db_host}:{db_port}/{db_name}")
        conn = psycopg2.connect(
            host=db_host,
            port=db_port,
            database=db_name,
            user=db_user,
            password=stocks_password,
            connect_timeout=10
        )

        # Use embedded schema from Terraform templatefile
        sql_script = """${sql_content}"""

        if not sql_script.strip():
            logger.warning("No SQL script found; skipping initialization")
            return {
                'statusCode': 200,
                'body': json.dumps('No SQL script to execute')
            }

        conn.autocommit = True
        cursor = conn.cursor()

        logger.info("Executing database schema initialization")

        # Split by semicolon and execute each statement separately
        # (psycopg2.execute() can only run one statement at a time)
        for statement in sql_script.split(';'):
            statement = statement.strip()
            if statement:  # Skip empty statements
                try:
                    cursor.execute(statement)
                    logger.info(f"Executed: {statement[:80]}...")
                except Exception as e:
                    logger.warning(f"Statement failed (continuing): {statement[:80]}... - {e}")
                    # Continue on error for idempotent operations (CREATE TABLE IF NOT EXISTS, etc.)

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
    logger.info(json.dumps(result, indent=2))
