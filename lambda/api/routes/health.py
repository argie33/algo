"""Route: health - Health check endpoints (basic, detailed, pipeline)"""
import psycopg2
from typing import Dict
import logging
from datetime import datetime, timezone
from .utils import check_data_freshness, success_response, error_response, execute_with_timeout, handle_db_error

logger = logging.getLogger(__name__)

def handle(cur, path: str, method: str, params: Dict, body: Dict = None, jwt_claims: Dict = None) -> Dict:
    """Handle health check endpoints.

    /api/health — PUBLIC, no auth required. Basic system status.
    /api/health/detailed — AUTHENTICATED. Database schema and table status.
    /api/health/pipeline — AUTHENTICATED. Data freshness of critical loaders.
    """

    # Route to appropriate handler
    if path.startswith('/api/health/detailed') or path.startswith('/health/detailed'):
        return _handle_detailed(cur, jwt_claims)
    elif path.startswith('/api/health/pipeline') or path.startswith('/health/pipeline'):
        return _handle_pipeline(cur, jwt_claims)
    else:
        # Basic health check (default for /api/health)
        return _handle_basic(cur)

def _handle_basic(cur) -> Dict:
    """Basic health check - PUBLIC, no auth required."""
    health = {
        "status": "healthy",
        "version": "v2-2026-05-21",
        "timestamp": datetime.now().isoformat(),
    }

    try:
        # Verify DB is responsive with a simple query (3 second timeout)
        result = execute_with_timeout(cur, "SELECT 1", timeout_sec=3)
        if result:
            return success_response(health)
        else:
            return error_response(503, 'connection_error', 'Database connection failed')

    except Exception as e:
        logger.error(f"Health check error: {str(e)[:100]}")
        code, error_type, message = handle_db_error(e, "health check")
        return error_response(code, error_type, message)

def _handle_detailed(cur, jwt_claims: Dict) -> Dict:
    """Detailed health check - AUTHENTICATED. Exposes schema information."""
    if not jwt_claims:
        return error_response(401, 'unauthorized', 'Authentication required')

    try:
        _HEALTH_TABLES = ('price_daily', 'buy_sell_daily', 'stock_scores', 'technical_data_daily')
        cur.execute("""
            SELECT relname, n_live_tup
            FROM pg_stat_user_tables
            WHERE relname = ANY(%s)
        """, (_HEALTH_TABLES,))
        table_counts = {row[0]: row[1] for row in cur.fetchall()}
        for t in _HEALTH_TABLES:
            table_counts.setdefault(t, 0)

        return success_response({
            "status": "healthy",
            "dbStatus": "connected",
            "tables": table_counts
        })
    except Exception as e:
        logger.error(f'[HEALTH_DETAILED_ERROR] {e}', exc_info=True)
        return error_response(503, 'query_error', 'Unable to fetch table status')

def _handle_pipeline(cur, jwt_claims: Dict) -> Dict:
    """Pipeline health check - AUTHENTICATED. Data freshness of critical loaders."""
    if not jwt_claims:
        return error_response(401, 'unauthorized', 'Authentication required')

    try:
        # Query freshness of critical data loaders
        query = """
            SELECT
                'price_daily' as table_name,
                COUNT(*) as row_count,
                EXTRACT(EPOCH FROM (NOW() - MAX(created_at))) / 86400.0 as age_days
            FROM price_daily
            UNION ALL
            SELECT
                'buy_sell_daily',
                COUNT(*),
                EXTRACT(EPOCH FROM (NOW() - MAX(created_at))) / 86400.0
            FROM buy_sell_daily
            UNION ALL
            SELECT
                'technical_data_daily',
                COUNT(*),
                EXTRACT(EPOCH FROM (NOW() - MAX(created_at))) / 86400.0
            FROM technical_data_daily
            UNION ALL
            SELECT
                'signal_quality_scores',
                COUNT(*),
                EXTRACT(EPOCH FROM (NOW() - MAX(created_at))) / 86400.0
            FROM signal_quality_scores
        """
        cur.execute(query)
        rows = [dict(row) for row in cur.fetchall()]

        tables = []
        for row in rows:
            age = float(row['age_days']) if row.get('age_days') is not None else 999
            status = 'HEALTHY' if age <= 2 and (row.get('row_count') or 0) > 0 else ('STALE' if age <= 7 else 'CRITICAL')
            tables.append({
                'table_name': row['table_name'],
                'row_count': row.get('row_count', 0),
                'age_days': round(age, 1),
                'status': status
            })

        healthy = sum(1 for t in tables if t['status'] == 'HEALTHY')
        return success_response({
            "status": 'HEALTHY' if healthy == len(tables) and tables else 'DEGRADED',
            "healthy_count": healthy,
            "total_count": len(tables),
            "tables": tables
        })
    except Exception as e:
        logger.error(f'[HEALTH_PIPELINE_ERROR] {e}', exc_info=True)
        return error_response(500, 'query_error', 'Unable to fetch pipeline status')
