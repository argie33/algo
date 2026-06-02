"""Route: health - Public health check endpoint"""
import psycopg2
from typing import Dict
import logging
import json
from datetime import datetime, timezone
from .utils import check_data_freshness

logger = logging.getLogger(__name__)

def handle(cur, path: str, method: str, params: Dict, body: Dict = None, jwt_claims: Dict = None) -> Dict:
    """Handle /api/health endpoint - PUBLIC health check (no auth required).

    Returns basic system status without exposing internal details.
    For detailed health info, use /api/health/detailed (requires authentication).
    """
    health = {
        "status": "healthy",
        "timestamp": datetime.now().isoformat(),
    }

    try:
        # Verify DB is responsive with a simple query
        cur.execute("SELECT 1")

        status_code = 200
        return {
            'statusCode': status_code,
            'body': json.dumps(health),
            'headers': {'Content-Type': 'application/json', 'Cache-Control': 'no-cache'}
        }

    except (psycopg2.OperationalError, psycopg2.DatabaseError) as e:
        logger.warning(f"Health check failed - DB issue: {str(e)[:100]}")
        health["status"] = "critical"
        return {
            'statusCode': 503,
            'body': json.dumps(health),
            'headers': {'Content-Type': 'application/json'}
        }
    except Exception as e:
        logger.error(f"Health check error: {str(e)[:100]}")
        health["status"] = "critical"
        return {
            'statusCode': 500,
            'body': json.dumps(health),
            'headers': {'Content-Type': 'application/json'}
        }
