#!/usr/bin/env python3
"""
Continuous Critical Monitoring — Run key checks every 15 minutes

During market hours, runs critical-path patrol checks (P1, P3, P7, P9) every 15 minutes.
Catches data issues faster than daily patrol. Alerts immediately on problems.

Usage:
  python3 algo_continuous_monitor.py                  # run until market close
  python3 algo_continuous_monitor.py --once          # run once and exit
  python3 algo_continuous_monitor.py --interval 300  # custom interval (seconds)
"""

import os
import sys
import time
import argparse
import psycopg2
import json
from pathlib import Path
from dotenv import load_dotenv
from datetime import datetime, date as _date
from algo_market_calendar import MarketCalendar

env_file = Path(__file__).parent / '.env.local'
if env_file.exists():
    load_dotenv(env_file)

DB_CONFIG = {
    "host": os.getenv("DB_HOST", "localhost"),
    "port": int(os.getenv("DB_PORT", 5432)),
    "user": os.getenv("DB_USER", "stocks"),
    "password": os.getenv("DB_PASSWORD", ""),
    "database": os.getenv("DB_NAME", "stocks"),
}


class ContinuousMonitor:
    """Run critical checks continuously."""

    def __init__(self, interval_seconds=900):
        self.interval = interval_seconds  # default 15 minutes
        self.conn = None
        self.cur = None
        self.run_count = 0

    def connect(self):
        self.conn = psycopg2.connect(**DB_CONFIG)
        self.cur = self.conn.cursor()

    def disconnect(self):
        if self.cur:
            self.cur.close()
        if self.conn:
            self.conn.close()

    def run_once(self):
        """Run critical checks once."""
        self.connect()
        try:
            self.run_count += 1
            now = datetime.now()
            status = MarketCalendar.market_status(now)

            print(f"\n[{now.strftime('%H:%M:%S')}] Continuous Monitor Run #{self.run_count}")
            print(f"  Market: {status['status']} - {status.get('reason', '')}")

            if not status['is_open']:
                print(f"  Skipping — market closed")
                return

            # Run critical checks
            issues = self._check_critical_path()

            if issues['critical_count'] > 0:
                print(f"  🚨 CRITICAL: {issues['critical_count']} issues")
                # Send alert
                self._alert_critical(issues)
            elif issues['error_count'] > 0:
                print(f"  ⚠️  ERROR: {issues['error_count']} issues")
            else:
                print(f"  ✓ All critical checks passed")

            self._log_run(issues)
        except Exception as e:
            print(f"  ERROR: {e}")
            import traceback
            traceback.print_exc()
        finally:
            self.disconnect()

    def _check_critical_path(self):
        """Run P1, P3, P7, P9 (critical path checks)."""
        issues = {
            'staleness': [],
            'zeros': [],
            'coverage': [],
            'constraints': [],
            'critical_count': 0,
            'error_count': 0,
        }

        # P1: Staleness
        self.cur.execute("""
            SELECT
                (SELECT MAX(date) FROM price_daily) AS price_latest,
                CURRENT_DATE - (SELECT MAX(date)::date FROM price_daily) AS age_days
        """)
        row = self.cur.fetchone()
        if row and row[1]:
            age = int(row[1])
            if age > 7:
                issues['staleness'].append(f"price_daily {age}d old")
                issues['error_count'] += 1

        # P3: Zero/identical
        self.cur.execute("""
            SELECT COUNT(*) FROM price_daily
            WHERE date = (SELECT MAX(date) FROM price_daily)
              AND (volume = 0 OR open = 0 OR close = 0)
        """)
        zero_count = int(self.cur.fetchone()[0] or 0)
        if zero_count > 30:
            issues['zeros'].append(f"{zero_count} symbols with zero OHLC")
            issues['error_count'] += 1

        # P7: Universe coverage
        self.cur.execute("""
            SELECT
                (SELECT COUNT(DISTINCT symbol) FROM price_daily
                   WHERE date = (SELECT MAX(date) FROM price_daily)) AS today_count,
                (SELECT COUNT(DISTINCT symbol) FROM price_daily) AS total_count
        """)
        row = self.cur.fetchone()
        if row:
            today, total = int(row[0] or 0), int(row[1] or 1)
            pct = (today / total * 100) if total else 0
            if pct < 90:
                issues['coverage'].append(f"Only {pct:.1f}% of universe updated")
                issues['error_count'] += 1

        # P9: Constraints
        self.cur.execute("""
            SELECT COUNT(*) FROM price_daily
            WHERE date = (SELECT MAX(date) FROM price_daily)
              AND (symbol IS NULL OR date IS NULL)
        """)
        constraint_count = int(self.cur.fetchone()[0] or 0)
        if constraint_count > 0:
            issues['constraints'].append(f"{constraint_count} NULL constraint violations")
            issues['critical_count'] += 1

        return issues

    def _alert_critical(self, issues):
        """Send alert on critical findings."""
        try:
            from algo_alerts import AlertManager
            alerts = AlertManager()
            alerts.send_patrol_alert(
                f"CONTINUOUS-{datetime.now().strftime('%Y%m%d-%H%M%S')}",
                {'critical': issues['critical_count'], 'error': issues['error_count'], 'warn': 0, 'info': 0},
                [
                    {'check': 'continuous_monitor', 'severity': 'critical' if issues['critical_count'] > 0 else 'error',
                     'target': 'price_daily', 'message': f"{issues['critical_count']} critical, {issues['error_count']} error"}
                ]
            )
        except Exception as e:
            print(f"    (alert failed: {e})")

    def _log_run(self, issues):
        """Log continuous monitor run."""
        try:
            self.cur.execute("""
                INSERT INTO algo_audit_log (action_type, action_date, details, actor, status, created_at)
                VALUES ('continuous_monitor', CURRENT_TIMESTAMP, %s, 'continuous_monitor',
                        %s, CURRENT_TIMESTAMP)
            """,
            (
                json.dumps(issues),
                'HALT' if issues['critical_count'] > 0 else ('ERROR' if issues['error_count'] > 0 else 'OK'),
            ))
            self.conn.commit()
        except Exception:
            pass

    def run_continuous(self):
        """Run checks continuously until market close."""
        print(f"\nContinuous Monitor Started")
        print(f"Interval: {self.interval}s ({self.interval/60:.0f} min)")
        print(f"Running during market hours only\n")

        try:
            while True:
                # Check if market is open
                if not MarketCalendar.is_market_open():
                    next_trading = MarketCalendar.get_next_trading_day()
                    print(f"\n[{datetime.now().strftime('%H:%M:%S')}] Market closed")
                    print(f"Next trading day: {next_trading}")
                    print("Exiting continuous monitor\n")
                    break

                self.run_once()

                # Wait for next interval
                print(f"  Next check in {self.interval}s... (Ctrl+C to exit)")
                time.sleep(self.interval)

        except KeyboardInterrupt:
            print(f"\n\nContinuous monitor stopped by user")
        except Exception as e:
            print(f"\nFatal error: {e}")
            import traceback
            traceback.print_exc()


if __name__ == '__main__':
    parser = argparse.ArgumentParser(description='Continuous critical monitoring')
    parser.add_argument('--once', action='store_true', help='Run once and exit')
    parser.add_argument('--interval', type=int, default=900, help='Interval in seconds (default 900 = 15 min)')
    args = parser.parse_args()

    monitor = ContinuousMonitor(interval_seconds=args.interval)

    if args.once:
        monitor.run_once()
    else:
        monitor.run_continuous()
