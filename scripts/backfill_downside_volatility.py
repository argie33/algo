#!/usr/bin/env python3
"""Direct backfill of downside volatility and max drawdown for all symbols.

Bypasses loader watermarks to populate stability_metrics for all symbols.
"""

import sys
sys.path.insert(0, '.')

from utils.dotenv_loader import load_env_local
load_env_local()

import psycopg2
import os
import logging
import math
from datetime import datetime, timezone
from typing import Optional

logger = logging.getLogger(__name__)
logger.setLevel(logging.INFO)
handler = logging.StreamHandler()
handler.setFormatter(logging.Formatter('%(message)s'))
logger.addHandler(handler)


def get_price_history(cur, symbol: str, limit: int = 252) -> Optional[tuple]:
    """Get recent price history for a symbol."""
    cur.execute(
        'SELECT date, close FROM price_daily WHERE symbol = %s ORDER BY date ASC',
        (symbol,)
    )
    rows = cur.fetchall()
    if not rows:
        return None
    # Keep only last `limit` rows (oldest first for calculation)
    rows = rows[-limit:] if len(rows) > limit else rows
    dates = [r[0] for r in rows]
    prices = [float(r[1]) for r in rows]
    return dates, prices


def calculate_volatility(returns):
    """Calculate annualized volatility from returns."""
    if not returns or len(returns) < 2:
        return None

    mean_return = sum(returns) / len(returns)
    variance = sum((r - mean_return) ** 2 for r in returns) / (len(returns) - 1)
    daily_std = math.sqrt(variance)
    return daily_std * math.sqrt(252)


def calculate_downside_volatility(returns):
    """Calculate annualized downside volatility (std dev of negative returns only)."""
    if not returns or len(returns) < 2:
        return None

    downside_returns = [r for r in returns if r < 0]
    if not downside_returns or len(downside_returns) < 1:
        return None

    if len(downside_returns) < 2:
        return 0.0

    mean_return = sum(downside_returns) / len(downside_returns)
    variance = sum((r - mean_return) ** 2 for r in downside_returns) / (len(downside_returns) - 1)
    daily_std = math.sqrt(variance)
    return daily_std * math.sqrt(252)


def calculate_max_drawdown(prices):
    """Calculate maximum drawdown: largest peak-to-trough decline as percentage."""
    if not prices or len(prices) < 2:
        return None

    max_drawdown = 0.0
    peak = prices[0]

    for price in prices[1:]:
        if price > 0 and peak > 0:
            drawdown = ((price - peak) / peak) * 100
            max_drawdown = min(max_drawdown, drawdown)
        if price > peak:
            peak = price

    return max_drawdown if max_drawdown != 0.0 else None


def calculate_log_returns(prices):
    """Calculate log returns from prices."""
    returns = []
    for i in range(1, len(prices)):
        if prices[i - 1] > 0:
            ret = math.log(prices[i] / prices[i - 1])
            returns.append(ret)
    return returns


def backfill_symbol(cur_read, cur_write, symbol: str) -> bool:
    """Calculate and insert/update downside volatility and max drawdown for a symbol."""
    try:
        # Get price history
        price_data = get_price_history(cur_read, symbol)
        if not price_data:
            return False

        dates, prices = price_data

        # Need at least 60 days for volatility calculations
        if len(prices) < 60:
            return False

        # Calculate returns for volatility measures
        log_returns = calculate_log_returns(prices)
        if not log_returns:
            return False

        # Calculate volatility measures
        vol_30d = calculate_volatility(log_returns[-30:]) if len(log_returns) >= 30 else None
        vol_60d = calculate_volatility(log_returns[-60:]) if len(log_returns) >= 60 else None
        vol_252d = calculate_volatility(log_returns) if len(log_returns) >= 60 else None

        # Calculate downside volatility (risk metric - negative returns only)
        downside_vol_30d = calculate_downside_volatility(log_returns[-30:]) if len(log_returns) >= 30 else None
        downside_vol_60d = calculate_downside_volatility(log_returns[-60:]) if len(log_returns) >= 60 else None
        downside_vol_252d = calculate_downside_volatility(log_returns) if len(log_returns) >= 60 else None

        # Calculate max drawdown (peak-to-trough decline)
        max_drawdown = calculate_max_drawdown(prices) if len(prices) >= 5 else None

        # Check if record exists
        cur_read.execute('SELECT 1 FROM stability_metrics WHERE symbol = %s', (symbol,))
        exists = cur_read.fetchone()

        if exists:
            # Update existing record
            cur_write.execute('''
                UPDATE stability_metrics
                SET volatility_30d = %s,
                    volatility_60d = %s,
                    volatility_252d = %s,
                    downside_volatility_30d = %s,
                    downside_volatility_60d = %s,
                    downside_volatility_252d = %s,
                    max_drawdown_1y = %s,
                    created_at = %s
                WHERE symbol = %s
            ''', (vol_30d, vol_60d, vol_252d, downside_vol_30d, downside_vol_60d,
                  downside_vol_252d, max_drawdown, datetime.now(timezone.utc).isoformat(), symbol))
        else:
            # Insert new record with minimal data
            cur_write.execute('''
                INSERT INTO stability_metrics
                (symbol, volatility_30d, volatility_60d, volatility_252d,
                 downside_volatility_30d, downside_volatility_60d, downside_volatility_252d,
                 max_drawdown_1y, created_at)
                VALUES (%s, %s, %s, %s, %s, %s, %s, %s, %s)
            ''', (symbol, vol_30d, vol_60d, vol_252d, downside_vol_30d, downside_vol_60d,
                  downside_vol_252d, max_drawdown, datetime.now(timezone.utc).isoformat()))

        return True
    except Exception as e:
        logger.warning(f"Failed to backfill {symbol}: {e}")
        return False


if __name__ == "__main__":
    conn = psycopg2.connect(
        host=os.getenv('DB_HOST'),
        port=os.getenv('DB_PORT', 5432),
        user=os.getenv('DB_USER'),
        password=os.getenv('DB_PASSWORD'),
        database=os.getenv('DB_NAME')
    )

    cur_read = conn.cursor()
    cur_write = conn.cursor()

    try:
        # Get all symbols
        cur_read.execute('SELECT DISTINCT symbol FROM stock_scores ORDER BY symbol')
        symbols = [row[0] for row in cur_read.fetchall()]

        print(f"Backfilling {len(symbols)} symbols...")
        success_count = 0

        for i, symbol in enumerate(symbols):
            if backfill_symbol(cur_read, cur_write, symbol):
                success_count += 1

            if (i + 1) % 100 == 0:
                conn.commit()
                print(f"  Processed {i + 1}/{len(symbols)} ({success_count} successful)")

        conn.commit()
        print(f"Backfill complete: {success_count}/{len(symbols)} symbols populated")

    finally:
        cur_read.close()
        cur_write.close()
        conn.close()
