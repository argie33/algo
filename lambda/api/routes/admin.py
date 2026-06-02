"""Route: admin"""
import psycopg2, psycopg2.extras, psycopg2.errors, psycopg2.sql
from typing import Dict, Any, Optional, List
import logging, re, os, boto3
from datetime import datetime, timedelta, date, timezone
from .utils import error_response, success_response, list_response, json_response, safe_limit, handle_db_error, check_data_freshness
from utils.admin_rate_limiter import check_admin_rate_limit, ADMIN_RATE_LIMITS

logger = logging.getLogger(__name__)

def _check_admin_access(jwt_claims: Dict) -> bool:
        """Check if user has admin access from verified JWT claims only.

        Checks the 'cognito:groups' claim for 'admin' group membership.
        Never trust role from query params - only from JWT signature.
        """
        if not jwt_claims:
            return False
        groups = jwt_claims.get('cognito:groups') or []
        is_admin = 'admin' in groups
        if not is_admin:
            logger.info(f"Access denied: user {jwt_claims.get('sub')} not in admin group. Groups: {groups}")
        return is_admin

def _audit_log_admin_action(cur, user_id: str, endpoint: str, status: str = 'success', details: str = '') -> None:
    """Log all admin actions for accountability."""
    try:
        import json as _json
        cur.execute("""
            INSERT INTO algo_audit_log (action_type, actor, status, details, action_date, created_at)
            VALUES (%s, %s, %s, %s, NOW(), NOW())
        """, ('admin_access', user_id, status, _json.dumps({'endpoint': endpoint, 'details': details})))
    except Exception as e:
        logger.warning(f"Failed to audit admin access: {e}")

def handle(cur, path: str, method: str, params: Dict, body: Dict = None, jwt_claims: Dict = None) -> Dict:
        """Handle /api/admin/* endpoints for operational visibility."""
        try:
            # Require admin role for all admin endpoints
            if not _check_admin_access(jwt_claims):
                user_id = (jwt_claims or {}).get('sub', 'unknown')
                _audit_log_admin_action(cur, user_id, path, 'denied', 'insufficient permissions')
                return error_response(403, 'forbidden', 'Admin access required')

            user_id = (jwt_claims or {}).get('sub', 'unknown')

            # SECURITY FIX S-09: Rate limit admin endpoints to prevent abuse
            if path in ADMIN_RATE_LIMITS:
                limits = ADMIN_RATE_LIMITS[path]
                is_allowed, error_msg = check_admin_rate_limit(
                    user_id, path,
                    max_requests=limits['max_requests'],
                    window_seconds=limits['window']
                )
                if not is_allowed:
                    _audit_log_admin_action(cur, user_id, path, 'denied', f'rate_limited: {error_msg}')
                    return error_response(429, 'too_many_requests', error_msg)

            if path == '/api/admin/loader-status':
                result = _get_loader_status(cur)
                _audit_log_admin_action(cur, user_id, path, 'success')
                return result
            elif path == '/api/admin/system-health':
                result = _get_system_health(cur)
                _audit_log_admin_action(cur, user_id, path, 'success')
                return result
            elif path == '/api/admin/database-stats':
                result = _get_database_stats(cur)
                _audit_log_admin_action(cur, user_id, path, 'success')
                return result
            elif path == '/api/admin/data-quality':
                result = _get_data_quality(cur)
                _audit_log_admin_action(cur, user_id, path, 'success')
                return result
            elif path == '/api/admin/verify-user-email' and method == 'POST':
                result = _verify_user_email(body)
                _audit_log_admin_action(cur, user_id, path, 'success', f"verified: {body.get('username', 'unknown')}")
                return result

            _audit_log_admin_action(cur, user_id, path, 'failed', 'endpoint not found')
            return error_response(404, 'not_found', f'No admin handler for {path}')
        except (psycopg2.errors.UndefinedTable, psycopg2.errors.UndefinedColumn,
                psycopg2.OperationalError, psycopg2.DatabaseError, Exception) as e:
            return handle_db_error(e, logger, 'handle admin')
