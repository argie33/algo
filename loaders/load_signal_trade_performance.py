#!/usr/bin/env python3
"""
Load signal trade performance metrics.
Tracks how well signals predict price movements.
"""
import psycopg2
from datetime import datetime, timedelta
import logging
from db_utils import get_db_connection

logger = logging.getLogger(__name__)

def load_signal_trade_performance():
    """Load signal trade performance metrics."""
    conn = get_db_connection()
    cur = conn.cursor()

    try:
        # Clear old performance data
        cur.execute("""
            DELETE FROM signal_trade_performance
            WHERE created_at < NOW() - INTERVAL '180 days'
        """)

        # Calculate signal performance from actual trades
        # Join signal_quality_scores with trades to measure effectiveness
        cur.execute("""
            INSERT INTO signal_trade_performance (
                symbol, signal_date, win_count, loss_count, win_rate,
                avg_win, avg_loss, profit_factor, return_pct, created_at, updated_at
            )
            SELECT
                sqs.symbol,
                sqs.signal_date,
                COALESCE(SUM(CASE WHEN at.profit_loss > 0 THEN 1 ELSE 0 END), 0) AS win_count,
                COALESCE(SUM(CASE WHEN at.profit_loss <= 0 THEN 1 ELSE 0 END), 0) AS loss_count,
                ROUND(COALESCE(
                    100.0 * SUM(CASE WHEN at.profit_loss > 0 THEN 1 ELSE 0 END) /
                    NULLIF(COUNT(at.id), 0), 0
                )::numeric, 2) AS win_rate,
                ROUND(COALESCE(
                    AVG(CASE WHEN at.profit_loss > 0 THEN at.profit_loss ELSE NULL END),
                    0
                )::numeric, 2) AS avg_win,
                ROUND(ABS(COALESCE(
                    AVG(CASE WHEN at.profit_loss <= 0 THEN at.profit_loss ELSE NULL END),
                    0
                ))::numeric, 2) AS avg_loss,
                ROUND(COALESCE(
                    SUM(CASE WHEN at.profit_loss > 0 THEN ABS(at.profit_loss) ELSE 0 END) /
                    NULLIF(SUM(CASE WHEN at.profit_loss < 0 THEN ABS(at.profit_loss) ELSE 0 END), 0),
                    1.0
                )::numeric, 2) AS profit_factor,
                ROUND(COALESCE(
                    SUM(at.profit_loss) / NULLIF(COUNT(at.id), 0),
                    0
                )::numeric, 2) AS return_pct,
                NOW(),
                NOW()
            FROM signal_quality_scores sqs
            LEFT JOIN algo_trades at ON at.symbol = sqs.symbol
                AND at.entry_date >= sqs.signal_date
                AND at.entry_date < sqs.signal_date + INTERVAL '30 days'
            WHERE sqs.signal_date >= NOW() - INTERVAL '180 days'
            GROUP BY sqs.symbol, sqs.signal_date
            LIMIT 1000
            ON CONFLICT (symbol, signal_date) DO UPDATE SET
                win_count = EXCLUDED.win_count,
                loss_count = EXCLUDED.loss_count,
                win_rate = EXCLUDED.win_rate,
                avg_win = EXCLUDED.avg_win,
                avg_loss = EXCLUDED.avg_loss,
                profit_factor = EXCLUDED.profit_factor,
                return_pct = EXCLUDED.return_pct,
                updated_at = NOW()
        """)

        inserted = cur.rowcount
        conn.commit()
        logger.info(f"Loaded {inserted} signal trade performance records")
        return inserted

    except Exception as e:
        conn.rollback()
        logger.error(f"Error loading signal trade performance: {e}")
        raise
    finally:
        cur.close()
        conn.close()

if __name__ == "__main__":
    load_signal_trade_performance()
