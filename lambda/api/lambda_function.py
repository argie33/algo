"""Stock Analytics Platform - API Lambda Handler.

Routes requests to extracted handler modules via api_router.
"""

import os
import json
import logging
from typing import Dict, Any
import psycopg2
from psycopg2.extras import RealDictCursor

import api_router

logger = logging.getLogger()
logger.setLevel(logging.INFO)

_db_conn = None


def get_db_connection():
    """Get or create database connection."""
    global _db_conn
    if _db_conn and not _db_conn.closed:
        return _db_conn

    try:
        db_secret_arn = os.getenv('DB_SECRET_ARN')
        db_host = os.getenv('DB_HOST', 'algo-db.cojggi2mkthi.us-east-1.rds.amazonaws.com')
        db_port = int(os.getenv('DB_PORT', '5432'))
        db_name = os.getenv('DB_NAME', 'stocks')
        db_user = os.getenv('DB_USER', 'stocks')
        db_password = os.getenv('DB_PASSWORD')

        if db_secret_arn and not db_password:
            import boto3
            secrets = boto3.client('secretsmanager', region_name='us-east-1')
            response = secrets.get_secret_value(SecretId=db_secret_arn)
            secret = json.loads(response['SecretString'])
            db_password = secret.get('password')
            db_user = secret.get('username', db_user)

        if not db_password:
            logger.error('No database password')
            return None

        _db_conn = psycopg2.connect(
            host=db_host,
            port=db_port,
            database=db_name,
            user=db_user,
            password=db_password,
            cursor_factory=RealDictCursor,
            connect_timeout=10
        )
        return _db_conn
    except Exception as e:
        logger.error(f'DB connection failed: {e}')
        return None


def parse_query_params(event: Dict) -> Dict:
    """Parse query parameters from API Gateway v1 or v2 events."""
    params = {}
    # Try v1 format first (REST API)
    if 'queryStringParameters' in event and event['queryStringParameters']:
        for k, v in event['queryStringParameters'].items():
            params[k] = [v] if v else []
    # If no v1 params, try v2 format (HTTP API with rawQueryString)
    elif 'rawQueryString' in event and event['rawQueryString']:
        for param in event['rawQueryString'].split('&'):
            if '=' in param:
                k, v = param.split('=', 1)
                params[k] = params.get(k, []) + [v]
            else:
                params[param] = ['']
    return params


def get_cors_headers(event: Dict) -> Dict[str, str]:
    """Get CORS headers based on request origin (whitelist only)."""
    origin = event.get('headers', {}).get('origin', '') or event.get('headers', {}).get('Origin', '')

    # Whitelist of allowed origins
    ALLOWED_ORIGINS = {
        'https://edgebrooke.example.com',
        'https://dashboard.example.com',
        'http://localhost:5173',
        'http://localhost:3000',
    }

    if origin in ALLOWED_ORIGINS:
        return {
            'Access-Control-Allow-Origin': origin,
            'Access-Control-Allow-Credentials': 'true',
        }

    # Reject cross-origin requests from unknown sources
    return {
        'Access-Control-Allow-Origin': 'null',
    }


def get_security_headers() -> Dict[str, str]:
    """Return security headers for all responses."""
    return {
        'Strict-Transport-Security': 'max-age=31536000; includeSubDomains; preload',
        'X-Content-Type-Options': 'nosniff',
        'X-Frame-Options': 'DENY',
        'X-XSS-Protection': '1; mode=block',
        'Referrer-Policy': 'strict-origin-when-cross-origin',
        'Permissions-Policy': 'geolocation=(), microphone=(), camera=()',
    }