def _get_loader_status(cur) -> Dict:
        """Get status of all data loaders from data_loader_status table.

        Reads from data_loader_status, which OptimalLoader updates after each run
        with the table's current row count and latest watermark date.
        """
        try:
            cur.execute("""
                SELECT
                    table_name,
                    row_count,
                    latest_date,
                    last_updated,
                    status,
                    error_message
                FROM data_loader_status
                ORDER BY last_updated DESC NULLS LAST, table_name
            """)
            rows = cur.fetchall()

            if not rows:
                return json_response(200, {
                    'status': 'no_runs',
                    'message': 'No loader runs recorded yet',
                    'loaders': []
                })

            now = datetime.now(timezone.utc)
            loaders = []
            for row in rows:
                last_updated = row['last_updated']
                if last_updated:
                    if last_updated.tzinfo is None:
                        last_updated = last_updated.replace(tzinfo=timezone.utc)
                    age_hours = (now - last_updated).total_seconds() / 3600
                else:
                    age_hours = 9999
                # Loaders run on weekdays only; allow up to 72h (covers 3-day weekends)
                health = 'stale' if age_hours > 72 else 'fresh'
                status = row['status'] or ('fresh' if age_hours <= 72 else 'stale')

                loaders.append({
                    'name': row['table_name'],
                    'table': row['table_name'],
                    'last_run': last_updated.isoformat() if last_updated else None,
                    'row_count': row['row_count'] or 0,
                    'latest_date': row['latest_date'].isoformat() if row['latest_date'] else None,
                    'status': status,
                    'age_hours': round(age_hours, 1),
                    'health': health,
                    'error': row['error_message'],
                })

            try:
                freshness = check_data_freshness(cur, 'data_loader_status', 'last_updated', warning_days=1)
            except Exception:
                freshness = None
            return json_response(200, {
                'status': 'ok',
                'loaders': loaders,
                'summary': {
                    'total': len(loaders),
                    'healthy': len([l for l in loaders if l['health'] == 'fresh']),
                    'stale': len([l for l in loaders if l['health'] == 'stale']),
                },
                'data_freshness': freshness
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

            cur.execute("SELECT date FROM price_daily ORDER BY date DESC LIMIT 1")
            last_price_date = next(iter(dict(cur.fetchone() or {}).values()), 0)
            if last_price_date:
                today = datetime.now(timezone.utc).date()
                age_days = (today - last_price_date).days
                # Use trading-day-aware freshness: data is fresh if it's from the most
                # recent trading day. A hardcoded day threshold causes false 'degraded'
                # on 3-day holiday weekends where Friday data is 4 calendar days old.
                try:
                    from algo.algo_market_calendar import MarketCalendar
                    expected = today - timedelta(days=1)
                    for _ in range(10):
                        if MarketCalendar.is_trading_day(expected):
                            break
                        expected -= timedelta(days=1)
                    is_fresh = last_price_date >= expected
                except Exception as e:
                    logger.warning(f"Exception: {e}")
                    is_fresh = age_days <= 3
                health_data['components']['data_freshness'] = 'ok' if is_fresh else 'stale'
                health_data['last_data_update'] = last_price_date.isoformat()
                if not is_fresh:
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

def _verify_user_email(body: Dict = None) -> Dict:
        """Verify a user's email in Cognito (dev/testing only)."""
        if not body or 'username' not in body:
            return error_response(400, 'bad_request', 'username required')

        try:
            cognito_user_pool_id = os.getenv('COGNITO_USER_POOL_ID', '').strip()
            cognito_region = os.getenv('COGNITO_REGION', 'us-east-1').strip()

            if not cognito_user_pool_id:
                return error_response(500, 'error', 'Cognito not configured')

            cognito_client = boto3.client('cognito-idp', region_name=cognito_region)
            username = body.get('username')

            # Update user attributes to mark email as verified
            cognito_client.admin_update_user_attributes(
                UserPoolId=cognito_user_pool_id,
                Username=username,
                UserAttributes=[
                    {'Name': 'email_verified', 'Value': 'true'}
                ]
            )

            logger.info(f"Email verified for user: {username}")
            return json_response(200, {
                'status': 'success',
                'message': f'Email verified for {username}',
                'username': username
            })
        except Exception as e:
            error_str = str(e)
            if 'UserNotFoundException' in error_str:
                return error_response(404, 'not_found', f'User not found: {body.get("username")}')
            logger.error(f"Failed to verify email: {e}")
            return error_response(500, 'error', f'Failed to verify email: {error_str}')
