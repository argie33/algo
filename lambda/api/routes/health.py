"""Route: health - Public health check endpoint"""
import psycopg2
from typing import Dict
import logging
import json
from datetime import datetime
from .utils import check_data_freshness

logger = logging.getLogger(__name__)

def handle(cur, path: str, method: str, params: Dict, body: Dict = None) -> Dict:
    """Handle /api/health endpoint - PUBLIC health check (no auth required).

    Returns comprehensive system health status including:
    - Database connectivity
    - Data freshness checks
    - Orchestrator execution status
    - Overall system status (healthy/degraded/critical)
    """
    health = {
        "status": "healthy",
        "timestamp": datetime.now().isoformat(),
        "database": "disconnected",
        "checks": {}
    }

    try:
        # Test database connectivity
        if cur is None:
            health["status"] = "critical"
            health["database"] = "disconnected"
            return {
                'statusCode': 503,
                'body': json.dumps(health),
                'headers': {'Content-Type': 'application/json'}
            }

        # Verify DB is responsive
        cur.execute("SELECT 1")
        health["database"] = "connected"

        # Check price data freshness
        price_freshness = check_data_freshness(cur, 'price_daily', 'date', warning_days=1)
        health["checks"]["price_data"] = price_freshness
        if price_freshness.get("is_stale"):
            health["status"] = "degraded"

        # Check technical data freshness
        tech_freshness = check_data_freshness(cur, 'technical_data_daily', 'date', warning_days=1)
        health["checks"]["technical_data"] = tech_freshness
        if tech_freshness.get("is_stale") and health["status"] == "healthy":
            health["status"] = "degraded"

        # Check signal data freshness
        signal_freshness = check_data_freshness(cur, 'buy_sell_daily', 'date', warning_days=1)
        health["checks"]["signal_data"] = signal_freshness

        # Check stock scores freshness
        scores_freshness = check_data_freshness(cur, 'stock_scores', 'updated_at', warning_days=7)
        health["checks"]["stock_scores"] = scores_freshness

        # Check orchestrator status
        try:
            cur.execute("""
                SELECT created_at FROM algo_audit_log
                ORDER BY created_at DESC LIMIT 1
            """)
            result = cur.fetchone()
            if result:
                from datetime import datetime, timezone
                last_run = result[0]
                if last_run.tzinfo is None:
                    last_run = last_run.replace(tzinfo=timezone.utc)
                age_hours = (datetime.now(timezone.utc) - last_run).total_seconds() / 3600
                health["checks"]["orchestrator"] = {
                    "last_run": last_run.isoformat(),
                    "age_hours": round(age_hours, 1),
                    "is_stale": age_hours > 4
                }
                if age_hours > 4 and health["status"] == "healthy":
                    health["status"] = "degraded"
            else:
                health["checks"]["orchestrator"] = {"error": "No orchestrator runs found"}
        except Exception as e:
            health["checks"]["orchestrator"] = {"error": str(e)[:100]}

        # Check loader status (if available)
        try:
            cur.execute("""
                SELECT COUNT(*) as total_loaders,
                       COUNT(CASE WHEN status = 'failed' THEN 1 END) as failed_loaders
                FROM data_loader_status
                WHERE status IN ('stale', 'failed')
            """)
            result = cur.fetchone()
            if result:
                health["checks"]["loaders"] = {
                    "total": result[0],
                    "failed": result[1]
                }
                if result[1] > 0:
                    health["status"] = "degraded"
        except Exception as e:
            health["checks"]["loaders"] = {"error": "Loader status unavailable"}

        status_code = 200 if health["status"] == "healthy" else (503 if health["status"] == "critical" else 200)
        return {
            'statusCode': status_code,
            'body': json.dumps(health),
            'headers': {'Content-Type': 'application/json', 'Cache-Control': 'no-cache'}
        }

    except (psycopg2.OperationalError, psycopg2.DatabaseError) as e:
        logger.warning(f"Health check failed - DB issue: {str(e)[:100]}")
        health["status"] = "critical"
        health["database"] = "disconnected"
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
