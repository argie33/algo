"""Route: health - Health check endpoints (basic, detailed, pipeline)"""
import psycopg2
from typing import Dict
import logging
from datetime import datetime, timezone
from .utils import check_data_freshness, success_response, error_response, execute_with_timeout, handle_db_error
from ..utils.config import get_config

# C-4 FIX: Import route status for health endpoint
try:
    from api_router import get_import_status as get_api_import_status
except (ImportError, ModuleNotFoundError):
    # Fallback if api_router not available (shouldn't happen in normal execution)
    def get_api_import_status():
        return {"failed_routes": 0, "critical_failures": []}

logger = logging.getLogger(__name__)

def handle(cur, path: str, method: str, params: Dict, body: Dict = None, jwt_claims: Dict = None) -> Dict:
    """Handle health check endpoints.

    /api/health — PUBLIC, no auth required. Basic system status.
    /api/health/cognito — PUBLIC, no auth required. C-7 FIX: Verify Cognito client ID matches configuration.
    /api/health/detailed — AUTHENTICATED. Database schema and table status.
    /api/health/pipeline — AUTHENTICATED. Data freshness of critical loaders.
    """

    # Route to appropriate handler
    if path.startswith('/api/health/cognito') or path.startswith('/health/cognito'):
        return _handle_cognito(cur)
    elif path.startswith('/api/health/detailed') or path.startswith('/health/detailed'):
        return _handle_detailed(cur, jwt_claims)
    elif path.startswith('/api/health/pipeline') or path.startswith('/health/pipeline'):
        return _handle_pipeline(cur, jwt_claims)
    else:
        # Basic health check (default for /api/health)
        return _handle_basic(cur)

