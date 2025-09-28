#!/usr/bin/env python3
"""
Latest Buy/Sell Monthly Signals - Incremental Loading
Efficiently updates only the most recent monthly buy/sell signals.
"""
import gc
import json
import logging
import os
import resource
import sys
import time
from datetime import datetime, timedelta
from importlib import import_module

import boto3
import numpy as np
import pandas as pd
import psycopg2
from dateutil.relativedelta import relativedelta
from psycopg2.extras import RealDictCursor, execute_values

SCRIPT_NAME = "loadlatestbuysellmonthly.py"
logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s - %(levelname)s - %(message)s",
    stream=sys.stdout,
)


def get_rss_mb():
    usage = resource.getrusage(resource.RUSAGE_SELF).ru_maxrss
    if sys.platform.startswith("linux"):
        return usage / 1024
    return usage / (1024 * 1024)


def log_mem(stage: str):
    logging.info(f"[MEM] {stage}: {get_rss_mb():.1f} MB RSS")


# Database configuration
FRED_API_KEY = os.environ.get("FRED_API_KEY", "")
SECRET_ARN = os.environ["DB_SECRET_ARN"]

sm_client = boto3.client("secretsmanager")
secret_resp = sm_client.get_secret_value(SecretId=SECRET_ARN)
creds = json.loads(secret_resp["SecretString"])

DB_CONFIG = {
    "host": creds["host"],
    "port": int(creds.get("port", 5432)),
    "user": creds["username"],
    "password": creds["password"],
    "dbname": creds["dbname"],
}


def get_db_connection():
    return psycopg2.connect(**DB_CONFIG)


def create_buy_sell_table_if_not_exists(cur):
    """Create buy_sell_monthly table if it doesn't exist"""
    cur.execute(
        """
        CREATE TABLE IF NOT EXISTS buy_sell_monthly (
            symbol VARCHAR(20) NOT NULL,
            date DATE NOT NULL,
            timeframe VARCHAR(10) NOT NULL DEFAULT 'monthly',
            signal_type VARCHAR(10) NOT NULL,
            confidence DECIMAL(5,2) NOT NULL DEFAULT 0.0,
            price DECIMAL(12,4),
            rsi DECIMAL(5,2),
            macd DECIMAL(10,6),
            volume BIGINT,
            volume_avg_3m BIGINT,
            price_vs_ma6m DECIMAL(5,2),
            price_vs_ma12m DECIMAL(5,2),
            bollinger_position DECIMAL(5,2),
            support_level DECIMAL(12,4),
            resistance_level DECIMAL(12,4),
            pattern_score DECIMAL(5,2),
            momentum_score DECIMAL(5,2),
            risk_score DECIMAL(5,2),
            created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
            PRIMARY KEY (symbol, date, timeframe, signal_type)
        );
        
        CREATE INDEX IF NOT EXISTS idx_buy_sell_monthly_symbol_date 
        ON buy_sell_monthly (symbol, date);
        
        CREATE INDEX IF NOT EXISTS idx_buy_sell_monthly_signal_date 
        ON buy_sell_monthly (signal_type, date);
    """
    )


def get_last_signal_date(cur, symbol, timeframe="monthly"):
    """Get the last date we have signals for this symbol"""
    cur.execute(
        """
        SELECT MAX(date) as last_date 
        FROM buy_sell_monthly 
        WHERE symbol = %s AND timeframe = %s
    """,
        (symbol, timeframe),
    )

    result = cur.fetchone()
    return result["last_date"] if result and result["last_date"] else None


def get_available_data_range(cur, symbol):
    """Get the date range of available monthly price and technical data"""
    cur.execute(
        """
        SELECT 
            MIN(p.date) as min_price_date,
            MAX(p.date) as max_price_date,
            MIN(t.date) as min_tech_date,
            MAX(t.date) as max_tech_date
        FROM price_monthly p
        LEFT JOIN technical_data_monthly t ON p.symbol = t.symbol AND p.date = t.date
        WHERE p.symbol = %s
    """,
        (symbol,),
    )

    return cur.fetchone()


