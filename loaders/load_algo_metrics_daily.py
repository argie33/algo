#!/usr/bin/env python3
"""Algo daily metrics — portfolio stats and execution summary after trading day."""

import sys
from pathlib import Path
sys.path.insert(0, str(Path(__file__).parent.parent))

import logging
from datetime import date
from typing import Dict, List
from algo.algo_orchestrator import Orchestrator
from utils.db_connection import get_db_connection
from config.env_loader import load_env

logger = logging.getLogger(__name__)


class AlgoMetricsDailyLoader:
    """Compute and store daily algo performance metrics after orchestrator completes."""

    def __init__(self):
        self.conn = None

    def connect(self):
        self.conn = get_db_connection()

    def disconnect(self):
        if self.conn:
            self.conn.close()

    def ensure_table_exists(self):
        """Create algo_metrics_daily table if it doesn't exist."""
        cursor = self.conn.cursor()
        try:
            # First check if table exists
            cursor.execute("""
                SELECT 1 FROM information_schema.tables
                WHERE table_schema = 'public' AND table_name = 'algo_metrics_daily'
            """)
            if cursor.fetchone():
                logger.info("algo_metrics_daily table exists")
                return

            # Table doesn't exist, create it
            logger.info("Creating algo_metrics_daily table...")
            cursor.execute("""
                CREATE TABLE algo_metrics_daily (
                    date DATE PRIMARY KEY,
                    total_actions INTEGER,
                    entries INTEGER,
                    exits INTEGER,
                    avg_signal_score DECIMAL(8, 4),
                    created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
                    updated_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP
                )
            """)
            self.conn.commit()
            logger.info("algo_metrics_daily table created successfully")
        except Exception as e:
            logger.error(f"Failed to ensure table: {e}", exc_info=True)
            try:
                self.conn.rollback()
            except:
                pass
            raise
            self.conn.rollback()
            raise
        finally:
            cursor.close()

    def compute_daily_metrics(self, run_date: date) -> Dict:
        """Compute portfolio stats from algo_audit_log for the trading day."""
        try:
            cursor = self.conn.cursor()
            cursor.execute("""
                SELECT
                    DATE(created_at) as trading_date,
                    COUNT(*) as total_actions,
                    SUM(CASE WHEN action_type = 'BUY' THEN 1 ELSE 0 END) as entries,
                    SUM(CASE WHEN action_type = 'SELL' THEN 1 ELSE 0 END) as exits,
                    AVG(CAST(details->>'score' AS FLOAT)) as avg_signal_score
                FROM algo_audit_log
                WHERE DATE(created_at) = %s
                GROUP BY DATE(created_at)
            """, (run_date,))
            row = cursor.fetchone()
            cursor.close()
            if not row:
                return {}
            return {
                'trading_date': row[0],
                'total_actions': row[1],
                'entries': row[2],
                'exits': row[3],
                'avg_signal_score': row[4]
            }
        except Exception as e:
            logger.error(f"Failed to compute metrics: {e}")
            return {}

    def store_metrics(self, run_date: date, metrics: Dict):
        """Store computed metrics to algo_metrics table."""
        try:
            cursor = self.conn.cursor()
            cursor.execute("""
                INSERT INTO algo_metrics_daily
                (date, total_actions, entries, exits, avg_signal_score)
                VALUES (%s, %s, %s, %s, %s)
                ON CONFLICT (date) DO UPDATE SET
                    total_actions = EXCLUDED.total_actions,
                    entries = EXCLUDED.entries,
                    exits = EXCLUDED.exits,
                    avg_signal_score = EXCLUDED.avg_signal_score
            """, (
                run_date,
                metrics.get('total_actions', 0),
                metrics.get('entries', 0),
                metrics.get('exits', 0),
                metrics.get('avg_signal_score', 0.0)
            ))
            self.conn.commit()
            logger.info(f"Stored metrics for {run_date}: {metrics}")
        except Exception as e:
            self.conn.rollback()
            logger.error(f"Failed to store metrics: {e}")
            raise


def main():
    from algo.algo_market_calendar import MarketCalendar
    from datetime import timedelta

    load_env()
    run_date = date.today()
    # If today is not a trading day, use yesterday instead
    # (prevents computing metrics for non-trading days when no new data exists)
    while run_date > date(2020, 1, 1) and not MarketCalendar.is_trading_day(run_date):
        run_date = run_date - timedelta(days=1)

    loader = AlgoMetricsDailyLoader()

    try:
        loader.connect()
        loader.ensure_table_exists()
        metrics = loader.compute_daily_metrics(run_date)
        loader.store_metrics(run_date, metrics)
        logger.info(f"Daily metrics computed and stored for {run_date}")
    finally:
        loader.disconnect()


if __name__ == '__main__':
    main()
