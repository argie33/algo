"""
API Lambda handler for stock analytics platform.

Routes API Gateway requests to appropriate handlers.
"""

import json
import logging
import os
from typing import Dict, Any

import psycopg2
from psycopg2.extras import RealDictCursor

logger = logging.getLogger()
logger.setLevel(logging.INFO)


def get_db_connection():
    """Create database connection using environment variables."""
    try:
        db_secret_arn = os.getenv('DB_SECRET_ARN')
        db_endpoint = os.getenv('DB_ENDPOINT', 'algo-db.cojggi2mkthi.us-east-1.rds.amazonaws.com')
        db_name = os.getenv('DB_NAME', 'stocks')
        db_user = os.getenv('DB_USER', 'stocks')
        db_password = os.getenv('DB_PASSWORD')

        if db_secret_arn and not db_password:
            import boto3
            secrets_client = boto3.client('secretsmanager', region_name='us-east-1')
            try:
                secret_response = secrets_client.get_secret_value(SecretId=db_secret_arn)
                secret_dict = json.loads(secret_response['SecretString'])
                db_password = secret_dict.get('password')
                db_user = secret_dict.get('username', db_user)
            except Exception as e:
                logger.error(f'Failed to fetch secret: {e}')
                return None

        if not db_password:
            logger.error('No database password available')
            return None

        conn = psycopg2.connect(
            host=db_endpoint,
            port=5432,
            database=db_name,
            user=db_user,
            password=db_password,
            cursor_factory=RealDictCursor,
            connect_timeout=10
        )
        return conn
    except Exception as e:
        logger.error(f'Database connection error: {e}')
        return None


def json_response(status_code: int, body: Any, headers: Dict[str, str] = None) -> Dict:
    """Format response for API Gateway."""
    if headers is None:
        headers = {}

    headers.update({
        'Content-Type': 'application/json',
        'Access-Control-Allow-Origin': os.getenv('FRONTEND_ORIGIN', '*'),
        'Access-Control-Allow-Headers': 'Content-Type,Authorization',
        'Access-Control-Allow-Methods': 'GET,POST,PUT,DELETE,OPTIONS'
    })

    return {
        'statusCode': status_code,
        'headers': headers,
        'body': json.dumps(body) if not isinstance(body, str) else body
    }


def handle_health(event: Dict, context: Any) -> Dict:
    """GET /api/health - Health check endpoint."""
    try:
        conn = get_db_connection()
        if conn:
            cursor = conn.cursor()
            cursor.execute('SELECT 1')
            conn.close()
            return json_response(200, {'status': 'healthy', 'database': 'connected'})
        else:
            return json_response(503, {'status': 'unhealthy', 'database': 'disconnected'})
    except Exception as e:
        logger.error(f'Health check error: {e}')
        return json_response(503, {'status': 'unhealthy', 'error': str(e)})


def handle_metrics(event: Dict, context: Any) -> Dict:
    """GET /api/metrics - Get system metrics."""
    try:
        conn = get_db_connection()
        if not conn:
            return json_response(503, {'error': 'database_unavailable'})

        cursor = conn.cursor()

        cursor.execute('''
            SELECT
                (SELECT COUNT(*) FROM stock_symbols) as symbols,
                (SELECT COUNT(*) FROM price_daily) as prices,
                (SELECT COUNT(*) FROM algo_trades) as trades
        ''')
        row = cursor.fetchone()
        conn.close()

        metrics = {
            'data': {
                'stock_symbols': row['symbols'] if row else 0,
                'price_records': row['prices'] if row else 0,
                'algo_trades': row['trades'] if row else 0
            },
            'status': 'ok'
        }
        return json_response(200, metrics)
    except Exception as e:
        logger.error(f'Metrics error: {e}')
        return json_response(500, {'error': str(e)})


def handle_not_found(event: Dict, context: Any) -> Dict:
    """Handle undefined routes."""
    path = event.get('path', 'unknown')
    return json_response(404, {'error': 'not_found', 'path': path})


def route_request(event: Dict, context: Any) -> Dict:
    """Route API requests to appropriate handlers."""
    path = event.get('path', '')
    method = event.get('httpMethod', 'GET')

    logger.info(f'{method} {path}')

    if method == 'OPTIONS':
        return json_response(200, {})

    if path == '/api/health':
        return handle_health(event, context)
    elif path == '/api/metrics':
        return handle_metrics(event, context)
    else:
        return handle_not_found(event, context)


def lambda_handler(event: Dict, context: Any) -> Dict:
    """Main Lambda handler for API Gateway proxy integration."""
    try:
        logger.info(f'Event: {json.dumps(event)}')
        return route_request(event, context)
    except Exception as e:
        logger.error(f'Unhandled error: {e}', exc_info=True)
        return json_response(500, {'error': 'internal_server_error', 'message': str(e)})