def calculate_buy_sell_signals_monthly(price_tech_data):
    """Calculate monthly buy/sell signals with long-term perspective"""
    signals = []

    if len(price_tech_data) < 12:  # Need at least 12 months for meaningful analysis
        return signals

    df = pd.DataFrame(price_tech_data)
    df = df.sort_values("date")

    # Calculate monthly moving averages
    if "ma6m" not in df.columns:
        df["ma6m"] = df["close"].rolling(6).mean()
    if "ma12m" not in df.columns:
        df["ma12m"] = df["close"].rolling(12).mean()
    if "volume_avg_3m" not in df.columns:
        df["volume_avg_3m"] = df["volume"].rolling(3).mean()

    # Calculate monthly Bollinger Bands
    if "bb_upper" not in df.columns:
        bb_period = 6  # 6 months for monthly data
        bb_std = 2
        rolling_mean = df["close"].rolling(bb_period).mean()
        rolling_std = df["close"].rolling(bb_period).std()
        df["bb_upper"] = rolling_mean + (rolling_std * bb_std)
        df["bb_lower"] = rolling_mean - (rolling_std * bb_std)

    # Calculate monthly support/resistance levels
    window = 6  # 6 months
    df["support"] = df["low"].rolling(window).min()
    df["resistance"] = df["high"].rolling(window).max()

    for idx, row in df.iterrows():
        if pd.isna(row["rsi"]) or pd.isna(row["macd"]) or pd.isna(row["ma6m"]):
            continue

        date = row["date"]
        symbol = row["symbol"]
        close = row["close"]
        volume = row["volume"]
        rsi = row["rsi"]
        macd = row["macd"]
        ma6m = row["ma6m"]
        ma12m = row["ma12m"]
        volume_avg = row["volume_avg_3m"]
        bb_upper = row["bb_upper"]
        bb_lower = row["bb_lower"]
        support = row["support"]
        resistance = row["resistance"]

        # Calculate derived metrics for monthly timeframe
        price_vs_ma6m = ((close - ma6m) / ma6m) * 100 if ma6m > 0 else 0
        price_vs_ma12m = ((close - ma12m) / ma12m) * 100 if ma12m > 0 else 0
        bollinger_pos = (
            ((close - bb_lower) / (bb_upper - bb_lower)) * 100
            if (bb_upper - bb_lower) > 0
            else 50
        )
        volume_ratio = volume / volume_avg if volume_avg > 0 else 1

        # Monthly signal calculation (very conservative, trend-focused)
        buy_score = 0
        sell_score = 0

        # RSI signals (even more conservative for monthly)
        if rsi < 40:
            buy_score += 25
        elif rsi > 60:
            sell_score += 25

        # MACD signals (long-term trend confirmation)
        if macd > 0:
            buy_score += 25
        else:
            sell_score += 25

        # Moving average signals (monthly trend is key)
        if close > ma6m > ma12m:
            buy_score += 30  # Strong uptrend
        elif close < ma6m < ma12m:
            sell_score += 30  # Strong downtrend

        # Long-term momentum
        if price_vs_ma12m > 10:  # 10% above 12-month MA
            buy_score += 15
        elif price_vs_ma12m < -10:  # 10% below 12-month MA
            sell_score += 15

        # Bollinger Band signals (monthly extremes)
        if bollinger_pos < 20:
            buy_score += 10
        elif bollinger_pos > 80:
            sell_score += 10

        # Volume confirmation (less important for monthly)
        if volume_ratio > 1.2:
            if buy_score > sell_score:
                buy_score += 5
            else:
                sell_score += 5

        # Support/resistance signals (wider tolerance for monthly)
        if abs(close - support) / close < 0.05:
            buy_score += 10
        elif abs(close - resistance) / close < 0.05:
            sell_score += 10

        # Pattern and momentum scores
        pattern_score = min(buy_score, sell_score) / max(buy_score, sell_score, 1) * 50
        momentum_score = abs(macd) * 5 if abs(macd) < 20 else 100
        risk_score = min(rsi, 100 - rsi) + (volume_ratio * 3)

        # Generate signals (very high threshold for monthly - focus on strong trends)
        if buy_score >= 60:
            signals.append(
                {
                    "symbol": symbol,
                    "date": date,
                    "timeframe": "monthly",
                    "signal_type": "BUY",
                    "confidence": min(buy_score, 95),
                    "price": close,
                    "rsi": rsi,
                    "macd": macd,
                    "volume": volume,
                    "volume_avg_3m": (
                        int(volume_avg) if not pd.isna(volume_avg) else None
                    ),
                    "price_vs_ma6m": price_vs_ma6m,
                    "price_vs_ma12m": price_vs_ma12m,
                    "bollinger_position": bollinger_pos,
                    "support_level": support,
                    "resistance_level": resistance,
                    "pattern_score": pattern_score,
                    "momentum_score": momentum_score,
                    "risk_score": risk_score,
                }
            )

        if sell_score >= 60:
            signals.append(
                {
                    "symbol": symbol,
                    "date": date,
                    "timeframe": "monthly",
                    "signal_type": "SELL",
                    "confidence": min(sell_score, 95),
                    "price": close,
                    "rsi": rsi,
                    "macd": macd,
                    "volume": volume,
                    "volume_avg_3m": (
                        int(volume_avg) if not pd.isna(volume_avg) else None
                    ),
                    "price_vs_ma6m": price_vs_ma6m,
                    "price_vs_ma12m": price_vs_ma12m,
                    "bollinger_position": bollinger_pos,
                    "support_level": support,
                    "resistance_level": resistance,
                    "pattern_score": pattern_score,
                    "momentum_score": momentum_score,
                    "risk_score": risk_score,
                }
            )

    return signals


