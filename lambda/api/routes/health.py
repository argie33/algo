"""Route: health - Public health check endpoint"""
import psycopg2
from typing import Dict
import logging
from datetime import datetime, timezone
from .utils import check_data_freshness, success_response, error_response

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
        return success_response(health)

    except (psycopg2.OperationalError, psycopg2.DatabaseError) as e:
        logger.warning(f"Health check failed - DB issue: {str(e)[:100]}")
        return error_response(503, 'connection_error', 'Database connection failed')
    except Exception as e:
        logger.error(f"Health check error: {str(e)[:100]}")
        return error_response(500, 'internal_error', 'Internal server error')
