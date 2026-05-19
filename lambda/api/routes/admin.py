"""Route: admin"""
import psycopg2, psycopg2.extras, psycopg2.errors, psycopg2.sql
from typing import Dict, Any, Optional, List
import logging, re
from datetime import datetime, timedelta, date, timezone
from .utils import error_response, success_response, list_response, json_response, safe_limit, handle_db_error

logger = logging.getLogger(__name__)

def _check_admin_access(params: Dict) -> bool:
        """Check if user has admin access.

        Reads user_role from query params — the API gateway extracts this from
        the verified Cognito JWT and injects it before routing. Admin users must
        be in the 'admin' Cognito group.
        """
        user_role = params.get('user_role', '') if params else ''
        return user_role == 'admin'

def handle(cur, path: str, method: str, params: Dict, body: Dict = None) -> Dict:
        """Handle /api/admin/* endpoints for operational visibility."""
        try:
            # Require admin role for all admin endpoints
            if not _check_admin_access(params):
                return error_response(403, 'forbidden', 'Admin access required')

            if path == '/api/admin/loader-status':
                return _get_loader_status(cur)
            elif path == '/api/admin/system-health':
                return _get_system_health(cur)
            elif path == '/api/admin/database-stats':
                return _get_database_stats(cur)
            elif path == '/api/admin/data-quality':
                return _get_data_quality(cur)
            return error_response(404, 'not_found', f'No admin handler for {path}')
        except (psycopg2.errors.UndefinedTable, psycopg2.errors.UndefinedColumn,
                psycopg2.OperationalError, psycopg2.DatabaseError, Exception) as e:
            return handle_db_error(e, logger, 'handle admin')
def _get_loader_status(cur) -> Dict:
        """Get status of all data loaders from data_loader_runs table."""
        try:
            cur.execute("""
                SELECT
                    loader_name,
                    run_date AS start_at,
                    records_loaded AS symbol_count,
                    duration_seconds,
                    (status = 'completed') AS success,
                    0 AS error_count,
                    '' AS table_name
                FROM data_loader_runs
                WHERE (loader_name, run_date) IN (
                    SELECT loader_name, MAX(run_date)
                    FROM data_loader_runs
                    GROUP BY loader_name
                )
                ORDER BY run_date DESC, loader_name
            """)
            rows = cur.fetchall()

            if not rows:
                return json_response(200, {
                    'status': 'no_runs',
                    'message': 'No loader runs recorded yet',
                    'loaders': []
                })

            loaders = []
            for row in rows:
                start_time = row['start_at']
                age_hours = (datetime.now(timezone.utc) - start_time.replace(tzinfo=timezone.utc)).total_seconds() / 3600
                health = 'stale' if age_hours > 24 else 'fresh'
                status = 'success' if row['success'] else 'failed'

                loaders.append({
                    'name': row['loader_name'],
                    'table': row['table_name'],
                    'last_run': start_time.isoformat() if start_time else None,
                    'symbols_processed': row['symbol_count'] or 0,
                    'duration_seconds': row['duration_seconds'] or 0,
                    'status': status,
                    'errors': row['error_count'] or 0,
                    'age_hours': round(age_hours, 1),
                    'health': health,
                })

            return json_response(200, {
                'status': 'ok',
                'loaders': loaders,
                'summary': {
                    'total': len(loaders),
                    'healthy': len([l for l in loaders if l['health'] == 'fresh']),
                    'stale': len([l for l in loaders if l['health'] == 'stale']),
                    'failed': len([l for l in loaders if l['status'] == 'failed']),
                }
            })
        except (psycopg2.errors.UndefinedTable, psycopg2.errors.UndefinedColumn,
                psycopg2.OperationalError, psycopg2.DatabaseError, Exception) as e:
            return handle_db_error(e, logger, 'get loader status')
