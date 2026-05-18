#!/usr/bin/env python3
import sys
from pathlib import Path
sys.path.insert(0, str(Path(__file__).parent.parent))

"""
Market Health Daily Loader.

Computes market-wide metrics from SPY price data:
- Distribution days
- Market stage
- Advance/decline
- VIX proxy

Populates market_health_daily table (one row per date).

Run:
    python3 load_market_health_daily.py [--parallelism 1]
"""

import argparse
import logging
import os
from datetime import date, timedelta
from typing import List, Optional

import numpy as np
import pandas as pd

from config.env_loader import load_env
from utils.db_connection import get_db_connection
from utils.structured_logger import get_logger
from utils.monitoring_context import TimeBlock
from utils.optimal_loader import OptimalLoader

logger = get_logger(__name__)


class MarketHealthDailyLoader(OptimalLoader):
    table_name = "market_health_daily"
    primary_key = ("date",)
    watermark_field = "date"

    def fetch_incremental(self, symbol: str, since: Optional[date]):
        """Fetch SPY price_daily data for market health calculations."""
        db_conn = get_db_connection()
        end = date.today()
        start = end - timedelta(days=100)  # 100 days lookback

        query = """
            SELECT symbol, date, open, high, low, close, volume
            FROM price_daily
            WHERE symbol = 'SPY' AND date >= %s AND date <= %s
            ORDER BY date ASC
        """

        try:
            cursor = db_conn.cursor()
            cursor.execute(query, (start, end))
            rows = cursor.fetchall()
            cursor.close()

            if not rows:
                logger.warning("No SPY price data found")
                return None

            return [
                {
                    'symbol': 'SPY',
                    'date': row[1],
                    'open': float(row[2]),
                    'high': float(row[3]),
                    'low': float(row[4]),
                    'close': float(row[5]),
                    'volume': float(row[6]),
                }
                for row in rows
            ]
        except Exception as e:
            logger.error(f"Failed to fetch SPY price_daily: {e}")
            return None
        finally:
            db_conn.close()

    def transform(self, rows):
        """Compute market health metrics from SPY data."""
        if not rows or len(rows) < 20:
            return []

        try:
            df = pd.DataFrame(rows)
            df = df.sort_values('date').reset_index(drop=True)

            # Compute market health metrics
            df = self._compute_market_health(df)

            # Keep last 50 rows
            df = df.tail(50)

            result = []
            for _, row in df.iterrows():
                result.append({
                    'date': row['date'],
                    'market_trend': row.get('market_trend', 'NEUTRAL'),
                    'market_stage': int(row.get('market_stage', 2)),
                    'distribution_days_4w': int(row.get('distribution_days_4w', 0)),
                    'distribution_days_20d': int(row.get('distribution_days_20d', 0)),
                    'up_volume_percent': float(row.get('up_volume_percent', 50.0)),
                    'advance_decline_ratio': float(row.get('advance_decline_ratio', 1.0)),
                    'new_highs_count': int(row.get('new_highs_count', 0)),
                    'new_lows_count': int(row.get('new_lows_count', 0)),
                    'breadth_momentum_10d': float(row.get('breadth_momentum_10d', np.nan)),
                    'vix_level': float(row.get('vix_level', np.nan)),
                    'put_call_ratio': float(row.get('put_call_ratio', np.nan)),
                    'yield_curve_slope': float(row.get('yield_curve_slope', np.nan)),
                    'fed_rate_environment': row.get('fed_rate_environment', 'NEUTRAL'),
                    'market_comment': row.get('market_comment', ''),
                })

            return result
        except Exception as e:
            logger.error(f"Transform failed: {e}")
            return []

    def _compute_market_health(self, df: pd.DataFrame) -> pd.DataFrame:
        """Compute market health metrics from SPY data."""
        df = df.copy()

        # Calculate distribution days (down days on high volume)
        df['volume_sma_20'] = df['volume'].rolling(20).mean()
        df['is_down_day'] = df['close'] < df['open']
        df['high_volume'] = df['volume'] > df['volume_sma_20']
        df['distribution_day'] = df['is_down_day'] & df['high_volume']

        # Count distribution days in different periods
        df['distribution_days_4w'] = df['distribution_day'].rolling(20).sum()
        df['distribution_days_20d'] = df['distribution_day'].rolling(10).sum()

        # Market trend based on price position
        df['sma_50'] = df['close'].rolling(50).mean()
        df['sma_200'] = df['close'].rolling(200).mean()

        # Determine market trend
        def get_market_trend(row):
            if row['close'] > row['sma_50'] > row['sma_200']:
                return 'STRONG_UP'
            elif row['close'] > row['sma_200'] and row['sma_50'] > row['sma_200']:
                return 'UP'
            elif row['close'] < row['sma_200'] and row['sma_50'] < row['sma_200']:
                return 'DOWN'
            elif row['close'] < row['sma_50'] < row['sma_200']:
                return 'STRONG_DOWN'
            else:
                return 'NEUTRAL'

        df['market_trend'] = df.apply(get_market_trend, axis=1)

        # Market stage (similar to Weinstein for market)
        def get_market_stage(row):
            if row['close'] > row['sma_50'] > row['sma_200']:
                return 2  # Markup
            elif row['close'] > row['sma_200']:
                return 1  # Accumulation
            elif row['close'] < row['sma_200']:
                return 4  # Decline
            else:
                return 3  # Distribution

        df['market_stage'] = df.apply(get_market_stage, axis=1)

        # Advance/decline ratio (simplified - use price momentum)
        df['price_change'] = df['close'].pct_change()
        df['positive_change'] = (df['price_change'] > 0).astype(int)
        df['advance_decline_ratio'] = df['positive_change'].rolling(10).mean() / (
            1 - df['positive_change'].rolling(10).mean()
        )

        # New highs/lows (simplified)
        df['is_new_high'] = df['close'] == df['close'].rolling(60).max()
        df['is_new_low'] = df['close'] == df['close'].rolling(60).min()
        df['new_highs_count'] = df['is_new_high'].rolling(10).sum()
        df['new_lows_count'] = df['is_new_low'].rolling(10).sum()

        # Up volume percent (simplified)
        df['up_day'] = df['close'] > df['open']
        df['up_volume'] = df.loc[df['up_day'], 'volume'].sum()
        df['total_volume'] = df['volume'].rolling(10).sum()
        df['up_volume_percent'] = (df['up_volume'] / df['total_volume'] * 100).fillna(50.0)

        # Breadth momentum
        df['breadth_momentum_10d'] = df['positive_change'].rolling(10).mean() * 100

        # VIX proxy (use SPY volatility as proxy)
        df['returns'] = df['close'].pct_change()
        df['vix_level'] = df['returns'].rolling(20).std() * np.sqrt(252) * 100

        # Put/call ratio (simplified)
        df['put_call_ratio'] = 1.0  # Placeholder

        # Yield curve slope (placeholder)
        df['yield_curve_slope'] = 2.0  # Placeholder

        # Fed rate environment
        df['fed_rate_environment'] = 'NEUTRAL'  # Placeholder

        # Market comment
        df['market_comment'] = ''

        return df

    def run(self, symbols: List[str], parallelism: int = 1):
        """Override run to use only SPY."""
        # Market health is calculated from SPY only
        return super().run(['SPY'], parallelism=1)


def main():
    try:
        load_env()
        logger.info("[MAIN] Environment loaded successfully")
    except Exception as e:
        logger.error(f"[MAIN] Failed to load environment: {e}", exc_info=True)
        return 1

    parser = argparse.ArgumentParser(description="Market Health Daily Loader")
    default_parallelism = int(os.getenv("PARALLELISM", os.getenv("LOADER_PARALLELISM", "1")))
    parser.add_argument("--parallelism", type=int, default=default_parallelism, help="Concurrent workers (always 1)")
    args = parser.parse_args()

    loader = MarketHealthDailyLoader()
    try:
        logger.info(f"[MAIN] Starting market health loader")
        with TimeBlock("load_market_health_daily"):
            stats = loader.run(['SPY'], parallelism=1)

        logger.info(f"[MAIN] Loader completed: {stats}")
        return 0 if stats["symbols_failed"] == 0 else 1

    except Exception as e:
        logger.error(f"[MAIN] Loader failed with error: {e}", exc_info=True)
        return 1
    finally:
        loader.close()


if __name__ == "__main__":
    sys.exit(main())
