"""
Transaction Cost Analysis (TCA) — Execution quality measurement.

Measures every fill against its signal price (arrival price) to quantify:
- Slippage per trade (signal_price vs executed_price)
- Fill rate (shares requested vs filled)
- Execution latency (order send → fill confirmation)
- Cumulative cost of execution friction

Alerts if slippage exceeds thresholds:
- 100 bps (1% adverse): WARN
- 300 bps (3% adverse): ERROR

This is what institutional traders use to validate their edge isn't eroded by fees/slippage.
"""

import psycopg2
from datetime import datetime, date
from typing import Optional
import os
from dotenv import load_dotenv
from pathlib import Path

env_file = Path(__file__).parent / '.env.local'
if env_file.exists():
    load_dotenv(env_file)


class TCAEngine:
    """Transaction Cost Analysis for every trade execution."""

    def __init__(self, config):
        self.config = config
        self.conn = None
        self.cur = None

        self.db_host = os.getenv('DB_HOST', 'localhost')
        self.db_port = int(os.getenv('DB_PORT', 5432))
        self.db_user = os.getenv('DB_USER', 'stocks')
        self.db_password = os.getenv('DB_PASSWORD', '')
        self.db_name = os.getenv('DB_NAME', 'stocks')

    def connect(self):
        """Connect to database."""
        try:
            self.conn = psycopg2.connect(
                host=self.db_host,
                port=self.db_port,
                user=self.db_user,
                password=self.db_password,
                database=self.db_name,
            )
            self.cur = self.conn.cursor()
        except Exception as e:
            print(f"TCA: DB connection failed: {e}")
            raise

    def disconnect(self):
        """Disconnect from database."""
        if self.cur:
            self.cur.close()
        if self.conn:
            self.conn.close()
        self.cur = self.conn = None

    def record_fill(self, trade_id: int, symbol: str, signal_price: float,
                   fill_price: float, shares_requested: int, shares_filled: int,
                   side: str = 'BUY', execution_latency_ms: Optional[int] = None):
        """Record a fill and compute slippage metrics.

        Args:
            trade_id: Foreign key to algo_trades
            symbol: Stock symbol
            signal_price: Entry price from signal (arrival price)
            fill_price: Actual executed price from Alpaca
            shares_requested: Target quantity
            shares_filled: Actual filled quantity
            side: BUY or SELL
            execution_latency_ms: Order send → fill confirmation time in ms

        Returns:
            dict with tca_id, slippage_bps, fill_rate, etc.
        """
        try:
            if not self.cur:
                self.connect()

            # Compute slippage in basis points
            if side == 'BUY':
                # For buy, adverse if fill_price > signal_price
                slippage_bps = (fill_price - signal_price) / signal_price * 10000
            else:
                # For sell, adverse if fill_price < signal_price
                slippage_bps = (signal_price - fill_price) / signal_price * 10000

            # Compute fill rate
            fill_rate_pct = (shares_filled / shares_requested * 100) if shares_requested > 0 else 0

            # Insert into algo_tca table
            self.cur.execute(
                """
                INSERT INTO algo_tca (
                    trade_id, symbol, signal_date, signal_price, fill_price,
                    shares_requested, shares_filled, fill_rate_pct,
                    slippage_bps, side, execution_latency_ms
                )
                VALUES (%s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s)
                RETURNING tca_id
                """,
                (trade_id, symbol, date.today(), signal_price, fill_price,
                 shares_requested, shares_filled, round(fill_rate_pct, 2),
                 round(slippage_bps, 2), side, execution_latency_ms)
            )
            tca_id = self.cur.fetchone()[0]
            self.conn.commit()

            result = {
                'tca_id': tca_id,
                'symbol': symbol,
                'signal_price': signal_price,
                'fill_price': fill_price,
                'slippage_bps': round(slippage_bps, 2),
                'fill_rate_pct': round(fill_rate_pct, 2),
                'execution_latency_ms': execution_latency_ms,
            }

            # Check slippage thresholds and alert if needed
            alert = self._check_slippage_alert(symbol, slippage_bps, side)
            if alert:
                result['alert'] = alert

            return result
        except Exception as e:
            self.conn.rollback() if self.conn else None
            print(f"TCA: record_fill failed: {e}")
            raise

    def _check_slippage_alert(self, symbol: str, slippage_bps: float,
                             side: str) -> Optional[dict]:
        """Check if slippage exceeds alert thresholds.

        Returns:
            dict with severity, message if alert triggered, else None
        """
        # Only alert on adverse slippage (positive for buy)
        if side == 'BUY' and slippage_bps <= 0:
            return None  # Favorable, no alert
        if side == 'SELL' and slippage_bps <= 0:
            return None  # Favorable, no alert

        abs_slippage = abs(slippage_bps)

        if abs_slippage >= 300:  # 3% adverse
            return {
                'severity': 'ERROR',
                'message': f'{symbol} excessive slippage: {abs_slippage:.0f} bps (3%+ adverse)',
                'slippage_bps': slippage_bps,
            }
        elif abs_slippage >= 100:  # 1% adverse
            return {
                'severity': 'WARN',
                'message': f'{symbol} high slippage: {abs_slippage:.0f} bps (1%+ adverse)',
                'slippage_bps': slippage_bps,
            }

        return None

    def daily_report(self, report_date: Optional[date] = None) -> dict:
        """Generate daily TCA report.

        Args:
            report_date: Date to report on (default today)

        Returns:
            dict with daily metrics: avg slippage, worst fills, alert count, etc.
        """
        try:
            if not self.cur:
                self.connect()

            if not report_date:
                report_date = date.today()

            self.cur.execute(
                """
                SELECT
                    COUNT(*) as fill_count,
                    AVG(ABS(slippage_bps)) as avg_abs_slippage_bps,
                    MIN(slippage_bps) as best_slippage_bps,
                    MAX(slippage_bps) as worst_slippage_bps,
                    AVG(fill_rate_pct) as avg_fill_rate_pct,
                    AVG(execution_latency_ms) as avg_latency_ms
                FROM algo_tca
                WHERE signal_date = %s
                """,
                (report_date,)
            )
            row = self.cur.fetchone()

            if not row or row[0] == 0:
                return {
                    'report_date': report_date,
                    'fill_count': 0,
                    'status': 'no_trades',
                }

            (fill_count, avg_abs_slippage, best_slippage, worst_slippage,
             avg_fill_rate, avg_latency) = row

            # Count adverse fills > 100 bps
            self.cur.execute(
                """
                SELECT COUNT(*) FROM algo_tca
                WHERE signal_date = %s AND ABS(slippage_bps) > 100
                """,
                (report_date,)
            )
            high_slippage_count = self.cur.fetchone()[0]

            # Get worst symbol
            self.cur.execute(
                """
                SELECT symbol, ABS(slippage_bps) FROM algo_tca
                WHERE signal_date = %s
                ORDER BY ABS(slippage_bps) DESC
                LIMIT 1
                """,
                (report_date,)
            )
            worst_row = self.cur.fetchone()
            worst_symbol = worst_row[0] if worst_row else None

            return {
                'report_date': report_date,
                'fill_count': fill_count,
                'avg_abs_slippage_bps': round(avg_abs_slippage or 0, 2),
                'best_slippage_bps': round(best_slippage or 0, 2),
                'worst_slippage_bps': round(worst_slippage or 0, 2),
                'worst_symbol': worst_symbol,
                'high_slippage_fills': high_slippage_count,
                'high_slippage_pct': round(high_slippage_count / fill_count * 100 if fill_count > 0 else 0, 1),
                'avg_fill_rate_pct': round(avg_fill_rate or 0, 2),
                'avg_execution_latency_ms': round(avg_latency or 0),
                'status': 'ok' if high_slippage_count == 0 else 'warning',
            }
        except Exception as e:
            print(f"TCA: daily_report failed: {e}")
            return {'status': 'error', 'message': str(e)}

    def monthly_summary(self, year: int, month: int) -> dict:
        """Generate monthly TCA summary.

        Args:
            year: Year (e.g., 2026)
            month: Month (1-12)

        Returns:
            Monthly aggregated metrics
        """
        try:
            if not self.cur:
                self.connect()

            self.cur.execute(
                """
                SELECT
                    COUNT(*) as fill_count,
                    AVG(ABS(slippage_bps)) as avg_abs_slippage_bps,
                    PERCENTILE_CONT(0.95) WITHIN GROUP (ORDER BY ABS(slippage_bps))
                        as p95_abs_slippage_bps,
                    MAX(ABS(slippage_bps)) as worst_slippage_bps,
                    AVG(fill_rate_pct) as avg_fill_rate_pct,
                    SUM(CASE WHEN ABS(slippage_bps) > 100 THEN 1 ELSE 0 END)
                        as high_slippage_count
                FROM algo_tca
                WHERE EXTRACT(YEAR FROM signal_date) = %s
                  AND EXTRACT(MONTH FROM signal_date) = %s
                """,
                (year, month)
            )
            row = self.cur.fetchone()

            if not row or row[0] == 0:
                return {
                    'period': f'{year}-{month:02d}',
                    'status': 'no_trades',
                }

            (fill_count, avg_abs_slippage, p95_slippage, worst_slippage,
             avg_fill_rate, high_slippage_count) = row

            return {
                'period': f'{year}-{month:02d}',
                'fill_count': fill_count,
                'avg_abs_slippage_bps': round(avg_abs_slippage or 0, 2),
                'p95_abs_slippage_bps': round(p95_slippage or 0, 2),
                'worst_slippage_bps': round(worst_slippage or 0, 2),
                'avg_fill_rate_pct': round(avg_fill_rate or 0, 2),
                'high_slippage_fills': high_slippage_count or 0,
                'high_slippage_pct': round((high_slippage_count or 0) / fill_count * 100, 1),
                'status': 'ok' if (high_slippage_count or 0) == 0 else 'warning',
            }
        except Exception as e:
            print(f"TCA: monthly_summary failed: {e}")
            return {'status': 'error', 'message': str(e)}