def _get_system_health(cur) -> Dict:
        """Get overall system health status."""
        try:
            health_data = {'status': 'healthy', 'components': {}}

            try:
                cur.execute("SELECT 1")
                health_data['components']['database'] = 'ok'
            except (psycopg2.errors.UndefinedTable, psycopg2.errors.UndefinedColumn,
                    psycopg2.OperationalError, psycopg2.DatabaseError, Exception) as e:
                health_data['components']['database'] = 'error'
                health_data['status'] = 'degraded'

            cur.execute("SELECT MAX(date) FROM price_daily")
            last_price_date = next(iter(dict(cur.fetchone() or {}).values()), 0)
            if last_price_date:
                age_days = (datetime.now(timezone.utc).date() - last_price_date).days
                health_data['components']['data_freshness'] = 'ok' if age_days <= 3 else 'stale'
                health_data['last_data_update'] = last_price_date.isoformat()
                if age_days > 3:
                    health_data['status'] = 'degraded'
            else:
                health_data['components']['data_freshness'] = 'no_data'
                health_data['status'] = 'unhealthy'

            table_counts = {}
            for table in ['stock_symbols', 'price_daily', 'algo_trades', 'algo_positions']:
                try:
                    query = psycopg2.sql.SQL("SELECT COUNT(*) FROM {}").format(
                        psycopg2.sql.Identifier(table)
                    )
                    cur.execute(query)
                    count = next(iter(dict(cur.fetchone() or {}).values()), 0)
                    table_counts[table] = count
                except (psycopg2.Error, TypeError, AttributeError) as e:
                    logger.warning(f"Failed to count rows in table {table}: {e}")
                    table_counts[table] = 0

            health_data['tables'] = table_counts
            health_data['timestamp'] = datetime.now(timezone.utc).isoformat()
            return json_response(200, health_data)
        except (psycopg2.errors.UndefinedTable, psycopg2.errors.UndefinedColumn,
                psycopg2.OperationalError, psycopg2.DatabaseError, Exception) as e:
            return handle_db_error(e, logger, 'get system health')
def _get_database_stats(cur) -> Dict:
        """Get database statistics (schema-safe version - no table name exposure)."""
        try:
            stats = {}

            # Count active connections without exposing table structure
            cur.execute("SELECT count(*) FROM pg_stat_activity WHERE state != 'idle'")
            stats['active_connections'] = next(iter(dict(cur.fetchone() or {}).values()), 0)

            # Get high-level DB size without exposing individual table names
            cur.execute("""
                SELECT pg_size_pretty(pg_database_size(current_database())) as total_size
            """)
            size_row = cur.fetchone()
            stats['total_database_size'] = dict(size_row).get('total_size', 'unknown') if size_row else 'unknown'

            # Check if any tables exist without revealing names
            cur.execute("""
                SELECT COUNT(*) as table_count FROM information_schema.tables
                WHERE table_schema NOT IN ('pg_catalog', 'information_schema')
            """)
            table_count_row = cur.fetchone()
            stats['table_count'] = dict(table_count_row).get('table_count', 0) if table_count_row else 0

            stats['timestamp'] = datetime.now(timezone.utc).isoformat()
            return json_response(200, stats)
        except (psycopg2.errors.UndefinedTable, psycopg2.errors.UndefinedColumn,
                psycopg2.OperationalError, psycopg2.DatabaseError, Exception) as e:
            return handle_db_error(e, logger, 'get database stats')
def _get_data_quality(cur) -> Dict:
        """Get data quality metrics."""
        try:
            quality = {'timestamp': datetime.now(timezone.utc).isoformat(), 'checks': {}}

            cur.execute("""
                SELECT COUNT(*) FROM price_daily
                WHERE close IS NULL OR open IS NULL OR high IS NULL OR low IS NULL
            """)
            null_prices = next(iter(dict(cur.fetchone() or {}).values()), 0)
            quality['checks']['null_prices'] = {'count': null_prices, 'status': 'ok' if null_prices == 0 else 'warning'}

            cur.execute("""
                SELECT COUNT(*) FROM (
                    SELECT symbol, date, COUNT(*)
                    FROM price_daily
                    GROUP BY symbol, date HAVING COUNT(*) > 1
                ) t
            """)
            duplicate_prices = next(iter(dict(cur.fetchone() or {}).values()), 0)
            quality['checks']['duplicate_prices'] = {'count': duplicate_prices, 'status': 'ok' if duplicate_prices == 0 else 'warning'}

            cur.execute("""
                SELECT COUNT(*) FROM price_daily
                WHERE high < low OR close > high OR close < low
            """)
            invalid_prices = next(iter(dict(cur.fetchone() or {}).values()), 0)
            quality['checks']['invalid_price_ranges'] = {'count': invalid_prices, 'status': 'ok' if invalid_prices == 0 else 'error'}

            # Overall status
            quality['status'] = 'healthy' if invalid_prices == 0 else 'degraded'

            return json_response(200, quality)
        except (psycopg2.errors.UndefinedTable, psycopg2.errors.UndefinedColumn,
                psycopg2.OperationalError, psycopg2.DatabaseError, Exception) as e:
            return handle_db_error(e, logger, 'get data quality')
