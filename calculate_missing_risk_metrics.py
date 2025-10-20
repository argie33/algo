#!/usr/bin/env python3
"""
Calculate missing volatility_12m_pct and max_drawdown_52w_pct from daily price data.

These metrics are calculated from technical_data_daily table:
- volatility_12m_pct: Standard deviation of daily returns over past 252 trading days
- max_drawdown_52w_pct: Maximum peak-to-trough drawdown over past 52 weeks
"""

import logging
import os
import sys
from datetime import datetime, timedelta

import numpy as np
import psycopg2
import psycopg2.extras

logging.basicConfig(level=logging.INFO, format="%(asctime)s - %(levelname)s - %(message)s")
logger = logging.getLogger(__name__)


def get_db_config():
    """Get database configuration from environment"""
    return {
        "host": os.getenv("DB_HOST", "localhost"),
        "port": int(os.getenv("DB_PORT", "5432")),
        "user": os.getenv("DB_USER", "postgres"),
        "password": os.getenv("DB_PASSWORD", "password"),
        "dbname": os.getenv("DB_NAME", "stocks"),
    }


def calculate_volatility_and_drawdown():
    """Calculate missing volatility and drawdown metrics"""
    cfg = get_db_config()
    conn = psycopg2.connect(**cfg)
    cur = conn.cursor()

    logger.info("=" * 80)
    logger.info("Calculating Missing Risk Metrics")
    logger.info("=" * 80)

    try:
        # Find all stocks with NULL volatility or drawdown
        cur.execute("""
            SELECT DISTINCT symbol
            FROM risk_metrics
            WHERE volatility_12m_pct IS NULL OR max_drawdown_52w_pct IS NULL
            ORDER BY symbol
        """)

        symbols_to_process = [row[0] for row in cur.fetchall()]
        logger.info(f"\nFound {len(symbols_to_process)} stocks with missing risk metrics")

        updated_vol = 0
        updated_draw = 0
        failed = 0

        for idx, symbol in enumerate(symbols_to_process):
            try:
                # Get daily price data for past 252 days (1 year) + 52 weeks lookback
                cur.execute("""
                    SELECT date, close
                    FROM price_daily
                    WHERE symbol = %s
                      AND date >= NOW() - INTERVAL '1 year'
                    ORDER BY date ASC
                """, (symbol,))

                rows = cur.fetchall()

                if len(rows) < 20:  # Need at least some data
                    logger.warning(f"  {symbol}: Insufficient data ({len(rows)} days)")
                    continue

                dates = [r[0] for r in rows]
                closes = np.array([float(r[1]) for r in rows])

                # Calculate daily returns
                daily_returns = np.diff(closes) / closes[:-1]

                # 1. Volatility: std dev of daily returns * sqrt(252) to annualize
                volatility_12m_pct = float(np.std(daily_returns, ddof=1) * np.sqrt(252) * 100)

                # 2. Max Drawdown: (peak - trough) / peak
                cumulative_max = np.maximum.accumulate(closes)
                drawdown = (cumulative_max - closes) / cumulative_max
                max_drawdown_52w_pct = float(np.max(drawdown) * 100)

                # Update database
                cur.execute("""
                    UPDATE risk_metrics
                    SET
                        volatility_12m_pct = %s,
                        max_drawdown_52w_pct = %s,
                        fetched_at = CURRENT_TIMESTAMP
                    WHERE symbol = %s AND volatility_12m_pct IS NULL
                """, (volatility_12m_pct, max_drawdown_52w_pct, symbol))

                if cur.rowcount > 0:
                    updated_vol += 1
                    logger.info(
                        f"  {symbol}: vol={volatility_12m_pct:.2f}%, drawdown={max_drawdown_52w_pct:.2f}%"
                    )

            except Exception as e:
                logger.error(f"  Error processing {symbol}: {e}")
                failed += 1
                conn.rollback()
                continue

            if (idx + 1) % 50 == 0:
                logger.info(f"  Progress: {idx + 1}/{len(symbols_to_process)} processed...")
                conn.commit()

        conn.commit()
        logger.info(f"\n✅ Complete:")
        logger.info(f"   Updated volatility: {updated_vol} stocks")
        logger.info(f"   Updated drawdown: {updated_vol} stocks (same batch)")
        logger.info(f"   Failed: {failed} stocks")

    except Exception as e:
        logger.error(f"Fatal error: {e}")
        import traceback

        traceback.print_exc()
    finally:
        cur.close()
        conn.close()


if __name__ == "__main__":
    calculate_volatility_and_drawdown()
