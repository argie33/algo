"""Route: admin"""
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

def json_response(code, data):
    return {"statusCode": code, **data}

def _safe_limit(limit_str, max_val=50000, default=500):
    if not limit_str:
        return default
    try:
        return min(int(limit_str), max_val)
    except:
        return default

def handle(cur, path: str, method: str, params: Dict, body: Dict = None) -> Dict:
        """Handle /api/admin/* endpoints for operational visibility."""
        try:
            if path == '/api/admin/loader-status':
                return _get_loader_status(cur)
            elif path == '/api/admin/system-health':
                return _get_system_health(cur)
            elif path == '/api/admin/database-stats':
                return _get_database_stats(cur)
            elif path == '/api/admin/data-quality':
                return _get_data_quality(cur)
            return error_response(404, 'not_found', f'No admin handler for {path}')
        except psycopg2.errors.UndefinedTable as e:
            logger.error(f'Required table not found: {e}', extra={'operation': 'handle admin'})
            return error_response(503, 'service_unavailable', 'Data pipeline loading')
        except psycopg2.errors.UndefinedColumn as e:
            logger.error(f'Column not found: {e}', extra={'operation': 'handle admin'})
            return error_response(503, 'service_unavailable', 'Data schema mismatch')
        except psycopg2.OperationalError as e:
            logger.error(f'Database connection error: {e}', extra={'operation': 'handle admin'})
            return error_response(503, 'service_unavailable', 'Database unavailable')
        except psycopg2.DatabaseError as e:
            logger.error(f'Database error: {e}', extra={'operation': 'handle admin', 'error_type': type(e).__name__})
            return error_response(500, 'internal_error', 'Database query failed')
        except Exception as e:
            logger.error(f'Unexpected error: {e}', extra={'operation': 'handle admin', 'error_type': type(e).__name__})
            return error_response(500, 'internal_error', 'Admin handler error')
