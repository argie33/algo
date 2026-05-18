"""Route: portfolio"""
import psycopg2, psycopg2.extras, psycopg2.errors, psycopg2.sql
from typing import Dict, Any, Optional, List
import logging, re
from datetime import datetime, timedelta, date, timezone

logger = logging.getLogger(__name__)

def error_response(code, typ, msg):
    return {"statusCode": code, "errorType": typ, "message": msg}

def success_response(data):
    return {"statusCode": 200, "data": data}

def list_response(items, total=None):
    return {"statusCode": 200, "items": items, "total": total or len(items)}

def _safe_limit(limit_str, max_val=50000, default=500):
    if not limit_str:
        return default
    try:
        return min(int(limit_str), max_val)
    except:
        return default

def handle(cur, path: str, method: str, params: Dict, body: Dict = None) -> Dict:
        """Handle /api/portfolio/* endpoints."""
        try:
            if path == '/api/portfolio/summary':
                cur.execute("""
                    SELECT
                        COALESCE(SUM(position_value), 0) as total_invested,
                        COUNT(*) as position_count
                    FROM algo_positions WHERE status='open'
                """)
                row = cur.fetchone()
                total_invested = float(row['total_invested'] or 0) if row else 0
                position_count = int(row['position_count'] or 0) if row else 0
                # Get latest account value from snapshots for real exposure calc
                cur.execute("""
                    SELECT total_portfolio_value FROM algo_portfolio_snapshots
                    ORDER BY snapshot_date DESC LIMIT 1
                """)
                snap = cur.fetchone()
                portfolio_value = float(snap['total_portfolio_value'] or 0) if snap else 0
                exposure = round(total_invested / portfolio_value, 4) if portfolio_value > 0 else 0.0
                return json_response(200, {
                    'total_value': total_invested,
                    'portfolio_value': portfolio_value,
                    'position_count': position_count,
                    'cash': max(0, portfolio_value - total_invested),
                    'exposure': exposure,
                })
            elif path == '/api/portfolio/allocation':
                cur.execute("""
                    SELECT
                        COALESCE(cp.sector, 'Unknown') as sector,
                        COUNT(*) as count,
                        SUM(ap.position_value) as value
                    FROM algo_positions ap
                    LEFT JOIN company_profile cp ON ap.symbol = cp.ticker
                    WHERE ap.status = 'open'
                    GROUP BY COALESCE(cp.sector, 'Unknown')
                    ORDER BY value DESC
                """)
                alloc = cur.fetchall()
                return list_response([dict(a) for a in alloc])
            return error_response(404, 'not_found', f'Unknown portfolio endpoint: {path}')
        except psycopg2.errors.UndefinedTable as e:
            logger.error(f'Required table not found: {e}', extra={'operation': 'handle portfolio'})
            return error_response(503, 'service_unavailable', 'Data pipeline loading')
        except psycopg2.errors.UndefinedColumn as e:
            logger.error(f'Column not found: {e}', extra={'operation': 'handle portfolio'})
            return error_response(503, 'service_unavailable', 'Data schema mismatch')
        except psycopg2.OperationalError as e:
            logger.error(f'Database connection error: {e}', extra={'operation': 'handle portfolio'})
            return error_response(503, 'service_unavailable', 'Database unavailable')
        except psycopg2.DatabaseError as e:
            logger.error(f'Database error: {e}', extra={'operation': 'handle portfolio', 'error_type': type(e).__name__})
            return error_response(500, 'internal_error', 'Database query failed')
        except Exception as e:
            logger.error(f'Unexpected error: {e}', extra={'operation': 'handle portfolio', 'error_type': type(e).__name__})
            return error_response(500, 'internal_error', 'Failed to fetch portfolio allocation')
