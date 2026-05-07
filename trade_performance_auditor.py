#!/usr/bin/env python3
"""
Trade Performance Attribution & Win Rate Analysis

On trade exit:
1. Populate signal_trade_performance table
2. Link trade -> signal metadata (base_type, SQS, swing_score, stage, sector)
3. Calculate realized P&L, R-multiple, hold duration
4. Record which targets were hit

Enables analytics:
- Win rate by base type: Cups 85%, Flat 70%, Double 60%
- Avg R by swing score: SQS 80+ avg 1.5R, SQS 60-79 avg 0.8R
- Best sector: Tech 80% win rate
"""

import os
import psycopg2
from pathlib import Path
from dotenv import load_dotenv
from datetime import datetime
import logging

env_file = Path(__file__).parent / '.env.local'
if env_file.exists():
    load_dotenv(env_file)

logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s [%(levelname)s] %(name)s: %(message)s",
)
log = logging.getLogger(__name__)

DB_CONFIG = {
    "host": os.getenv("DB_HOST", "localhost"),
    "port": int(os.getenv("DB_PORT", 5432)),
    "user": os.getenv("DB_USER", "stocks"),
    "password": os.getenv("DB_PASSWORD", ""),
    "database": os.getenv("DB_NAME", "stocks"),
}


class TradePerformanceAuditor:
    """Track trade performance and link back to signal metadata."""

    def __init__(self, config=None):
        self.config = config or {}
        self.conn = None
        self.cur = None

    def connect(self):
        """Connect to database."""
        if not self.conn:
            self.conn = psycopg2.connect(**DB_CONFIG)
            self.cur = self.conn.cursor()

    def disconnect(self):
        """Disconnect from database."""
        if self.cur:
            self.cur.close()
        if self.conn:
            self.conn.close()
        self.cur = self.conn = None

    def audit_exit(self, trade_id):
        """
        Called when a position exits.
        Populate signal_trade_performance with full context.

        Args:
            trade_id: ID from algo_trades table
        """
        self.connect()

        try:
            # Fetch trade record
            self.cur.execute("""
                SELECT id, symbol, signal_date, entry_price, entry_quantity,
                       stop_loss_price, exit_date, exit_price,
                       profit_loss_dollars, profit_loss_pct,
                       target_1_price, target_2_price, target_3_price
                FROM algo_trades WHERE id = %s
            """, (trade_id,))
            trade = self.cur.fetchone()

            if not trade:
                log.warning(f"Trade {trade_id} not found")
                self.disconnect()
                return

            (tid, symbol, sig_date, entry, qty, stop, exit_date, exit_price,
             pnl, pnl_pct, t1, t2, t3) = trade

            # Fetch signal metadata from buy_sell_daily and related tables
            self.cur.execute("""
                SELECT
                    bsd.base_type,
                    sqs.composite_sqs,
                    sts.score,
                    sts.components->>'grade' as grade,
                    tmt.minervini_trend_score,
                    tmt.weinstein_stage,
                    ss.sector,
                    tmt.percent_from_52w_high
                FROM buy_sell_daily bsd
                LEFT JOIN signal_quality_scores sqs
                    ON bsd.symbol = sqs.symbol AND bsd.date = sqs.date
                LEFT JOIN swing_trader_scores sts
                    ON bsd.symbol = sts.symbol AND bsd.date = sts.date
                LEFT JOIN trend_template_data tmt
                    ON bsd.symbol = tmt.symbol AND bsd.date = tmt.date
                LEFT JOIN stock_symbols ss
                    ON bsd.symbol = ss.symbol
                WHERE bsd.symbol = %s AND bsd.date = %s AND bsd.signal = 'BUY'
                LIMIT 1
            """, (symbol, sig_date))
            sig_meta = self.cur.fetchone()

            if not sig_meta:
                log.debug(f"No signal metadata for {symbol} on {sig_date}")
                self.disconnect()
                return

            (base_type, sqs, swing_score, swing_grade, trend_score,
             stage, sector, rs_pct) = sig_meta

            # Compute R-multiple (realized profit / risk)
            r_mult = 0.0
            if stop and entry and exit_price:
                risk = entry - stop
                realized = exit_price - entry
                if risk > 0:
                    r_mult = realized / risk

            # Determine which targets were hit
            target_1_hit = (exit_price >= t1) if t1 else False
            target_2_hit = (exit_price >= t2) if t2 else False
            target_3_hit = (exit_price >= t3) if t3 else False

            # Compute hold duration
            hold_days = (exit_date - sig_date).days if exit_date and sig_date else 0

            # Insert or update signal_trade_performance
            self.cur.execute("""
                INSERT INTO signal_trade_performance
                (trade_id, symbol, signal_date, entry_price, base_type, sqs,
                 swing_score, swing_grade, trend_score, stage_at_entry, sector,
                 rs_percentile, exit_price, exit_date, hold_days,
                 realized_pnl, realized_pnl_pct, r_multiple, win,
                 target_1_hit, target_2_hit, target_3_hit, updated_at)
                VALUES (%s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, NOW())
                ON CONFLICT (trade_id) DO UPDATE SET
                    exit_price = EXCLUDED.exit_price,
                    exit_date = EXCLUDED.exit_date,
                    realized_pnl = EXCLUDED.realized_pnl,
                    realized_pnl_pct = EXCLUDED.realized_pnl_pct,
                    r_multiple = EXCLUDED.r_multiple,
                    win = EXCLUDED.win,
                    target_1_hit = EXCLUDED.target_1_hit,
                    target_2_hit = EXCLUDED.target_2_hit,
                    target_3_hit = EXCLUDED.target_3_hit,
                    updated_at = NOW()
            """, (
                trade_id, symbol, sig_date, entry, base_type, sqs,
                float(swing_score) if swing_score else None,
                swing_grade, trend_score, stage, sector,
                int(rs_pct) if rs_pct else None,
                exit_price, exit_date, hold_days, pnl, pnl_pct,
                float(r_mult), pnl > 0 if pnl else False,
                target_1_hit, target_2_hit, target_3_hit
            ))

            self.conn.commit()
            log.info(f"Audited trade {trade_id}: {symbol} R={r_mult:.2f} "
                    f"PnL=${pnl:.2f} ({pnl_pct:.2f}%)")

        except Exception as e:
            log.error(f"Failed to audit trade {trade_id}: {e}")
            self.conn.rollback()

        finally:
            self.disconnect()

    def get_win_rate_by_base_type(self, days=90):
        """
        Get win rate analysis by base type.

        Returns:
            list of dicts: [
                {'base_type': 'Cup', 'trades': 10, 'wins': 9, 'win_rate_pct': 90.0, 'avg_r': 1.5},
                ...
            ]
        """
        self.connect()

        try:
            self.cur.execute("""
                SELECT
                    base_type,
                    COUNT(*) as total_trades,
                    SUM(CASE WHEN win THEN 1 ELSE 0 END) as wins,
                    ROUND(100.0 * SUM(CASE WHEN win THEN 1 ELSE 0 END) / COUNT(*), 1) as win_rate_pct,
                    ROUND(AVG(r_multiple), 2) as avg_r
                FROM signal_trade_performance
                WHERE exit_date >= NOW()::DATE - INTERVAL %s
                  AND base_type IS NOT NULL
                GROUP BY base_type
                ORDER BY win_rate_pct DESC
            """, (f'{days} days',))

            results = []
            for row in self.cur.fetchall():
                results.append({
                    'base_type': row[0],
                    'trades': row[1],
                    'wins': row[2],
                    'win_rate_pct': row[3],
                    'avg_r': row[4],
                })

            return results

        except Exception as e:
            log.error(f"Failed to get win rates: {e}")
            return []

        finally:
            self.disconnect()

    def get_win_rate_by_sqs(self, days=90):
        """
        Get win rate analysis by SQS score bucket.

        Returns:
            list of dicts: [
                {'sqs_bucket': '80-99', 'trades': 5, 'wins': 5, 'win_rate_pct': 100.0, 'avg_r': 2.1},
                ...
            ]
        """
        self.connect()

        try:
            self.cur.execute("""
                SELECT
                    CASE
                        WHEN sqs >= 80 THEN '80-99'
                        WHEN sqs >= 70 THEN '70-79'
                        WHEN sqs >= 60 THEN '60-69'
                        ELSE '< 60'
                    END as sqs_bucket,
                    COUNT(*) as total_trades,
                    SUM(CASE WHEN win THEN 1 ELSE 0 END) as wins,
                    ROUND(100.0 * SUM(CASE WHEN win THEN 1 ELSE 0 END) / COUNT(*), 1) as win_rate_pct,
                    ROUND(AVG(r_multiple), 2) as avg_r
                FROM signal_trade_performance
                WHERE exit_date >= NOW()::DATE - INTERVAL %s
                  AND sqs IS NOT NULL
                GROUP BY sqs_bucket
                ORDER BY sqs_bucket DESC
            """, (f'{days} days',))

            results = []
            for row in self.cur.fetchall():
                results.append({
                    'sqs_bucket': row[0],
                    'trades': row[1],
                    'wins': row[2],
                    'win_rate_pct': row[3],
                    'avg_r': row[4],
                })

            return results

        except Exception as e:
            log.error(f"Failed to get SQS win rates: {e}")
            return []

        finally:
            self.disconnect()