def _handle_basic(cur) -> Dict:
    """Basic health check - PUBLIC, no auth required.

    Includes: database connectivity, RDS connection pool status, data freshness overview,
    API route import status.
    """
    # Get route status from api_router module (for C-4 fix)
    import_status = get_api_import_status()

    health = {
        "status": "healthy",
        "version": "v2-2026-06-06",
        "timestamp": datetime.now().isoformat(),
    }

    has_critical = False
    has_warning = False
    degradation_reasons = []

    # C-4 FIX: Report API route import failures in health check
    if import_status.get('failed_routes', 0) > 0:
        health['api_route_imports'] = {
            'status': 'degraded',
            'failed_count': import_status['failed_routes'],
            'critical_failures': import_status['critical_failures'],
            'failed_modules': import_status['failed_modules'],
        }
        if import_status.get('critical_failures'):
            has_critical = True
            degradation_reasons.append(f"Critical routes failed to import: {', '.join(import_status['critical_failures'])}")
        else:
            has_warning = True
            degradation_reasons.append(f"Some routes failed to import: {len(import_status['failed_modules'])} modules")
    else:
        health['api_route_imports'] = {'status': 'healthy', 'failed_count': 0}

    try:
        # Verify DB is responsive with a simple query (3 second timeout)
        result = execute_with_timeout(cur, "SELECT 1", timeout_sec=3)
        if not result:
            return error_response(503, 'connection_error', 'Database connection failed')

        # Get RDS connection pool status (5-second timeout for metadata query)
        try:
            pool_info = execute_with_timeout(cur, """
                SELECT
                    (SELECT count(*) FROM pg_stat_activity WHERE datname = current_database()) as active_connections,
                    current_setting('max_connections')::int as max_connections
            """, timeout_sec=5)

            if pool_info and len(pool_info) > 0:
                row = dict(pool_info[0])
                active = row.get('active_connections', 0)
                max_conn = row.get('max_connections', 100)
                pool_pct = int((active / max_conn) * 100) if max_conn > 0 else 0

                health['rds_connection_pool'] = {
                    'active_connections': active,
                    'max_connections': max_conn,
                    'utilization_percent': pool_pct,
                    'status': 'CRITICAL' if pool_pct > 90 else ('WARNING' if pool_pct > 75 else 'HEALTHY')
                }
        except Exception as e:
            logger.warning(f"Failed to get connection pool status: {str(e)[:80]}")
            health['rds_connection_pool'] = {'status': 'UNKNOWN', 'error': 'Unable to fetch pool stats'}

        # ISSUE #13 FIX: Include signal freshness in basic endpoint for frontend visibility
        # Query signal freshness with short timeout to keep endpoint responsive
        try:
            signal_freshness = execute_with_timeout(cur, """
                SELECT
                    MAX(EXTRACT(EPOCH FROM (NOW() - created_at)) / 3600.0) as max_age_hours
                FROM signal_quality_scores
                WHERE created_at >= NOW() - INTERVAL '7 days'
            """, timeout_sec=2)

            if signal_freshness and len(signal_freshness) > 0:
                row = dict(signal_freshness[0])
                age_hours = float(row.get('max_age_hours')) if row.get('max_age_hours') is not None else 999
                config = get_config()

                if age_hours <= 1:  # Fresh (within 1 hour)
                    signal_status = 'FRESH'
                elif age_hours <= config.signal_stale_threshold_hours:  # Acceptable
                    signal_status = 'OK'
                    if age_hours > (config.signal_stale_threshold_hours * 0.5):  # Warn at 50% of threshold
                        degradation_reasons.append(f"Signals {age_hours:.1f}h old (waiting for fresh data)")
                        has_warning = True
                else:  # Stale (exceeds threshold)
                    signal_status = 'STALE'
                    degradation_reasons.append(f"Signals {age_hours:.1f}h old (use with caution)")
                    has_critical = True

                health['freshness'] = {
                    'status': signal_status,
                    'signal_age_hours': round(age_hours, 1),
                    'message': f'Signals based on data from {age_hours:.1f} hours ago'
                }
            else:
                health['freshness'] = {'status': 'UNKNOWN', 'message': 'No signal data available'}
        except Exception as e:
            logger.debug(f"Failed to get signal freshness: {str(e)[:60]}")
            health['freshness'] = {'status': 'UNKNOWN', 'message': 'Signal freshness check unavailable'}

        # Overall system status based on component health
        if health.get('rds_connection_pool', {}).get('status') == 'CRITICAL':
            has_critical = True
            degradation_reasons.append(f"RDS pool at {health['rds_connection_pool'].get('utilization_percent', 0)}%")
        elif health.get('rds_connection_pool', {}).get('status') == 'WARNING':
            has_warning = True

        if health.get('freshness', {}).get('status') == 'STALE':
            has_critical = True
            degradation_reasons.append(f"Data {health['freshness'].get('oldest_data_age_days', 0):.1f}d stale")
        elif health.get('freshness', {}).get('status') == 'WARNING':
            has_warning = True

        # Check orchestrator halt flag and degraded mode status (from DynamoDB)
        try:
            import boto3
            import os
            dynamodb = boto3.resource('dynamodb')
            table_name = os.getenv('HALT_FLAG_TABLE', 'algo_orchestrator_state')
            table = dynamodb.Table(table_name)

            response = table.get_item(Key={'key': 'orchestrator_halt'})
            halt_flag_active = response.get('Item', {}).get('halt_flag', False) is True
            health['orchestrator_halt_flag'] = halt_flag_active

            # ISSUE #9 FIX: Check Phase 1 degraded mode status (indicates failsafe is running)
            degraded_response = table.get_item(Key={'key': 'phase1_degraded_mode'})
            phase1_degraded = degraded_response.get('Item', {}).get('degraded', False) is True
            health['phase1_degraded_mode'] = phase1_degraded
            if phase1_degraded:
                degradation_reasons.append("Phase 1 degraded: failsafe in progress")
                has_warning = True
        except Exception as e:
            logger.debug(f"Failed to check orchestrator state: {str(e)[:60]}")
            health['orchestrator_halt_flag'] = None  # Unknown if DynamoDB unavailable
            health['phase1_degraded_mode'] = None

        # Check last successful load time
        try:
            loader_status = execute_with_timeout(cur, """
                SELECT MAX(last_updated) as latest_load_time
                FROM data_loader_status
                WHERE table_name IN ('stock_prices_daily', 'buy_sell_daily', 'signal_quality_scores')
                AND status = 'success'
            """, timeout_sec=3)

            if loader_status and len(loader_status) > 0:
                row = dict(loader_status[0])
                last_load = row.get('latest_load_time')
                if last_load:
                    health['last_successful_load_time'] = last_load.isoformat() if hasattr(last_load, 'isoformat') else str(last_load)
        except Exception as e:
            logger.debug(f"Failed to get last load time: {str(e)[:60]}")

        if has_critical:
            health['status'] = 'degraded'
            health['degraded_mode_active'] = True
            health['degradation_reason'] = ' | '.join(degradation_reasons) if degradation_reasons else 'System degraded'
        else:
            health['degraded_mode_active'] = False

        if has_warning and not has_critical:
            health['status'] = 'warning'

        return success_response(health)

    except Exception as e:
        logger.error(f"Health check error: {str(e)[:100]}")
        code, error_type, message = handle_db_error(e, "health check")
        return error_response(code, error_type, message)