def process_symbol_incremental(cur, symbol, timeframe="monthly"):
    """Process monthly buy/sell signals for a symbol using incremental approach"""

    last_signal_date = get_last_signal_date(cur, symbol, timeframe)
    data_range = get_available_data_range(cur, symbol)

    if not data_range or not data_range["max_price_date"]:
        logging.warning(f"No monthly price data available for {symbol}")
        return 0

    # Determine date range to process
    if last_signal_date:
        # Incremental update with 2-month buffer
        start_date = last_signal_date - relativedelta(months=2)
        logging.info(f"{symbol}: Monthly incremental update from {start_date}")

        # Delete existing signals in the date range
        cur.execute(
            """
            DELETE FROM buy_sell_monthly 
            WHERE symbol = %s AND timeframe = %s AND date >= %s
        """,
            (symbol, timeframe, start_date),
        )

    else:
        # Full history processing
        start_date = data_range["min_price_date"]
        logging.info(f"{symbol}: Monthly full history processing from {start_date}")

    # Fetch monthly price and technical data
    cur.execute(
        """
        SELECT 
            p.symbol, p.date, p.open, p.high, p.low, p.close, p.adj_close, p.volume,
            t.rsi, t.macd, t.signal_line, t.macd_histogram, t.bb_upper, t.bb_lower,
            t.stoch_k, t.stoch_d, t.williams_r, t.cci, t.adx
        FROM price_monthly p
        LEFT JOIN technical_data_monthly t ON p.symbol = t.symbol AND p.date = t.date
        WHERE p.symbol = %s AND p.date >= %s
        ORDER BY p.date
    """,
        (symbol, start_date),
    )

    price_tech_data = cur.fetchall()

    if not price_tech_data:
        logging.warning(f"No monthly data found for {symbol} from {start_date}")
        return 0

    # Calculate monthly signals
    signals = calculate_buy_sell_signals_monthly(price_tech_data)

    if not signals:
        logging.info(f"{symbol}: No monthly signals generated")
        return 0

    # Insert new signals
    insert_sql = """
        INSERT INTO buy_sell_monthly (
            symbol, date, timeframe, signal_type, confidence, price, rsi, macd,
            volume, volume_avg_3m, price_vs_ma6m, price_vs_ma12m, bollinger_position,
            support_level, resistance_level, pattern_score, momentum_score, risk_score
        ) VALUES %s
        ON CONFLICT (symbol, date, timeframe, signal_type) 
        DO UPDATE SET
            confidence = EXCLUDED.confidence,
            price = EXCLUDED.price,
            rsi = EXCLUDED.rsi,
            macd = EXCLUDED.macd,
            volume = EXCLUDED.volume,
            volume_avg_3m = EXCLUDED.volume_avg_3m,
            price_vs_ma6m = EXCLUDED.price_vs_ma6m,
            price_vs_ma12m = EXCLUDED.price_vs_ma12m,
            bollinger_position = EXCLUDED.bollinger_position,
            support_level = EXCLUDED.support_level,
            resistance_level = EXCLUDED.resistance_level,
            pattern_score = EXCLUDED.pattern_score,
            momentum_score = EXCLUDED.momentum_score,
            risk_score = EXCLUDED.risk_score,
            created_at = CURRENT_TIMESTAMP
    """

    signal_rows = []
    for signal in signals:
        signal_rows.append(
            (
                signal["symbol"],
                signal["date"],
                signal["timeframe"],
                signal["signal_type"],
                signal["confidence"],
                signal["price"],
                signal["rsi"],
                signal["macd"],
                signal["volume"],
                signal["volume_avg_3m"],
                signal["price_vs_ma6m"],
                signal["price_vs_ma12m"],
                signal["bollinger_position"],
                signal["support_level"],
                signal["resistance_level"],
                signal["pattern_score"],
                signal["momentum_score"],
                signal["risk_score"],
            )
        )

    execute_values(cur, insert_sql, signal_rows)

    logging.info(f"{symbol}: Processed {len(signals)} monthly signals")
    return len(signals)


