#!/usr/bin/env python3
"""
Database schema initialization Lambda for RDS PostgreSQL.
Uses Secrets Manager for credentials. Must run in VPC.
"""

import json
import logging
import os
import re
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
        raw_host = os.environ.get('DB_ENDPOINT') or secret.get('host', '')
        host = raw_host.split(':')[0] if ':' in raw_host else raw_host
        return {
            'host': host,
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


def split_sql_statements(sql):
    """Split SQL into statements, respecting dollar-quoted blocks (DO $$ ... $$).

    A naive split(';') breaks DO $$ BEGIN ... ; END $$; blocks.
    This parser tracks dollar-quoting depth so inner semicolons are preserved.
    """
    statements = []
    current = []
    dollar_tag = None
    i = 0
    while i < len(sql):
        ch = sql[i]

        # Detect start/end of dollar-quoted string
        if ch == '$' and dollar_tag is None:
            match = re.match(r'\$([^$]*)\$', sql[i:])
            if match:
                dollar_tag = match.group(0)
                current.append(dollar_tag)
                i += len(dollar_tag)
                continue

        if dollar_tag and sql[i:i + len(dollar_tag)] == dollar_tag:
            current.append(dollar_tag)
            i += len(dollar_tag)
            dollar_tag = None
            continue

        if ch == ';' and dollar_tag is None:
            stmt = ''.join(current).strip()
            if stmt:
                statements.append(stmt)
            current = []
            i += 1
            continue

        current.append(ch)
        i += 1

    # Flush any remaining
    stmt = ''.join(current).strip()
    if stmt:
        statements.append(stmt)

    return statements


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

        logger.info(f"DB Init Lambda v3 — Connecting to RDS: {creds['host']}:{creds['port']}/{creds['database']}")
        conn = psycopg2.connect(
            host=creds['host'],
            port=creds['port'],
            database=creds['database'],
            user=creds['user'],
            password=creds['password'],
            connect_timeout=15
        )
        conn.autocommit = True

        # Add MACD columns if needed (idempotent)
        cursor = conn.cursor()
        for table in ['buy_sell_daily', 'buy_sell_weekly', 'buy_sell_monthly']:
            try:
                cursor.execute(f"ALTER TABLE {table} ADD COLUMN IF NOT EXISTS macd DECIMAL(10, 2)")
                cursor.execute(f"ALTER TABLE {table} ADD COLUMN IF NOT EXISTS macd_signal DECIMAL(10, 2)")
                logger.info(f"Added MACD columns to {table}")
            except Exception as e:
                logger.info(f"MACD columns may already exist on {table}: {e}")

        sql_script = ''
        try:
            with open('schema.sql', 'r') as f:
                sql_script = f.read()
            logger.info("Using schema.sql")
        except FileNotFoundError:
            logger.warning("schema.sql not found")

        if not sql_script.strip():
            cursor.execute("SELECT COUNT(*) FROM information_schema.tables WHERE table_schema = 'public'")
            table_count = cursor.fetchone()[0]
            cursor.close()
            conn.close()
            return {
                'statusCode': 200,
                'body': json.dumps(f'DB connected, {table_count} tables exist (MACD columns added)')
            }

        statements = split_sql_statements(sql_script)
        ok_count = 0
        skip_count = 0

        for statement in statements:
            if not statement:
                continue
            try:
                cursor.execute(statement)
                ok_count += 1
            except Exception as e:
                err = str(e)
                if 'already exists' in err or 'does not exist' in err:
                    skip_count += 1
                else:
                    logger.warning(f"Statement failed: {statement[:100]}... -> {err[:120]}")
                    skip_count += 1

        cursor.close()
        conn.close()

        logger.info(f"Schema init done: {ok_count} ok, {skip_count} skipped/errored of {len(statements)} total")
        return {
            'statusCode': 200,
            'body': json.dumps(f'Database schema initialized ({ok_count}/{len(statements)} statements)')
        }

    except psycopg2.OperationalError as e:
        logger.error(f"Database connection failed: {e}")
        return {'statusCode': 503, 'body': json.dumps(f'DB connection failed: {e}')}

    except Exception as e:
        logger.error(f"Init failed: {e}", exc_info=True)
        return {'statusCode': 500, 'body': json.dumps(f'Init failed: {e}')}
