#!/usr/bin/env python3
"""SLA Monitoring for Stock Scores - Track 99.95% coverage goal.

Checks:
1. Total stocks with scores (target: 99.95% of active universe)
2. Average data completeness (target: 60%+)
3. Freshness of price data (must be from the most recent trading day)
4. Score distribution (reasonable spread across stocks)

Alerts if any metric falls below SLA threshold.
"""
import sys
from pathlib import Path
sys.path.insert(0, str(Path(__file__).parent.parent))

from utils.database_context import DatabaseContext
from datetime import datetime, timedelta
import logging

logger = logging.getLogger(__name__)

# SLA THRESHOLDS
COVERAGE_SLA_PCT = 0.9995            # 99.95% of actual stock universe
MIN_AVG_COMPLETENESS = 60.0          # Average data completeness %

class StockScoresSLAMonitor:
    def __init__(self):
        self.conn = get_db_connection()
        self.alerts = []

    def check_coverage(self):
        """Check: Do we have 99.95%+ coverage of all active stock symbols?"""
        cur = self.conn.cursor()
        cur.execute('SELECT COUNT(*) FROM stock_scores WHERE composite_score > 0')
        scored = cur.fetchone()[0]
        cur.execute('SELECT COUNT(*) FROM stock_symbols')
        total = cur.fetchone()[0] or 1
        cur.close()

        pct = scored * 100 / total if total else 0
        target_count = round(total * COVERAGE_SLA_PCT)
        status = 'PASS' if scored >= target_count else 'FAIL'
        print(f'[{status}] Coverage: {scored:,}/{total:,} stocks ({pct:.2f}%) target={target_count:,}')

        if scored < target_count:
            self.alerts.append(f'CRITICAL: Stock coverage below SLA ({scored:,} vs target {target_count:,} = {COVERAGE_SLA_PCT*100:.2f}%)')

        return scored >= target_count

    def check_completeness(self):
        """Check: Average data completeness >= 60%?"""
        cur = self.conn.cursor()
        cur.execute('SELECT AVG(data_completeness) FROM stock_scores WHERE composite_score > 0')
        row = cur.fetchone()
        cur.close()

        avg_completeness = float(row[0]) if row and row[0] is not None else None

        if avg_completeness is None:
            print('[WARN] Avg Completeness: no scored stocks found')
            self.alerts.append('WARNING: No scored stocks — stock_scores table may be empty')
            return False

        status = 'PASS' if avg_completeness >= MIN_AVG_COMPLETENESS else 'WARN'
        print(f'[{status}] Avg Completeness: {avg_completeness:.1f}% (target: {MIN_AVG_COMPLETENESS}%)')

        if avg_completeness < MIN_AVG_COMPLETENESS:
            self.alerts.append(f'WARNING: Avg completeness low ({avg_completeness:.1f}% vs target {MIN_AVG_COMPLETENESS}%)')

        return avg_completeness >= MIN_AVG_COMPLETENESS

    def check_price_freshness(self):
        """Check: Most recent price data is from the last trading day?

        Compares against the most recent expected trading day rather than a fixed
        calendar-hour window. This prevents false FAILs on weekends and holidays
        where market data is correctly absent (markets closed).
        """
        cur = self.conn.cursor()
        cur.execute('SELECT MAX(date) FROM price_daily')
        max_date = cur.fetchone()[0]
        cur.close()

        if max_date:
            # Find most recent expected trading day (yesterday or earlier)
            expected_date = datetime.now().date() - timedelta(days=1)
            try:
                from algo.algo_market_calendar import MarketCalendar
                for _ in range(10):
                    if MarketCalendar.is_trading_day(expected_date):
                        break
                    expected_date -= timedelta(days=1)
            except Exception:
                # Fallback: skip weekends only (ignores holidays)
                for _ in range(10):
                    if expected_date.weekday() < 5:
                        break
                    expected_date -= timedelta(days=1)

            is_fresh = max_date >= expected_date
            age_days = (datetime.now().date() - max_date).days
            status = 'PASS' if is_fresh else 'FAIL'
            print(f'[{status}] Price Freshness: latest={max_date} expected>={expected_date} ({age_days}d old)')

            if not is_fresh:
                self.alerts.append(f'ALERT: Prices stale (latest={max_date}, expected>={expected_date})')

            return is_fresh

        print('[FAIL] Price Freshness: no data in price_daily')
        self.alerts.append('ALERT: price_daily table has no data')
        return False

    def check_score_distribution(self):
        """Check: Scores reasonably distributed (not all same value)?"""
        cur = self.conn.cursor()
        cur.execute('''
            SELECT
                MIN(composite_score), MAX(composite_score),
                STDDEV(composite_score),
                COUNT(*)
            FROM stock_scores WHERE composite_score > 0
        ''')
        row = cur.fetchone()
        cur.close()

        if not row or row[3] == 0:
            print('[WARN] Score Distribution: no scored stocks found')
            self.alerts.append('WARNING: No scored stocks in stock_scores')
            return False

        min_s, max_s, stddev, count = row
        min_s = float(min_s) if min_s is not None else 0.0
        max_s = float(max_s) if max_s is not None else 0.0
        stddev = float(stddev) if stddev is not None else 0.0

        spread = max_s - min_s
        status = 'PASS' if spread > 10 else 'WARN'
        print(f'[{status}] Score Distribution: {min_s:.2f}-{max_s:.2f} (stddev: {stddev:.2f})')

        if spread < 10:
            self.alerts.append(f'WARNING: Low score spread ({spread:.2f} - possible data issue)')

        return True

    def run_full_check(self):
        """Run all SLA checks."""
        print()
        print('=' * 70)
        print(f'STOCK SCORES SLA CHECK - {datetime.now().strftime("%Y-%m-%d %H:%M:%S")}')
        print('=' * 70)
        print()

        self.check_coverage()
        self.check_completeness()
        self.check_price_freshness()
        self.check_score_distribution()

        print()
        print('=' * 70)
        if self.alerts:
            print(f'ALERTS ({len(self.alerts)}):')
            for alert in self.alerts:
                print(f'  [ALERT] {alert}')
            print()
            return 1
        else:
            print('[OK] ALL CHECKS PASSED - SLA COMPLIANT')
            print()
            return 0

    def close(self):
        self.conn.close()


if __name__ == '__main__':
    monitor = StockScoresSLAMonitor()
    try:
        exit_code = monitor.run_full_check()
    finally:
        monitor.close()

    sys.exit(exit_code)