def main():
    log_mem("Monthly script start")

    conn = get_db_connection()
    cur = conn.cursor(cursor_factory=RealDictCursor)

    try:
        create_buy_sell_table_if_not_exists(cur)
        conn.commit()

        cur.execute(
            """
            SELECT DISTINCT symbol 
            FROM stock_symbols 
            WHERE status = 'active'
            ORDER BY symbol
        """
        )
        symbols = [row["symbol"] for row in cur.fetchall()]

        if not symbols:
            logging.warning("No active symbols found")
            return

        logging.info(
            f"Processing {len(symbols)} symbols for latest monthly buy/sell signals"
        )

        total_signals = 0
        processed_count = 0
        failed_count = 0

        for symbol in symbols:
            try:
                signals_count = process_symbol_incremental(cur, symbol)
                total_signals += signals_count
                processed_count += 1

                if processed_count % 10 == 0:
                    conn.commit()
                    logging.info(
                        f"Monthly progress: {processed_count}/{len(symbols)} symbols processed"
                    )

                time.sleep(0.1)

            except Exception as e:
                logging.error(f"Failed to process monthly signals for {symbol}: {e}")
                failed_count += 1
                continue

        conn.commit()

        logging.info(f"=== MONTHLY SUMMARY ===")
        logging.info(f"Symbols processed: {processed_count}")
        logging.info(f"Symbols failed: {failed_count}")
        logging.info(f"Total monthly signals generated: {total_signals}")

        # Cleanup old monthly signals (keep last 3 years)
        cleanup_date = datetime.now().date() - relativedelta(years=3)
        cur.execute(
            """
            DELETE FROM buy_sell_monthly 
            WHERE date < %s
        """,
            (cleanup_date,),
        )

        deleted_count = cur.rowcount
        if deleted_count > 0:
            logging.info(
                f"Cleaned up {deleted_count} old monthly signals before {cleanup_date}"
            )

        conn.commit()

    except Exception as e:
        logging.error(f"Monthly script failed: {e}")
        conn.rollback()
        raise
    finally:
        cur.close()
        conn.close()
        log_mem("Monthly script end")


if __name__ == "__main__":
    main()