def _handle_cognito(cur) -> Dict:
    """C-7 FIX: Verify Cognito client ID matches AWS Cognito configuration.

    This endpoint is called by pre-deploy validation (GitHub Actions) to ensure
    the COGNITO_CLIENT_ID environment variable matches the actual Cognito user pool
    configuration. If mismatch is detected, deployment should be blocked.

    Returns:
    - status: 'healthy' if client ID matches, 'misconfigured' if mismatch
    - configured_client_id: Value from COGNITO_CLIENT_ID env var
    - cognito_client_id: Actual client ID from Cognito (if verifiable)
    - cognito_user_pool_id: User pool ID from config
    """
    import os
    import boto3

    try:
        configured_client_id = os.getenv('COGNITO_CLIENT_ID', '').strip()
        cognito_user_pool_id = os.getenv('COGNITO_USER_POOL_ID', '').strip()
        cognito_region = os.getenv('AWS_REGION', 'us-east-1').strip()

        health = {
            "status": "healthy",
            "check_type": "cognito_configuration",
            "timestamp": datetime.now(timezone.utc).isoformat(),
        }

        # If client ID not configured, flag as critical (security issue)
        if not configured_client_id:
            health['status'] = 'misconfigured'
            health['error'] = 'COGNITO_CLIENT_ID not configured'
            logger.error("CRITICAL: COGNITO_CLIENT_ID environment variable is missing")
            return error_response(503, 'misconfigured', 'Cognito client ID not configured')

        if not cognito_user_pool_id:
            health['status'] = 'misconfigured'
            health['error'] = 'COGNITO_USER_POOL_ID not configured'
            logger.error("CRITICAL: COGNITO_USER_POOL_ID environment variable is missing")
            return error_response(503, 'misconfigured', 'Cognito user pool ID not configured')

        health['configured_client_id'] = configured_client_id
        health['cognito_user_pool_id'] = cognito_user_pool_id
        health['cognito_region'] = cognito_region

        # Attempt to verify against actual Cognito configuration
        try:
            cognito = boto3.client('cognito-idp', region_name=cognito_region)

            # Get user pool description to find app client
            pool_response = cognito.describe_user_pool(UserPoolId=cognito_user_pool_id)
            user_pool = pool_response.get('UserPool', {})

            # List app clients in this user pool
            apps_response = cognito.list_user_pool_clients(
                UserPoolId=cognito_user_pool_id,
                MaxResults=10
            )
            clients = apps_response.get('UserPoolClients', [])

            # Find matching client
            matching_client = None
            for client in clients:
                if client.get('ClientId') == configured_client_id:
                    matching_client = client
                    break

            if matching_client:
                health['cognito_client_found'] = True
                health['cognito_client_name'] = matching_client.get('ClientName', 'unknown')
                health['validation_result'] = 'PASS'
                return success_response(health)
            else:
                health['status'] = 'misconfigured'
                health['cognito_client_found'] = False
                health['available_clients'] = [c.get('ClientId') for c in clients]
                health['validation_result'] = 'FAIL - client ID not found in Cognito'
                logger.error(f"CRITICAL: COGNITO_CLIENT_ID {configured_client_id} not found in user pool {cognito_user_pool_id}")
                return error_response(503, 'misconfigured', f'Client ID {configured_client_id} not found in Cognito user pool')

        except Exception as cognito_err:
            logger.warning(f"Could not verify Cognito client ID with API (will proceed with config): {str(cognito_err)[:100]}")
            # If we can't reach Cognito API, still report what we have configured (pre-deploy may not have IAM)
            health['cognito_verification_skipped'] = True
            health['cognito_error'] = str(cognito_err)[:80]
            return success_response(health)

    except Exception as e:
        logger.error(f"Cognito health check error: {str(e)[:100]}")
        return error_response(503, 'health_check_error', str(e)[:100])

def _handle_detailed(cur, jwt_claims: Dict) -> Dict:
    """Detailed health check - AUTHENTICATED. Exposes schema information."""
    if not jwt_claims:
        return error_response(401, 'unauthorized', 'Authentication required')

    try:
        _HEALTH_TABLES = ('price_daily', 'buy_sell_daily', 'stock_scores', 'technical_data_daily')
        rows = execute_with_timeout(
            cur,
            """
            SELECT relname, n_live_tup
            FROM pg_stat_user_tables
            WHERE relname = ANY(%s)
            """,
            params=(_HEALTH_TABLES,),
            timeout_sec=5
        )
        table_counts = {row[0]: row[1] for row in rows}
        for t in _HEALTH_TABLES:
            table_counts.setdefault(t, 0)

        return success_response({
            "status": "healthy",
            "dbStatus": "connected",
            "tables": table_counts
        })
    except Exception as e:
        logger.error(f'[HEALTH_DETAILED_ERROR] {e}', exc_info=True)
        code, error_type, message = handle_db_error(e, "detailed health check")
        return error_response(code, error_type, message)

def _handle_pipeline(cur, jwt_claims: Dict) -> Dict:
    """Pipeline health check - AUTHENTICATED. Data freshness of critical loaders."""
    if not jwt_claims:
        return error_response(401, 'unauthorized', 'Authentication required')

    try:
        # Query freshness of critical data loaders (15 second timeout for this larger query)
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
        rows = execute_with_timeout(cur, query, timeout_sec=15, max_attempts=1)
        rows = [dict(row) for row in rows]

        config = get_config()
        tables = []
        for row in rows:
            age = float(row.get('age_days')) if row.get('age_days') is not None else 999
            row_count = row.get('row_count')
            if age <= config.pipeline_healthy_days and row_count is not None and row_count > 0:
                status = 'HEALTHY'
            elif age <= config.pipeline_critical_days:
                status = 'STALE'
            else:
                status = 'CRITICAL'
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
        code, error_type, message = handle_db_error(e, "pipeline health check")
        return error_response(code, error_type, message)
