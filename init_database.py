#!/usr/bin/env python3
"""Initialize PostgreSQL Database Schema"""
import os, sys, logging, psycopg2
from pathlib import Path

logging.basicConfig(level=logging.INFO, format='%(asctime)s - %(levelname)s - %(message)s')
logger = logging.getLogger(__name__)

def init_database():
    try:
        db_host = os.getenv('DB_HOST', 'localhost')
        db_port = int(os.getenv('DB_PORT', 5432))
        db_name = os.getenv('DB_NAME', 'stocks')
        db_user = os.getenv('DB_USER', 'stocks')
        db_password = os.getenv('DB_PASSWORD', 'stocks')

        logger.info(f"Connecting to: {db_user}@{db_host}:{db_port}/{db_name}")

        conn = psycopg2.connect(
            host=db_host, port=db_port, database=db_name,
            user=db_user, password=db_password, connect_timeout=10
        )
        cur = conn.cursor()

        schema_path = Path(__file__).parent / 'terraform' / 'modules' / 'database' / 'init.sql'
        if not schema_path.exists():
            logger.error(f"✗ Schema file not found: {schema_path}")
            return False

        with open(schema_path, 'r') as f:
            schema_sql = f.read()

        statements = [s.strip() for s in schema_sql.split(';') if s.strip()]
        logger.info(f"Executing {len(statements)} SQL statements...")

        success_count = 0
        for i, stmt in enumerate(statements, 1):
            try:
                cur.execute(stmt)
                success_count += 1
                if i % 10 == 0:
                    logger.info(f"  Progress: {i}/{len(statements)}")
            except psycopg2.ProgrammingError:
                pass

        conn.commit()
        cur.close()
        conn.close()

        logger.info("=" * 80)
        logger.info(f"✓ Database schema initialized successfully!")
        logger.info(f"  - {success_count} statements executed")
        logger.info("=" * 80)
        return True

    except Exception as e:
        logger.error(f"✗ Error: {e}", exc_info=True)
        return False

if __name__ == '__main__':
    success = init_database()
    sys.exit(0 if success else 1)
