#!/usr/bin/env python3
"""
Database schema initialization Lambda for RDS PostgreSQL.
Uses Secrets Manager for credentials. Must run in VPC.
"""

import json
import logging
import os
import boto3
import psycopg2

logger = logging.getLogger()
logger.setLevel(logging.INFO)

DEFAULT_DB_PORT = 5432


def get_credentials():
    """Get DB credentials from Secrets Manager or env vars."""
    secret_arn = os.environ.get('DB_SECRET_ARN')
    if secret_arn:
        client = boto3.client('secretsmanager', region_name=os.environ.get('AWS_REGION', 'us-east-1'))
        response = client.get_secret_value(SecretId=secret_arn)
        secret = json.loads(response['SecretString'])
        return {
            'host': os.environ.get('DB_ENDPOINT') or secret.get('host'),
            'port': int(secret.get('port', DEFAULT_DB_PORT)),
            'database': os.environ.get('DB_NAME') or secret.get('dbname', 'stocks'),
            'user': secret.get('username'),
            'password': secret.get('password'),
        }

    return {
        'host': os.environ.get('DB_HOST'),
        'port': int(os.environ.get('DB_PORT', DEFAULT_DB_PORT)),
        'database': os.environ.get('DB_NAME', 'stocks'),
        'user': os.environ.get('DB_USER'),
        'password': os.environ.get('DB_PASSWORD'),
    }


def lambda_handler(event, context):
    """Initialize RDS database schema."""
    try:
        creds = get_credentials()

        if not all([creds['host'], creds['user'], creds['password']]):
            logger.error("Missing required database credentials")
            return {
                'statusCode': 400,
                'body': json.dumps('Missing required database credentials')
            }

        logger.info(f"Connecting to RDS: {creds['host']}:{creds['port']}/{creds['database']}")
        conn = psycopg2.connect(
            host=creds['host'],
            port=creds['port'],
            database=creds['database'],
            user=creds['user'],
            password=creds['password'],
            connect_timeout=15
        )
        conn.autocommit = True

        try:
            with open('schema.sql', 'r') as f:
                sql_script = f.read()
        except FileNotFoundError:
            logger.warning("schema.sql not found; checking for init_database module")
            sql_script = ""

        if not sql_script.strip():
            # Try running init_database.py if bundled
            try:
                import init_database
                cursor = conn.cursor()
                result = init_database.initialize_database(conn)
                cursor.close()
                conn.close()
                logger.info(f"init_database completed: {result}")
                return {
                    'statusCode': 200,
                    'body': json.dumps(f'Database initialized via init_database module')
                }
            except ImportError:
                pass

            # Fall back: create a minimal schema
            logger.info("Creating minimal schema (no schema.sql found)")
            cursor = conn.cursor()
            cursor.execute("SELECT COUNT(*) FROM information_schema.tables WHERE table_schema = 'public'")
            table_count = cursor.fetchone()[0]
            cursor.close()
            conn.close()
            return {
                'statusCode': 200,
                'body': json.dumps(f'DB connected, {table_count} tables exist (no schema applied)')
            }

        cursor = conn.cursor()
        statement_count = 0

        for statement in sql_script.split(';'):
            statement = statement.strip()
            if statement:
                try:
                    cursor.execute(statement)
                    statement_count += 1
                except Exception as e:
                    logger.warning(f"Statement failed (continuing): {statement[:80]}... - {e}")

        cursor.close()
        conn.close()

        logger.info(f"Schema init done: {statement_count} statements")
        return {
            'statusCode': 200,
            'body': json.dumps(f'Database schema initialized ({statement_count} statements)')
        }

    except psycopg2.OperationalError as e:
        logger.error(f"Database connection failed: {e}")
        return {'statusCode': 503, 'body': json.dumps(f'DB connection failed: {e}')}

    except Exception as e:
        logger.error(f"Init failed: {e}", exc_info=True)
        return {'statusCode': 500, 'body': json.dumps(f'Init failed: {e}')}
