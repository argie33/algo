#!/usr/bin/env python3
"""
Initialize PostgreSQL Database Schema

This script reads the Terraform SQL schema and initializes the local
PostgreSQL database with all required tables for local development.

Usage:
    python3 init_database.py

Environment Variables:
    DB_HOST (default: localhost)
    DB_PORT (default: 5432)
    DB_NAME (default: stocks)
    DB_USER (default: stocks)
    DB_PASSWORD (default: stocks)
"""

import os
import sys
import logging
import psycopg2
from pathlib import Path

logging.basicConfig(
    level=logging.INFO,
    format='%(asctime)s - %(levelname)s - %(message)s'
)
logger = logging.getLogger(__name__)

def get_schema_sql():
    """Read the database schema from Terraform init.sql file."""
    schema_path = Path(__file__).parent / 'terraform' / 'modules' / 'database' / 'init.sql'

    if not schema_path.exists():
        logger.error(f"Schema file not found: {schema_path}")
        sys.exit(1)

    with open(schema_path, 'r') as f:
        return f.read()

def split_sql_statements(sql):
    """Split SQL into statements, respecting dollar-quoted blocks."""
    statements = []
    current = []
    dollar_tag = None
    i = 0

    while i < len(sql):
        ch = sql[i]

        # Detect start/end of dollar-quoted string
        if ch == '$' and dollar_tag is None:
            # Look ahead for dollar-quoted string start
            j = i + 1
            tag = ''
            while j < len(sql) and sql[j] != '$':
                tag += sql[j]
                j += 1
            if j < len(sql):  # Found closing $
                dollar_tag = tag
                current.append('$' + tag + '$')
                i = j + 1
                continue

        if dollar_tag is not None:
            # Look for end of dollar-quoted string
            end_tag = '$' + dollar_tag + '$'
            if sql[i:i + len(end_tag)] == end_tag:
                current.append(end_tag)
                i += len(end_tag)
                dollar_tag = None
                continue

        # Outside dollar quotes - check for statement end
        if ch == ';' and dollar_tag is None:
            stmt = ''.join(current).strip()
            if stmt:
                statements.append(stmt)
            current = []
            i += 1
            continue

        current.append(ch)
        i += 1

    # Flush remaining
    stmt = ''.join(current).strip()
    if stmt:
        statements.append(stmt)

    return statements

def init_database():
    """Initialize the database schema."""
    try:
        # Get connection parameters from environment
        db_host = os.getenv('DB_HOST', 'localhost')
        db_port = int(os.getenv('DB_PORT', 5432))
        db_name = os.getenv('DB_NAME', 'stocks')
        db_user = os.getenv('DB_USER', 'stocks')
        db_password = os.getenv('DB_PASSWORD', 'stocks')

        logger.info(f"Connecting to database: {db_user}@{db_host}:{db_port}/{db_name}")

        # Connect to database
        conn = psycopg2.connect(
            host=db_host,
            port=db_port,
            database=db_name,
            user=db_user,
            password=db_password,
            connect_timeout=10
        )

        cur = conn.cursor()

        # Read schema
        logger.info("Reading database schema...")
        schema_sql = get_schema_sql()

        # Split into statements
        statements = split_sql_statements(schema_sql)

        logger.info(f"Executing {len(statements)} SQL statements...")

        # Execute each statement
        success_count = 0
        skip_count = 0

        for i, statement in enumerate(statements, 1):
            try:
                cur.execute(statement)
                success_count += 1

                # Log progress every 10 statements
                if i % 10 == 0:
                    logger.info(f"  Executed {i}/{len(statements)} statements...")

            except psycopg2.ProgrammingError as e:
                # Some statements might fail if tables already exist, that's OK
                if 'already exists' in str(e):
                    skip_count += 1
                else:
                    logger.error(f"Error executing statement {i}: {e}")
                    logger.error(f"Statement: {statement[:100]}...")

        # Commit
        conn.commit()
        cur.close()
        conn.close()

        logger.info("=" * 80)
        logger.info(f"✓ Database schema initialized successfully!")
        logger.info(f"  - {success_count} statements executed")
        logger.info(f"  - {skip_count} statements skipped (tables already exist)")
        logger.info("=" * 80)
        logger.info("")
        logger.info("Next steps:")
        logger.info("  1. Start the local API server: python3 local_api_server.py")
        logger.info("  2. Load data: python3 run-all-loaders.py")
        logger.info("  3. Start frontend: cd webapp/frontend && npm run dev")
        logger.info("")

        return True

    except psycopg2.OperationalError as e:
        logger.error(f"Failed to connect to database: {e}")
        logger.error("")
        logger.error("Troubleshooting:")
        logger.error("  1. Make sure PostgreSQL is running")
        logger.error("  2. Check connection parameters:")
        logger.error(f"     Host: {db_host}")
        logger.error(f"     Port: {db_port}")
        logger.error(f"     Database: {db_name}")
        logger.error(f"     User: {db_user}")
        logger.error("  3. Verify database exists: createdb stocks")
        logger.error("  4. Verify user exists: createuser stocks")
        return False

    except Exception as e:
        logger.error(f"Error initializing database: {e}", exc_info=True)
        return False

if __name__ == '__main__':
    success = init_database()
    sys.exit(0 if success else 1)
