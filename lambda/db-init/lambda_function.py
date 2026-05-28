#!/usr/bin/env python3
"""
Database schema initialization Lambda for RDS PostgreSQL.
Uses Secrets Manager for credentials. Must run in VPC.
Deployed: May 24, 2026 21:56 - Triggering auto database initialization
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
        try:
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
        except (json.JSONDecodeError, ValueError, KeyError, TypeError) as e:
            logger.error(f'Failed to parse secrets: {e}')
            # Fall through to env vars

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
    """Initialize RDS database schema and ensure stocks user exists."""
    try:
        creds = get_credentials()

        if not all([creds['host'], creds['user'], creds['password']]):
            logger.error("Missing required database credentials")
            return {
                'statusCode': 400,
                'body': json.dumps('Missing required database credentials')
            }

        # Step 1: Ensure stocks user exists (as master user)
        logger.info("Step 1: Ensuring stocks user exists with correct password...")

        master_user = os.environ.get('DB_MASTER_USER', 'postgres')
        master_password = os.environ.get('DB_MASTER_PASSWORD')

        if master_user and master_password:
            try:
                logger.info(f"Connecting as master user ({master_user}) to create/update stocks user...")
                master_conn = psycopg2.connect(
                    host=creds['host'],
                    port=creds['port'],
                    database=creds['database'],
                    user=master_user,
                    password=master_password,
                    connect_timeout=15
                )
                master_conn.autocommit = True
                master_cursor = master_conn.cursor()

                # Create or update stocks user with password from Secrets Manager
                try:
                    master_cursor.execute(f'ALTER USER "{creds["user"]}" WITH PASSWORD %s', (creds['password'],))
                    logger.info(f"Updated existing {creds['user']} user password")
                except Exception as e:
                    logger.info(f"User update failed, creating new user: {e}")
                    try:
                        master_cursor.execute(f'CREATE USER "{creds["user"]}" WITH PASSWORD %s', (creds['password'],))
                        logger.info(f"Created new {creds['user']} user")
                        # Grant permissions
                        master_cursor.execute(f'GRANT CONNECT ON DATABASE "{creds["database"]}" TO "{creds["user"]}"')
                        master_cursor.execute(f'GRANT USAGE ON SCHEMA public TO "{creds["user"]}"')
                        master_cursor.execute(f'GRANT ALL PRIVILEGES ON ALL TABLES IN SCHEMA public TO "{creds["user"]}"')
                        master_cursor.execute(f'GRANT ALL PRIVILEGES ON ALL SEQUENCES IN SCHEMA public TO "{creds["user"]}"')
                        logger.info(f"Granted permissions to {creds['user']}")
                    except Exception as e2:
                        logger.error(f"Failed to create/update user: {e2}")

                master_cursor.close()
                master_conn.close()
                logger.info("✅ Stocks user setup complete")
            except Exception as e:
                logger.warning(f"Could not connect as master user to create stocks user: {e}")
        else:
            logger.info("Master user credentials not provided, skipping user creation")

        # Step 2: Initialize schema as stocks user
        logger.info(f"Step 2: Initializing database schema — Connecting to RDS: {creds['host']}:{creds['port']}/{creds['database']}")
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

        # Add historical rank columns to industry_ranking (idempotent)
        try:
            cursor.execute("ALTER TABLE industry_ranking ADD COLUMN IF NOT EXISTS rank_1w_ago INTEGER")
            cursor.execute("ALTER TABLE industry_ranking ADD COLUMN IF NOT EXISTS rank_4w_ago INTEGER")
            cursor.execute("ALTER TABLE industry_ranking ADD COLUMN IF NOT EXISTS rank_12w_ago INTEGER")
            logger.info("Added historical rank columns to industry_ranking")
        except Exception as e:
            logger.info(f"industry_ranking history columns may already exist: {e}")

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
