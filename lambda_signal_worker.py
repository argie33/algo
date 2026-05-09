#!/usr/bin/env python3
"""
Lambda Worker for Processing Single Symbol or Batch via Step Functions Map

This worker is invoked once per symbol (or batch) by the Step Functions Map state.
It computes buy/sell signals for that symbol and returns results.

Invocation via Step Functions Map:
{
  "symbol": "AAPL",
  "backfill_days": 30
}

Response:
{
  "symbol": "AAPL",
  "status": "success",
  "rows_inserted": 150,
  "duration_ms": 1234,
  "error": null
}
"""

import json
import logging
import os
import sys
import time
from datetime import date, timedelta
from typing import Dict, Optional

logger = logging.getLogger()
logger.setLevel(logging.INFO)


def get_db_connection():
    """Get RDS database connection from Secrets Manager"""
    import boto3
    import psycopg2

    try:
        secrets_client = boto3.client('secretsmanager')
        secret_name = os.environ.get('RDS_SECRET_ARN', 'stocks-prod-postgres-creds')

        try:
            secret_response = secrets_client.get_secret_value(SecretId=secret_name)
            secret = json.loads(secret_response['SecretString'])
        except Exception:
            secret = {
                'host': os.environ.get('DB_HOST', 'localhost'),
                'port': int(os.environ.get('DB_PORT', '5432')),
                'user': os.environ.get('DB_USER', 'stocks'),
                'password': os.environ.get('DB_PASSWORD', ''),
                'dbname': os.environ.get('DB_NAME', 'stocks')
            }

        conn = psycopg2.connect(
            host=secret.get('host'),
            port=secret.get('port', 5432),
            user=secret.get('username', secret.get('user')),
            password=secret.get('password'),
            database=secret.get('dbname', secret.get('name'))
        )
        return conn
    except Exception as e:
        logger.exception(f"Failed to connect to database: {e}")
        raise


def fetch_price_data(conn, symbol: str, start: date, end: date) -> list:
    """Fetch price data for symbol"""
    try:
        cur = conn.cursor()
        cur.execute(
            """
            SELECT date, open, high, low, close, volume
            FROM price_daily
            WHERE symbol = %s AND date >= %s AND date <= %s
            ORDER BY date ASC
            """,
            (symbol, start, end)
        )
        rows = cur.fetchall()
        cur.close()

        return [
            {
                "date": r[0].isoformat() if r[0] else None,
                "open": float(r[1]) if r[1] is not None else None,
                "high": float(r[2]) if r[2] is not None else None,
                "low": float(r[3]) if r[3] is not None else None,
                "close": float(r[4]) if r[4] is not None else None,
                "volume": int(r[5]) if r[5] is not None else None,
            }
            for r in rows
        ]
    except Exception as e:
        logger.exception(f"Error fetching price data for {symbol}: {e}")
        return []


def compute_signals(symbol: str, price_rows: list) -> Optional[list]:
    """Compute buy/sell signals from price data"""
    if len(price_rows) < 50:
        return None

    try:
        import pandas as pd
        import numpy as np

        df = pd.DataFrame(price_rows)
        if not all(c in df.columns for c in ["close", "high", "low"]):
            return None

        df["close"] = pd.to_numeric(df["close"], errors="coerce")
        df["high"] = pd.to_numeric(df["high"], errors="coerce")
        df["low"] = pd.to_numeric(df["low"], errors="coerce")
        df = df.dropna(subset=["close"]).reset_index(drop=True)

        if len(df) < 50:
            return None

        # Compute indicators
        df["rsi"] = compute_rsi(df["close"], 14)
        df["sma_50"] = df["close"].rolling(50).mean()
        df["sma_200"] = df["close"].rolling(200).mean()
        df["atr"] = compute_atr(df["high"], df["low"], df["close"], 14)

        # Generate signals (simplified)
        signals = []
        for idx, row in df.iterrows():
            if pd.isna(row.get("rsi")) or pd.isna(row.get("sma_50")):
                continue

            signal_type = None
            if row["rsi"] < 30 and row["sma_50"] > row["sma_200"]:
                signal_type = "BUY"
            elif row["rsi"] > 70 and row["sma_50"] < row["sma_200"]:
                signal_type = "SELL"

            if signal_type:
                signals.append({
                    "symbol": symbol,
                    "date": row["date"],
                    "signal_type": signal_type,
                    "rsi": float(row["rsi"]),
                    "sma_50": float(row["sma_50"]),
                    "sma_200": float(row["sma_200"]),
                    "close": float(row["close"])
                })

        return signals if signals else None
    except Exception as e:
        logger.exception(f"Error computing signals for {symbol}: {e}")
        return None


