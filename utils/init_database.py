#!/usr/bin/env python3
"""Initialize database schema by running terraform/modules/database/init.sql via psql."""
import os
import sys
import logging
import subprocess

logger = logging.getLogger(__name__)


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
    """Run init.sql via psql. conn arg is accepted for API compatibility but ignored."""
    sql_path = _find_sql()
    if not sql_path:
        raise FileNotFoundError("init.sql not found in expected locations")

    host = os.environ.get('DB_HOST', 'localhost')
    port = os.environ.get('DB_PORT', '5432')
    dbname = os.environ.get('DB_NAME', 'stocks')
    user = os.environ.get('DB_USER', 'stocks')
    password = os.environ.get('DB_PASSWORD', '')

    env = {**os.environ, 'PGPASSWORD': password}
    cmd = ['psql', '-h', host, '-p', port, '-U', user, '-d', dbname, '-f', sql_path,
           '-v', 'ON_ERROR_STOP=0']
    result = subprocess.run(cmd, capture_output=True, text=True, env=env)
    if result.returncode != 0:
        raise RuntimeError(f"psql failed (rc={result.returncode}): {result.stderr[:500]}")
    return {'status': 'ok', 'sql_path': sql_path}


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