def _get_loader_status(cur) -> Dict:
        """Get status of all data loaders from data_loader_runs table."""
        try:
            cur.execute("""
                SELECT
                    loader_name,
                    start_at,
                    symbol_count,
                    duration_seconds,
                    success,
                    error_count,
                    table_name
                FROM data_loader_runs
                WHERE (loader_name, start_at) IN (
                    SELECT loader_name, MAX(start_at)
                    FROM data_loader_runs
                    GROUP BY loader_name
                )
                ORDER BY start_at DESC, loader_name
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
        except psycopg2.errors.UndefinedTable as e:
            logger.error(f'Required table not found: {e}', extra={'operation': 'get loader status'})
            return error_response(503, 'service_unavailable', 'Data pipeline loading')
        except psycopg2.errors.UndefinedColumn as e:
            logger.error(f'Column not found: {e}', extra={'operation': 'get loader status'})
            return error_response(503, 'service_unavailable', 'Data schema mismatch')
        except psycopg2.OperationalError as e:
            logger.error(f'Database connection error: {e}', extra={'operation': 'get loader status'})
            return error_response(503, 'service_unavailable', 'Database unavailable')
        except psycopg2.DatabaseError as e:
            logger.error(f'Database error: {e}', extra={'operation': 'get loader status', 'error_type': type(e).__name__})
            return error_response(500, 'internal_error', 'Database query failed')
        except Exception as e:
            logger.error(f'Unexpected error: {e}', extra={'operation': 'get loader status', 'error_type': type(e).__name__})
            return error_response(500, 'internal_error', 'Failed to fetch loader status')
def _get_system_health(cur) -> Dict:
        """Get overall system health status."""
        try:
            health_data = {'status': 'healthy', 'components': {}}

            # Check database connectivity
            try:
                cur.execute("SELECT 1")
                health_data['components']['database'] = 'ok'
            except psycopg2.errors.UndefinedTable as e:
                logger.error(f'Required table not found: {e}', extra={'operation': 'get system health'})
                return error_response(503, 'service_unavailable', 'Data pipeline loading')
            except psycopg2.errors.UndefinedColumn as e:
                logger.error(f'Column not found: {e}', extra={'operation': 'get system health'})
                return error_response(503, 'service_unavailable', 'Data schema mismatch')
            except psycopg2.OperationalError as e:
                logger.error(f'Database connection error: {e}', extra={'operation': 'get system health'})
                return error_response(503, 'service_unavailable', 'Database unavailable')
            except psycopg2.DatabaseError as e:
                logger.error(f'Database error: {e}', extra={'operation': 'get system health', 'error_type': type(e).__name__})
                return error_response(500, 'internal_error', 'Database query failed')
            except Exception as e:
                logger.error(f'Unexpected error: {e}', extra={'operation': 'get system health', 'error_type': type(e).__name__})
                return error_response(500, 'internal_error', 'Failed to fetch data')
                logger.error(f"Database health check failed: {e}")
                health_data['components']['database'] = 'error'
                health_data['status'] = 'degraded'

            # Check data freshness
            cur.execute("SELECT MAX(date) FROM price_daily")
            last_price_date = cur.fetchone()[0]
            if last_price_date:
                age_days = (datetime.now(timezone.utc).date() - last_price_date).days
                health_data['components']['data_freshness'] = 'ok' if age_days <= 3 else 'stale'
                health_data['last_data_update'] = last_price_date.isoformat()
                if age_days > 3:
                    health_data['status'] = 'degraded'
            else:
                health_data['components']['data_freshness'] = 'no_data'
                health_data['status'] = 'unhealthy'

            # Check table counts
            table_counts = {}
            for table in ['stock_symbols', 'price_daily', 'algo_trades', 'algo_positions']:
                try:
                    query = psycopg2.sql.SQL("SELECT COUNT(*) FROM {}").format(
                        psycopg2.sql.Identifier(table)
                    )
                    cur.execute(query)
                    count = cur.fetchone()[0]
                    table_counts[table] = count
                except (psycopg2.Error, TypeError, AttributeError) as e:
                    logger.warning(f"Failed to count rows in table {table}: {e}")
                    table_counts[table] = 0

            health_data['tables'] = table_counts
            health_data['timestamp'] = datetime.now(timezone.utc).isoformat()
            return json_response(200, health_data)
        except psycopg2.errors.UndefinedTable as e:
            logger.error(f'Required table not found: {e}', extra={'operation': 'get system health'})
            return error_response(503, 'service_unavailable', 'Data pipeline loading')
        except psycopg2.errors.UndefinedColumn as e:
            logger.error(f'Column not found: {e}', extra={'operation': 'get system health'})
            return error_response(503, 'service_unavailable', 'Data schema mismatch')
        except psycopg2.OperationalError as e:
            logger.error(f'Database connection error: {e}', extra={'operation': 'get system health'})
            return error_response(503, 'service_unavailable', 'Database unavailable')
        except psycopg2.DatabaseError as e:
            logger.error(f'Database error: {e}', extra={'operation': 'get system health', 'error_type': type(e).__name__})
            return error_response(500, 'internal_error', 'Database query failed')
        except Exception as e:
            logger.error(f'Unexpected error: {e}', extra={'operation': 'get system health', 'error_type': type(e).__name__})
            return error_response(500, 'internal_error', 'Failed to get system health')
def _get_database_stats(cur) -> Dict:
        """Get database statistics."""
        try:
            stats = {}

            # Get table sizes
            cur.execute("""
                SELECT
                    schemaname,
                    tablename,
                    pg_size_pretty(pg_total_relation_size(schemaname||'.'||tablename)) as size
                FROM pg_tables
                WHERE schemaname NOT IN ('pg_catalog', 'information_schema')
                ORDER BY pg_total_relation_size(schemaname||'.'||tablename) DESC
                LIMIT 20
            """)

            tables = []
            for row in cur.fetchall():
                tables.append({'name': row[1], 'size': row[2]})

            stats['largest_tables'] = tables

            # Get connection info
            cur.execute("SELECT count(*) FROM pg_stat_activity WHERE state != 'idle'")
            stats['active_connections'] = cur.fetchone()[0]

            # Get index usage
            cur.execute("""
                SELECT COUNT(*) FROM pg_stat_user_indexes WHERE idx_scan = 0
            """)
            stats['unused_indexes'] = cur.fetchone()[0]

            stats['timestamp'] = datetime.now(timezone.utc).isoformat()
            return json_response(200, stats)
        except psycopg2.errors.UndefinedTable as e:
            logger.error(f'Required table not found: {e}', extra={'operation': 'get database stats'})
            return error_response(503, 'service_unavailable', 'Data pipeline loading')
        except psycopg2.errors.UndefinedColumn as e:
            logger.error(f'Column not found: {e}', extra={'operation': 'get database stats'})
            return error_response(503, 'service_unavailable', 'Data schema mismatch')
        except psycopg2.OperationalError as e:
            logger.error(f'Database connection error: {e}', extra={'operation': 'get database stats'})
            return error_response(503, 'service_unavailable', 'Database unavailable')
        except psycopg2.DatabaseError as e:
            logger.error(f'Database error: {e}', extra={'operation': 'get database stats', 'error_type': type(e).__name__})
            return error_response(500, 'internal_error', 'Database query failed')
        except Exception as e:
            logger.error(f'Unexpected error: {e}', extra={'operation': 'get database stats', 'error_type': type(e).__name__})
            return error_response(500, 'internal_error', 'Failed to get database stats')
def _get_data_quality(cur) -> Dict:
        """Get data quality metrics."""
        try:
            quality = {'timestamp': datetime.now(timezone.utc).isoformat(), 'checks': {}}

            # Check for null prices
            cur.execute("""
                SELECT COUNT(*) FROM price_daily
                WHERE close IS NULL OR open IS NULL OR high IS NULL OR low IS NULL
            """)
            null_prices = cur.fetchone()[0]
            quality['checks']['null_prices'] = {'count': null_prices, 'status': 'ok' if null_prices == 0 else 'warning'}

            # Check for duplicate prices
            cur.execute("""
                SELECT COUNT(*) FROM (
                    SELECT symbol, date, COUNT(*)
                    FROM price_daily
                    GROUP BY symbol, date HAVING COUNT(*) > 1
                ) t
            """)
            duplicate_prices = cur.fetchone()[0]
            quality['checks']['duplicate_prices'] = {'count': duplicate_prices, 'status': 'ok' if duplicate_prices == 0 else 'warning'}

            # Check price logical consistency (high >= low >= close)
            cur.execute("""
                SELECT COUNT(*) FROM price_daily
                WHERE high < low OR close > high OR close < low
            """)
            invalid_prices = cur.fetchone()[0]
            quality['checks']['invalid_price_ranges'] = {'count': invalid_prices, 'status': 'ok' if invalid_prices == 0 else 'error'}

            # Overall status
            quality['status'] = 'healthy' if invalid_prices == 0 else 'degraded'

            return json_response(200, quality)
        except psycopg2.errors.UndefinedTable as e:
            logger.error(f'Required table not found: {e}', extra={'operation': 'get data quality'})
            return error_response(503, 'service_unavailable', 'Data pipeline loading')
        except psycopg2.errors.UndefinedColumn as e:
            logger.error(f'Column not found: {e}', extra={'operation': 'get data quality'})
            return error_response(503, 'service_unavailable', 'Data schema mismatch')
        except psycopg2.OperationalError as e:
            logger.error(f'Database connection error: {e}', extra={'operation': 'get data quality'})
            return error_response(503, 'service_unavailable', 'Database unavailable')
        except psycopg2.DatabaseError as e:
            logger.error(f'Database error: {e}', extra={'operation': 'get data quality', 'error_type': type(e).__name__})
            return error_response(500, 'internal_error', 'Database query failed')
        except Exception as e:
            logger.error(f'Unexpected error: {e}', extra={'operation': 'get data quality', 'error_type': type(e).__name__})
            return error_response(500, 'internal_error', 'Failed to get data quality metrics')
