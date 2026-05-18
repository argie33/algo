#!/usr/bin/env python3
import sys
from pathlib import Path
sys.path.insert(0, str(Path(__file__).parent.parent))

"""
Signal Quality Scores Loader.

Computes composite signal quality scores combining:
- Trend template score
- Base quality score (from signal strength)
- Volume confirmation
- Distance from 52w high
- Institutional ownership
- Market stage
- VCP pattern
- Distribution days
- Earnings proximity

Populates signal_quality_scores table.

Run:
    python3 load_signal_quality_scores.py [--symbols AAPL,MSFT] [--parallelism 4]
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
from utils.loader_helpers import get_active_symbols
from utils.structured_logger import get_logger
from utils.monitoring_context import TimeBlock
from utils.optimal_loader import OptimalLoader

logger = get_logger(__name__)


class SignalQualityScoresLoader(OptimalLoader):
    table_name = "signal_quality_scores"
    primary_key = ("symbol", "date")
    watermark_field = "date"

    def fetch_incremental(self, symbol: str, since: Optional[date]):
        """Fetch signal and technical data for quality scoring."""
        db_conn = get_db_connection()
        end = date.today()
        start = end - timedelta(days=60)

        query = """
            SELECT
                b.symbol, b.date, b.signal, b.strength,
                t.minervini_trend_score, t.price_52w_high, t.price_52w_low, t.percent_from_52w_high,
                m.market_stage, m.distribution_days_4w,
                p.volume, p.close
            FROM buy_sell_daily b
            LEFT JOIN trend_template_data t ON b.symbol = t.symbol AND b.date = t.date
            LEFT JOIN market_health_daily m ON b.date = m.date
            LEFT JOIN price_daily p ON b.symbol = p.symbol AND b.date = p.date
            WHERE b.symbol = %s AND b.date >= %s AND b.date <= %s
            AND b.signal IN ('BUY', 'STRONG_BUY')
            ORDER BY b.date ASC
        """

        try:
            cursor = db_conn.cursor()
            cursor.execute(query, (symbol, start, end))
            rows = cursor.fetchall()
            cursor.close()

            if not rows:
                return None

            return [
                {
                    'symbol': row[0],
                    'date': row[1],
                    'signal': row[2],
                    'strength': float(row[3]) if row[3] else 0.0,
                    'minervini_trend_score': int(row[4]) if row[4] else 0,
                    'price_52w_high': float(row[5]) if row[5] else None,
                    'price_52w_low': float(row[6]) if row[6] else None,
                    'percent_from_52w_high': float(row[7]) if row[7] else None,
                    'market_stage': int(row[8]) if row[8] else 2,
                    'distribution_days_4w': int(row[9]) if row[9] else 0,
                    'volume': float(row[10]) if row[10] else 0.0,
                    'close': float(row[11]) if row[11] else 0.0,
                }
                for row in rows
            ]
        except Exception as e:
            logger.error(f"[{symbol}] Failed to fetch signal data: {e}")
            return None
        finally:
            db_conn.close()

    def transform(self, rows):
        """Compute signal quality scores."""
        if not rows:
            return []

        try:
            df = pd.DataFrame(rows)

            # Compute all quality components
            df['trend_template_score'] = self._score_trend_template(df)
            df['base_quality_score'] = self._score_base_quality(df)
            df['volume_confirmation_score'] = self._score_volume_confirmation(df)
            df['distance_from_high_score'] = self._score_distance_from_high(df)
            df['institutional_ownership_score'] = 50  # Placeholder
            df['market_stage_score'] = self._score_market_stage(df)
            df['vcp_pattern_score'] = 50  # Placeholder
            df['distribution_days_score'] = self._score_distribution_days(df)
            df['earnings_proximity_score'] = 50  # Placeholder

            # Composite SQS (weighted average of all components)
            df['composite_sqs'] = self._calculate_composite_sqs(df)

            # Rank signals
            df = df.sort_values('composite_sqs', ascending=False).reset_index(drop=True)
            df['rank_vs_all_signals'] = range(1, len(df) + 1)

            result = []
            for _, row in df.iterrows():
                result.append({
                    'symbol': row['symbol'],
                    'date': row['date'],
                    'trend_template_score': int(row['trend_template_score']),
                    'base_quality_score': int(row['base_quality_score']),
                    'volume_confirmation_score': int(row['volume_confirmation_score']),
                    'distance_from_high_score': int(row['distance_from_high_score']),
                    'institutional_ownership_score': int(row['institutional_ownership_score']),
                    'market_stage_score': int(row['market_stage_score']),
                    'vcp_pattern_score': int(row['vcp_pattern_score']),
                    'distribution_days_score': int(row['distribution_days_score']),
                    'earnings_proximity_score': int(row['earnings_proximity_score']),
                    'composite_sqs': int(row['composite_sqs']),
                    'rank_vs_all_signals': int(row['rank_vs_all_signals']),
                })

            return result
        except Exception as e:
            logger.error(f"Transform failed: {e}")
            return []

    def _score_trend_template(self, df: pd.DataFrame) -> pd.Series:
        """Score based on Minervini trend template (0-100)."""
        # Minervini scores 0-8, convert to 0-100
        return (df['minervini_trend_score'] / 8 * 100).fillna(0).astype(int)

    def _score_base_quality(self, df: pd.DataFrame) -> pd.Series:
        """Score based on signal strength (0-100)."""
        # Signal strength typically 0-100
        return df['strength'].fillna(0).astype(int)

    def _score_volume_confirmation(self, df: pd.DataFrame) -> pd.Series:
        """Score based on volume analysis (0-100)."""
        # Placeholder: all signals get 50
        return pd.Series(50, index=df.index)

    def _score_distance_from_high(self, df: pd.DataFrame) -> pd.Series:
        """Score based on proximity to 52w high.

        Sweet spot: 70-90% of 52w high (good risk/reward)
        Score 100 if 70-90%, decay otherwise
        """
        pct_from_high = df['percent_from_52w_high'].fillna(-100)

        score = pd.Series(0, index=df.index)

        # Sweet zone: 70-90% from high (negative percent means below)
        sweet_zone = (-30 <= pct_from_high) & (pct_from_high <= -10)
        score[sweet_zone] = 100

        # Near sweet zone: 50-100
        near_sweet = ((-50 <= pct_from_high) & (pct_from_high < -30)) | (
            (pct_from_high > -10) & (pct_from_high <= -5)
        )
        score[near_sweet] = 75

        # Moderate distance
        moderate = (-100 <= pct_from_high) & (pct_from_high < -50)
        score[moderate] = 50

        return score

    def _score_market_stage(self, df: pd.DataFrame) -> pd.Series:
        """Score based on market stage.

        Stage 1-2 (Accumulation/Markup): 100
        Stage 3 (Distribution): 50
        Stage 4 (Decline): 0
        """
        stage = df['market_stage'].fillna(2).astype(int)
        score = pd.Series(0, index=df.index)

        score[(stage == 1) | (stage == 2)] = 100
        score[stage == 3] = 50
        score[stage == 4] = 0

        return score

    def _score_distribution_days(self, df: pd.DataFrame) -> pd.Series:
        """Score based on market distribution days.

        Few distribution days (0-3): 100
        Moderate (4-7): 75
        High (8+): 25
        """
        days = df['distribution_days_4w'].fillna(0).astype(int)
        score = pd.Series(0, index=df.index)

        score[days <= 3] = 100
        score[(days > 3) & (days <= 7)] = 75
        score[days > 7] = 25

        return score

    def _calculate_composite_sqs(self, df: pd.DataFrame) -> pd.Series:
        """Calculate weighted composite SQS (Signal Quality Score)."""
        weights = {
            'trend_template_score': 0.25,
            'base_quality_score': 0.25,
            'volume_confirmation_score': 0.15,
            'distance_from_high_score': 0.15,
            'market_stage_score': 0.12,
            'distribution_days_score': 0.08,
        }

        composite = pd.Series(0.0, index=df.index)

        for col, weight in weights.items():
            composite += df[col].fillna(0) * weight

        return composite.round(0).astype(int)


def main():
    try:
        load_env()
        logger.info("[MAIN] Environment loaded successfully")
    except Exception as e:
        logger.error(f"[MAIN] Failed to load environment: {e}", exc_info=True)
        return 1

    parser = argparse.ArgumentParser(description="Signal Quality Scores Loader")
    parser.add_argument("--symbols", help="Comma-separated symbols. Default: all from stocks table.")
    default_parallelism = int(os.getenv("PARALLELISM", os.getenv("LOADER_PARALLELISM", "4")))
    parser.add_argument("--parallelism", type=int, default=default_parallelism, help="Concurrent workers")
    args = parser.parse_args()

    try:
        if args.symbols:
            symbols = [s.strip().upper() for s in args.symbols.split(",")]
            logger.info(f"[MAIN] Loaded {len(symbols)} symbols from CLI")
        else:
            symbols = get_active_symbols()
            logger.info(f"[MAIN] Loaded {len(symbols)} symbols from database")
    except Exception as e:
        logger.error(f"[MAIN] Failed to get symbols: {e}", exc_info=True)
        return 1

    loader = SignalQualityScoresLoader()
    try:
        logger.info(f"[MAIN] Starting signal quality scores loader (parallelism={args.parallelism})")
        with TimeBlock("load_signal_quality_scores"):
            stats = loader.run(symbols, parallelism=args.parallelism)

        logger.info(f"[MAIN] Loader completed: {stats}")
        return 0 if stats["symbols_failed"] == 0 else 1

    except Exception as e:
        logger.error(f"[MAIN] Loader failed with error: {e}", exc_info=True)
        return 1
    finally:
        loader.close()


if __name__ == "__main__":
    sys.exit(main())