def lambda_handler(event: Dict[str, Any], context: Any) -> Dict[str, Any]:
    """Handle API Gateway v2 (HTTP API) requests by routing to extracted handler modules."""
    try:
        # API Gateway v2 (HTTP API) uses rawPath and requestContext.http.method
        path = event.get('rawPath', event.get('path', '/'))
        method = event.get('requestContext', {}).get('http', {}).get('method', event.get('httpMethod', 'GET'))
        logger.info(f'Request: {method} {path}')

        # Health check
        if path in ['/health', '/api/health']:
            return {
                'statusCode': 200,
                'headers': {'Content-Type': 'application/json', 'Access-Control-Allow-Origin': '*'},
                'body': json.dumps({'status': 'healthy'})
            }

        # Detailed health check
        if path in ['/health/detailed', '/api/health/detailed']:
            try:
                conn = get_db_connection()
                if not conn:
                    return {
                        'statusCode': 503,
                        'headers': {'Content-Type': 'application/json', 'Access-Control-Allow-Origin': '*'},
                        'body': json.dumps({'status': 'unhealthy', 'dbStatus': 'disconnected'})
                    }

                cur = conn.cursor()
                # Get table counts (whitelist prevents SQL injection)
                ALLOWED_TABLES = {'price_daily', 'signals', 'stock_scores', 'technical_data_daily'}
                table_counts = {}
                for table in ALLOWED_TABLES:
                    try:
                        cur.execute(f'SELECT COUNT(*) FROM "{table}"')
                        table_counts[table] = cur.fetchone()[0]
                    except:
                        table_counts[table] = 0
                cur.close()

                return {
                    'statusCode': 200,
                    'headers': {'Content-Type': 'application/json', 'Access-Control-Allow-Origin': '*'},
                    'body': json.dumps({'status': 'healthy', 'dbStatus': 'connected', 'tables': table_counts})
                }
            except Exception as e:
                return {
                    'statusCode': 503,
                    'headers': {'Content-Type': 'application/json', 'Access-Control-Allow-Origin': '*'},
                    'body': json.dumps({'status': 'unhealthy', 'error': str(e)})
                }

        # Pipeline health — queries data_loader_status for all table freshness
        if path in ['/health/pipeline', '/api/health/pipeline']:
            try:
                conn = get_db_connection()
                if not conn:
                    return {
                        'statusCode': 503,
                        'headers': {'Content-Type': 'application/json', 'Access-Control-Allow-Origin': '*'},
                        'body': json.dumps({'status': 'unhealthy', 'error': 'db_unavailable'})
                    }
                cur = conn.cursor()
                try:
                    cur.execute("""
                        SELECT table_name, row_count, last_updated,
                               EXTRACT(EPOCH FROM (NOW() - last_updated)) / 86400 AS age_days
                        FROM data_loader_status ORDER BY table_name
                    """)
                    rows = cur.fetchall()
                except Exception:
                    rows = []
                tables = []
                for row in rows:
                    age = float(row['age_days']) if row.get('age_days') is not None else 999
                    status = 'HEALTHY' if age <= 2 and (row.get('row_count') or 0) > 0 else ('STALE' if age <= 7 else 'CRITICAL')
                    tables.append({'table_name': row['table_name'], 'row_count': row.get('row_count', 0), 'age_days': round(age, 1), 'status': status})
                healthy = sum(1 for t in tables if t['status'] == 'HEALTHY')
                cur.close()
                return {
                    'statusCode': 200,
                    'headers': {'Content-Type': 'application/json', 'Access-Control-Allow-Origin': '*'},
                    'body': json.dumps({'status': 'HEALTHY' if healthy == len(tables) and tables else 'DEGRADED', 'healthy_count': healthy, 'total_count': len(tables), 'tables': tables})
                }
            except Exception as e:
                return {
                    'statusCode': 500,
                    'headers': {'Content-Type': 'application/json', 'Access-Control-Allow-Origin': '*'},
                    'body': json.dumps({'status': 'error', 'error': str(e)})
                }

        # CORS preflight
        if method == 'OPTIONS':
            return {
                'statusCode': 200,
                'headers': {
                    'Access-Control-Allow-Origin': '*',
                    'Access-Control-Allow-Methods': 'GET,POST,PATCH,DELETE,OPTIONS',
                    'Access-Control-Allow-Headers': 'Content-Type,Authorization'
                }
            }

        conn = get_db_connection()
        if not conn:
            return {
                'statusCode': 503,
                'headers': {'Content-Type': 'application/json', 'Access-Control-Allow-Origin': '*'},
                'body': json.dumps({'error': 'database_unavailable'})
            }

        # Reset any failed transaction state from a previous Lambda invocation
        try:
            conn.rollback()
        except Exception:
            _db_conn = None
            conn = get_db_connection()
            if not conn:
                return {
                    'statusCode': 503,
                    'headers': {'Content-Type': 'application/json', 'Access-Control-Allow-Origin': '*'},
                    'body': json.dumps({'error': 'database_unavailable'})
                }

        cur = conn.cursor()

        params = parse_query_params(event)
        body = None
        if event.get('body'):
            try:
                body = json.loads(event['body'])
            except:
                pass

        # Route request to appropriate handler
        response = api_router.route_request(cur, path, method, params, body)
        cur.close()

        # Ensure response has proper format
        def _json_default(obj):
            import datetime
            if isinstance(obj, (datetime.date, datetime.datetime)):
                return obj.isoformat()
            if hasattr(obj, '__float__'):
                return float(obj)
            return str(obj)

        if isinstance(response, dict):
            status = response.get('statusCode', 200)
            headers = {'Content-Type': 'application/json', 'Access-Control-Allow-Origin': '*'}
            if 'body' in response:
                body = response['body'] if isinstance(response['body'], str) else json.dumps(response['body'], default=_json_default)
            else:
                # Route handlers return data dicts directly (no body key) — wrap them
                body = json.dumps({k: v for k, v in response.items() if k != 'statusCode'}, default=_json_default)
            return {'statusCode': status, 'headers': headers, 'body': body}

        return {
            'statusCode': 500,
            'headers': {'Content-Type': 'application/json', 'Access-Control-Allow-Origin': '*'},
            'body': json.dumps({'error': 'invalid_response'})
        }

    except Exception as e:
        logger.error(f'Error: {e}', exc_info=True)
        return {
            'statusCode': 500,
            'headers': {'Content-Type': 'application/json', 'Access-Control-Allow-Origin': '*'},
            'body': json.dumps({'error': 'internal_server_error'})
        }

