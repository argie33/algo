#!/usr/bin/env python3
"""Monitor algo orchestrator execution - query RDS and Alpaca for results."""

import json
import os
import boto3
import psycopg2
import logging
from datetime import datetime, date
from psycopg2.extras import RealDictCursor

logger = logging.getLogger()
logger.setLevel(logging.INFO)

sm_client = boto3.client('secretsmanager', region_name='us-east-1')


def get_rds_credentials():
    """Get RDS credentials from Secrets Manager."""
    try:
        response = sm_client.get_secret_value(SecretId='algo-db-credentials-dev')
        secret = json.loads(response['SecretString'])
        return {
            'host': secret.get('host'),
            'port': secret.get('port', 5432),
            'user': secret.get('username', 'admin'),
            'password': secret.get('password'),
            'database': secret.get('dbname', 'algo'),
        }
    except Exception as e:
        logger.error(f"Failed to get RDS credentials: {e}")
        return None


def query_rds_signals(credentials):
    """Query RDS for today's signals."""
    if not credentials:
        return {'error': 'No RDS credentials'}

    try:
        conn = psycopg2.connect(**credentials, connect_timeout=5)
        with conn.cursor(cursor_factory=RealDictCursor) as cur:
            # Get signals generated today
            cur.execute("""
                SELECT
                    COUNT(*) as total,
                    COUNT(CASE WHEN signal_type = 'BUY' THEN 1 END) as buy,
                    COUNT(CASE WHEN signal_type = 'SELL' THEN 1 END) as sell,
                    COUNT(DISTINCT symbol) as symbols,
                    MAX(created_at) as latest_signal
                FROM buy_sell_daily
                WHERE DATE(created_at) = CURRENT_DATE
            """)
            signals = cur.fetchone()

            # Get recent signals
            cur.execute("""
                SELECT symbol, signal_type, price, confidence_score, created_at
                FROM buy_sell_daily
                WHERE DATE(created_at) = CURRENT_DATE
                ORDER BY created_at DESC
                LIMIT 10
            """)
            recent = cur.fetchall()

            conn.close()
            return {
                'summary': dict(signals) if signals else {},
                'recent_signals': [dict(r) for r in recent],
                'status': 'success'
            }
    except Exception as e:
        return {'error': str(e), 'status': 'failed'}


def get_alpaca_trades():
    """Get Alpaca trades (paper account)."""
    try:
        import alpaca_trade_api as tradeapi
    except ImportError:
        return {'error': 'alpaca_trade_api not installed', 'status': 'skipped'}

    try:
        api_key = os.getenv('APCA_API_KEY_ID')
        secret_key = os.getenv('APCA_API_SECRET_KEY')

        if not api_key or not secret_key:
            return {'error': 'Alpaca credentials not configured', 'status': 'skipped'}

        base_url = os.getenv('APCA_API_BASE_URL', 'https://paper-api.alpaca.markets')
        api = tradeapi.REST(api_key, secret_key, base_url=base_url)

        account = api.get_account()
        orders = api.list_orders(status='closed', limit=20)

        return {
            'account': {
                'status': account.status,
                'buying_power': float(account.buying_power),
                'portfolio_value': float(account.portfolio_value),
                'pnl': float(account.portfolio_value - account.cash),
            },
            'recent_trades': [
                {
                    'symbol': o.symbol,
                    'side': o.side,
                    'qty': float(o.qty),
                    'price': float(o.filled_avg_price) if o.filled_avg_price else None,
                    'status': o.status,
                    'filled_at': str(o.filled_at) if o.filled_at else None,
                }
                for o in orders[:10]
            ],
            'status': 'success'
        }
    except Exception as e:
        return {'error': str(e), 'status': 'failed'}


def lambda_handler(event, context):
    """Monitor execution status."""
    logger.info(f"Execution Monitor - {datetime.now().isoformat()}")

    rds_creds = get_rds_credentials()
    signals_result = query_rds_signals(rds_creds)
    trades_result = get_alpaca_trades()

    result = {
        'timestamp': datetime.now().isoformat(),
        'date': str(date.today()),
        'signals': signals_result,
        'trades': trades_result,
    }

    # Log summary
    logger.info(json.dumps(result, indent=2, default=str))

    return {
        'statusCode': 200,
        'body': json.dumps(result, default=str),
    }


if __name__ == '__main__':
    lambda_handler({}, {})
