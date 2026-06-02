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

        # Check stock scores freshness (swing_trader_scores is the live table)
        scores_freshness = check_data_freshness(cur, 'swing_trader_scores', 'date', warning_days=7)
        health["checks"]["stock_scores"] = scores_freshness

        # Check orchestrator status
        # The orchestrator runs Mon–Fri only. On weekends the last run was Friday
        # evening, so the age threshold must account for up to ~60h gap (Fri 5:30 PM
        # → Sun night) before flagging as stale.
        try:
            cur.execute("""
                SELECT created_at FROM algo_audit_log
                ORDER BY created_at DESC LIMIT 1
            """)
            result = cur.fetchone()
            if result:
                last_run = result[0]
                if last_run.tzinfo is None:
                    last_run = last_run.replace(tzinfo=timezone.utc)
                age_hours = (datetime.now(timezone.utc) - last_run).total_seconds() / 3600
                # On weekends the orchestrator legitimately hasn't run since Friday.
                # Allow up to 72 h (Fri 5:30 PM → Mon 5:30 AM) before flagging stale.
                import datetime as _dt
                weekday = _dt.datetime.now(_dt.timezone.utc).weekday()
                stale_threshold = 72 if weekday in (5, 6) else 4  # Sat=5, Sun=6
                is_stale = age_hours > stale_threshold
                health["checks"]["orchestrator"] = {
                    "last_run": last_run.isoformat(),
                    "age_hours": round(age_hours, 1),
                    "is_stale": is_stale
                }
                if is_stale and health["status"] == "healthy":
                    health["status"] = "degraded"
            else:
                health["checks"]["orchestrator"] = {"error": "No orchestrator runs found"}
        except Exception as e:
            health["checks"]["orchestrator"] = {"error": str(e)[:100]}

        # Check loader status (if available)
        try:
            cur.execute("""
                SELECT
                    COUNT(*) as total_loaders,
                    COUNT(*) FILTER (WHERE status = 'failed') as failed_loaders,
                    COUNT(*) FILTER (WHERE status = 'stale') as stale_loaders
                FROM data_loader_status
            """)
            result = cur.fetchone()
            if result:
                total = result['total_loaders'] or 0
                failed = result['failed_loaders'] or 0
                stale = result['stale_loaders'] or 0
                health["checks"]["loaders"] = {
                    "total": total,
                    "failed": failed,
                    "stale": stale,
                }
                if failed > 0 or stale > 0:
                    health["status"] = "degraded"
        except Exception as e:
            health["checks"]["loaders"] = {"error": "Loader status unavailable"}

        status_code = 200 if health["status"] == "healthy" else 503
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
