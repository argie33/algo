"""Route: health - Public health check endpoint"""
import psycopg2
from typing import Dict
import logging

logger = logging.getLogger(__name__)

def handle(cur, path: str, method: str, params: Dict, body: Dict = None) -> Dict:
    """Handle /api/health endpoint - PUBLIC health check (no auth required)."""
    try:
        # Test database connectivity
        if cur is None:
            return {
                'statusCode': 503,
                'body': '{"status":"unhealthy","reason":"no_database_connection"}',
                'headers': {'Content-Type': 'application/json'}
            }

        # Quick query to verify DB is responsive
        cur.execute("SELECT 1")
        db_connected = True

        return {
            'statusCode': 200,
            'body': '{"status":"healthy","database":"connected"}',
            'headers': {'Content-Type': 'application/json', 'Cache-Control': 'no-cache'}
        }
    except (psycopg2.OperationalError, psycopg2.DatabaseError) as e:
        logger.warning(f"Health check failed - DB issue: {str(e)[:100]}")
        return {
            'statusCode': 503,
            'body': '{"status":"unhealthy","reason":"database_unavailable"}',
            'headers': {'Content-Type': 'application/json'}
        }
    except Exception as e:
        logger.error(f"Health check error: {str(e)[:100]}")
        return {
            'statusCode': 500,
            'body': '{"status":"error","reason":"internal_error"}',
            'headers': {'Content-Type': 'application/json'}
        }