def compute_rsi(closes, period=14):
    """Compute Relative Strength Index"""
    deltas = closes.diff()
    gains = (deltas.where(deltas > 0, 0)).rolling(window=period).mean()
    losses = (-deltas.where(deltas < 0, 0)).rolling(window=period).mean()
    rs = gains / losses
    return 100 - (100 / (1 + rs))


def compute_atr(highs, lows, closes, period=14):
    """Compute Average True Range"""
    tr1 = highs - lows
    tr2 = abs(highs - closes.shift())
    tr3 = abs(lows - closes.shift())
    tr = pd.concat([tr1, tr2, tr3], axis=1).max(axis=1)
    return tr.rolling(period).mean()


def insert_signals(conn, signals: list) -> int:
    """Insert signals into database"""
    try:
        cur = conn.cursor()
        rows_inserted = 0

        for signal in signals:
            cur.execute(
                """
                INSERT INTO buy_sell_daily
                (symbol, timeframe, date, signal_type, rsi, sma_50, sma_200, close, created_at)
                VALUES (%s, %s, %s, %s, %s, %s, %s, %s, NOW())
                ON CONFLICT (symbol, timeframe, date) DO UPDATE SET
                    signal_type = EXCLUDED.signal_type,
                    rsi = EXCLUDED.rsi,
                    sma_50 = EXCLUDED.sma_50,
                    sma_200 = EXCLUDED.sma_200,
                    close = EXCLUDED.close
                """,
                (
                    signal["symbol"],
                    "Daily",
                    signal["date"],
                    signal["signal_type"],
                    signal.get("rsi"),
                    signal.get("sma_50"),
                    signal.get("sma_200"),
                    signal.get("close")
                )
            )
            rows_inserted += 1

        conn.commit()
        cur.close()
        return rows_inserted
    except Exception as e:
        logger.exception(f"Error inserting signals: {e}")
        conn.rollback()
        return 0


def lambda_handler(event, context) -> Dict:
    """
    Lambda handler for processing a single symbol via Step Functions Map state.

    Input event:
    {
        "symbol": "AAPL",
        "backfill_days": 30
    }

    Output:
    {
        "symbol": "AAPL",
        "status": "success",
        "rows_inserted": 150,
        "duration_ms": 1234
    }
    """
    start_time = time.time()

    try:
        symbol = event.get('symbol')
        backfill_days = event.get('backfill_days', 30)

        if not symbol:
            return {
                'symbol': 'unknown',
                'status': 'error',
                'error': 'Missing symbol in event',
                'duration_ms': int((time.time() - start_time) * 1000)
            }

        logger.info(f"Processing symbol: {symbol}")

        # Get database connection
        conn = get_db_connection()

        try:
            # Fetch price data
            end = date.today()
            start = end - timedelta(days=backfill_days)
            price_rows = fetch_price_data(conn, symbol, start, end)

            if not price_rows:
                logger.warning(f"No price data found for {symbol}")
                return {
                    'symbol': symbol,
                    'status': 'no_data',
                    'rows_inserted': 0,
                    'duration_ms': int((time.time() - start_time) * 1000)
                }

            # Compute signals
            signals = compute_signals(symbol, price_rows)

            if not signals:
                logger.info(f"No signals generated for {symbol}")
                return {
                    'symbol': symbol,
                    'status': 'no_signals',
                    'rows_inserted': 0,
                    'duration_ms': int((time.time() - start_time) * 1000)
                }

            # Insert signals
            rows_inserted = insert_signals(conn, signals)

            logger.info(f"Successfully processed {symbol}: {rows_inserted} signals inserted")

            return {
                'symbol': symbol,
                'status': 'success',
                'rows_inserted': rows_inserted,
                'signal_count': len(signals),
                'duration_ms': int((time.time() - start_time) * 1000)
            }

        finally:
            conn.close()

    except Exception as e:
        logger.exception(f"Error processing symbol: {e}")
        return {
            'symbol': event.get('symbol', 'unknown'),
            'status': 'error',
            'error': str(e),
            'duration_ms': int((time.time() - start_time) * 1000)
        }


# For local testing
if __name__ == "__main__":
    test_event = {
        "symbol": "AAPL",
        "backfill_days": 30
    }

    class MockContext:
        pass

    result = lambda_handler(test_event, MockContext())
    print(json.dumps(result, indent=2))
