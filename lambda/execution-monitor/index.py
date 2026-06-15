#!/usr/bin/env python3
"""Monitor algo orchestrator execution - query RDS and Alpaca for results."""

import json
import os
import psycopg2
import logging
import sys
from datetime import datetime, date, timezone
from pathlib import Path
from psycopg2.extras import RealDictCursor

logger = logging.getLogger()
logger.setLevel(logging.INFO)

# Lambda layer path and project root
if os.path.exists("/opt/python"):
    sys.path.insert(0, "/opt/python")
sys.path.insert(0, str(Path(__file__).parent.parent.parent))

def get_rds_credentials():
    """Get RDS credentials from credential_manager."""
    try:
        from config.credential_manager import get_db_credentials

        return get_db_credentials()
    except Exception as e:
        logger.error(f"Failed to get RDS credentials: {e}")
        return None

def query_rds_signals(credentials):
    """Query RDS for today's signals."""
    if not credentials:
        return {"error": "No RDS credentials"}

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
                "summary": dict(signals) if signals else {},
                "recent_signals": [dict(r) for r in recent],
                "status": "success",
            }
    except Exception as e:
        return {"error": str(e), "status": "failed"}

def get_alpaca_credentials():
    """Get Alpaca credentials from credential_manager."""
    from config.alpaca_config import get_alpaca_base_url
    from config.credential_manager import get_alpaca_credentials as get_alpaca_creds

    base_url = get_alpaca_base_url()

    try:
        creds = get_alpaca_creds()
        return {
            "api_key": creds.get("key"),
            "secret_key": creds.get("secret"),
            "base_url": base_url,
        }
    except Exception as e:
        logger.error(f"Failed to get Alpaca credentials: {e}")
        return {
            "api_key": None,
            "secret_key": None,
            "base_url": base_url,
        }

def get_alpaca_trades():
    """Get Alpaca trades (paper account)."""
    try:
        import alpaca_trade_api as tradeapi
    except ImportError as e:
        error_msg = f"FATAL: alpaca_trade_api not installed in Lambda layer. Install via requirements.txt. Error: {e}"
        logger.error(error_msg)
        return {"error": error_msg, "status": "failed"}

    try:
        # FIXED Issue #21: Use credential_manager pattern for Alpaca credentials
        creds = get_alpaca_credentials()
        api_key = creds.get("api_key")
        secret_key = creds.get("secret_key")
        base_url = creds.get("base_url")

        if not api_key or not secret_key:
            error_msg = "Alpaca credentials not configured (check AWS Secrets Manager and ALPACA_SECRET_ARN env var)"
            logger.error(error_msg)
            return {"error": error_msg, "status": "failed"}

        api = tradeapi.REST(api_key, secret_key, base_url=base_url)

        account = api.get_account()
        orders = api.list_orders(status="closed", limit=20)

        return {
            "account": {
                "status": account.status,
                "buying_power": float(account.buying_power),
                "portfolio_value": float(account.portfolio_value),
                "pnl": float(account.portfolio_value - account.cash),
            },
            "recent_trades": [
                {
                    "symbol": o.symbol,
                    "side": o.side,
                    "qty": float(o.qty),
                    "price": float(o.filled_avg_price) if o.filled_avg_price else None,
                    "status": o.status,
                    "filled_at": str(o.filled_at) if o.filled_at else None,
                }
                for o in orders[:10]
            ],
            "status": "success",
        }
    except Exception as e:
        return {"error": str(e), "status": "failed"}

def lambda_handler(event, context):
    """Monitor execution status."""

    logger.info(f"Execution Monitor - {datetime.now(timezone.utc).isoformat()}")

    rds_creds = get_rds_credentials()
    signals_result = query_rds_signals(rds_creds)
    trades_result = get_alpaca_trades()

    result = {
        "timestamp": datetime.now(timezone.utc).isoformat(),
        "date": str(date.today()),
        "signals": signals_result,
        "trades": trades_result,
    }

    # Log summary
    logger.info(json.dumps(result, indent=2, default=str))

    return {
        "statusCode": 200,
        "body": json.dumps(result, default=str),
    }

if __name__ == "__main__":
    lambda_handler({}, {})
