#!/usr/bin/env python3
"""
Lambda function to identify and terminate blocking database locks.
Can be invoked before migrations to clear lock contention.
"""

import json
import logging
import sys
from pathlib import Path

logger = logging.getLogger()
logger.setLevel(logging.INFO)

# Add project root to path
sys.path.insert(0, str(Path(__file__).parent.parent.parent))


def lambda_handler(event, context):
    """Identify and terminate database locks."""
    try:
        import psycopg2
    except ImportError:
        logger.error("psycopg2 not available in Lambda")
        return {
            "statusCode": 500,
            "body": json.dumps({
                "success": False,
                "error": "psycopg2 library not available"
            })
        }

    try:
        from config.credential_manager import get_db_credentials
        creds = get_db_credentials()
    except Exception as e:
        logger.error(f"Failed to get credentials: {e}")
        return {
            "statusCode": 400,
            "body": json.dumps({
                "success": False,
                "error": f"Failed to get database credentials: {e}"
            })
        }

    try:
        conn = psycopg2.connect(
            host=creds['host'],
            port=creds['port'],
            database=creds['database'],
            user=creds['user'],
            password=creds['password'],
            connect_timeout=5
        )
        cur = conn.cursor()

        # Find long-running queries (> 30 seconds)
        cur.execute("""
            SELECT pid, usename, state, query, extract(epoch FROM (now() - query_start)) as duration_secs
            FROM pg_stat_activity
            WHERE state != 'idle'
              AND pid != pg_backend_pid()
              AND query_start < now() - interval '30 seconds'
            ORDER BY query_start ASC;
        """)

        long_running = cur.fetchall()
        killed = []

        for pid, user, _state, query, duration in long_running:
            logger.info(f"Found long-running query: PID {pid} ({user}) for {duration:.0f}s: {query[:100]}")

            # Terminate it
            cur.execute("SELECT pg_terminate_backend(%s);", (pid,))
            result = cur.fetchone()[0]
            if result:
                killed.append({"pid": pid, "user": user, "duration_s": int(duration)})
                logger.info(f"Terminated PID {pid}")

        conn.commit()
        conn.close()

        return {
            "statusCode": 200,
            "body": json.dumps({
                "success": True,
                "message": f"Terminated {len(killed)} long-running queries",
                "killed_pids": killed
            })
        }

    except Exception as e:
        logger.error(f"Database error: {e}", exc_info=True)
        return {
            "statusCode": 500,
            "body": json.dumps({
                "success": False,
                "error": str(e)
            })
        }
