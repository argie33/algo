#!/usr/bin/env python3
"""Initialize database schema by executing terraform/modules/database/init.sql."""
import os
import sys
import logging
import psycopg2

logger = logging.getLogger(__name__)


def _get_conn():
    return psycopg2.connect(
        host=os.environ.get('DB_HOST', 'localhost'),
        port=int(os.environ.get('DB_PORT', 5432)),
        dbname=os.environ.get('DB_NAME', 'stocks'),
        user=os.environ.get('DB_USER', 'stocks'),
        password=os.environ.get('DB_PASSWORD', ''),
    )


def _find_sql():
    candidates = [
        os.path.join(os.path.dirname(__file__), '..', 'terraform', 'modules', 'database', 'init.sql'),
        os.path.join(os.path.dirname(__file__), '..', 'lambda', 'db-init', 'schema.sql'),
    ]
    for path in candidates:
        resolved = os.path.realpath(path)
        if os.path.exists(resolved):
            return resolved
    return None


def initialize_database(conn=None):
    """Run init.sql against the configured database. Returns row counts summary."""
    sql_path = _find_sql()
    if not sql_path:
        raise FileNotFoundError("init.sql not found")

    with open(sql_path, 'r', encoding='utf-8') as f:
        sql = f.read()

    close_after = conn is None
    if conn is None:
        conn = _get_conn()
    try:
        conn.autocommit = True
        with conn.cursor() as cur:
            cur.execute(sql)
        return {'status': 'ok', 'sql_path': sql_path}
    finally:
        if close_after:
            conn.close()


def main():
    logging.basicConfig(level=logging.INFO, format='%(levelname)s %(message)s')
    try:
        result = initialize_database()
        logger.info("Database initialized: %s", result)
    except Exception as e:
        logger.error("Failed to initialize database: %s", e)
        sys.exit(1)


if __name__ == '__main__':
    main()
