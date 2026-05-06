#!/usr/bin/env python3
"""
Quality Trend Analysis — Detect data quality degradation over time

Analyzes patrol findings across 7/30/90 day windows to detect:
  - Increasing error rates (systemic issues emerging)
  - Recurring problems (same check failing repeatedly)
  - Pattern shifts (suddenly more NULL anomalies? More stale data?)

Run weekly to monitor system health.
"""

import os
import json
import psycopg2
from pathlib import Path
from dotenv import load_dotenv
from datetime import datetime, timedelta

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


class QualityTrendAnalyzer:
    """Analyze patrol findings over time."""

    def __init__(self):
        self.conn = None
        self.cur = None

    def connect(self):
        self.conn = psycopg2.connect(**DB_CONFIG)
        self.cur = self.conn.cursor()

    def disconnect(self):
        if self.cur:
            self.cur.close()
        if self.conn:
            self.conn.close()
        self.cur = self.conn = None

    def analyze(self, days=7):
        """Analyze quality trends over past N days.

        Args:
            days: 7 (weekly), 30 (monthly), 90 (quarterly)

        Returns:
            dict with trend metrics and alerts
        """
        self.connect()
        try:
            print(f"\n{'='*70}")
            print(f"QUALITY TREND ANALYSIS — Last {days} days")
            print(f"{'='*70}\n")

            start_date = datetime.now() - timedelta(days=days)

            # Get all findings in window
            self.cur.execute("""
                SELECT severity, check_name, COUNT(*) as count
                FROM data_patrol_log
                WHERE created_at >= %s
                GROUP BY severity, check_name
                ORDER BY count DESC
            """, (start_date,))
            findings = self.cur.fetchall()

            # Aggregate by severity
            severity_counts = {}
            for sev, check, count in findings:
                if sev not in severity_counts:
                    severity_counts[sev] = {'total': 0, 'checks': {}}
                severity_counts[sev]['total'] += count
                severity_counts[sev]['checks'][check] = count

            print(f"Findings by severity:")
            total_findings = 0
            for sev in ['critical', 'error', 'warn', 'info']:
                if sev in severity_counts:
                    count = severity_counts[sev]['total']
                    total_findings += count
                    pct = (count / (total_findings + count)) * 100 if total_findings else 0
                    print(f"  {sev.upper():8s}: {count:4d}")
                    # Show top checks
                    checks = sorted(severity_counts[sev]['checks'].items(),
                                  key=lambda x: x[1], reverse=True)[:3]
                    for check, check_count in checks:
                        print(f"           └─ {check}: {check_count}")

            # Trend comparison: is it getting better or worse?
            print(f"\nTrend Analysis:")
            trend = self._compute_trend(start_date, days)
            if trend['getting_worse']:
                print(f"  ⚠️  QUALITY DEGRADING")
                print(f"      {trend['error_increase']}% more errors vs previous period")
                print(f"      Top recurrence: {trend['top_repeat']}")
            elif trend['stable']:
                print(f"  → Stable")
            else:
                print(f"  ✓ Improving")

            # Check for patterns
            print(f"\nRecurring Issues (appeared >3x in period):")
            recurring = {}
            for sev, check, count in findings:
                if count >= 3 and sev in ['error', 'critical']:
                    recurring[check] = count
            if recurring:
                for check, count in sorted(recurring.items(), key=lambda x: x[1], reverse=True):
                    print(f"  • {check}: {count} times")
            else:
                print(f"  (none)")

            # Recommendations
            print(f"\nRecommendations:")
            if severity_counts.get('critical', {}).get('total', 0) > 0:
                print(f"  1. CRITICAL findings active — investigate root cause immediately")
            if trend.get('error_increase', 0) > 20:
                print(f"  2. Errors increasing {trend['error_increase']}% — system degrading")
            if len(recurring) > 2:
                print(f"  3. {len(recurring)} checks consistently failing — needs structural fix")
            if total_findings < 5:
                print(f"  ✓ System healthy — few issues detected")

            print(f"\n{'='*70}\n")

            return {
                'period_days': days,
                'total_findings': total_findings,
                'severity_counts': severity_counts,
                'recurring_issues': recurring,
                'trend': trend,
            }

        finally:
            self.disconnect()

    def _compute_trend(self, start_date, current_period_days):
        """Compare current period to previous period."""
        prev_start = start_date - timedelta(days=current_period_days)

        # Current period errors
        self.cur.execute("""
            SELECT COUNT(*)
            FROM data_patrol_log
            WHERE created_at >= %s AND severity IN ('error', 'critical')
        """, (start_date,))
        current_errors = self.cur.fetchone()[0] or 0

        # Previous period errors
        self.cur.execute("""
            SELECT COUNT(*)
            FROM data_patrol_log
            WHERE created_at >= %s AND created_at < %s
              AND severity IN ('error', 'critical')
        """, (prev_start, start_date))
        prev_errors = self.cur.fetchone()[0] or 1  # avoid divide by zero

        error_increase = ((current_errors - prev_errors) / prev_errors * 100) if prev_errors else 0

        # Most repeated check
        self.cur.execute("""
            SELECT check_name, COUNT(*) as count
            FROM data_patrol_log
            WHERE created_at >= %s AND severity IN ('error', 'critical')
            GROUP BY check_name
            ORDER BY count DESC LIMIT 1
        """, (start_date,))
        top_repeat = self.cur.fetchone()
        top_repeat_name = f"{top_repeat[0]} ({top_repeat[1]}x)" if top_repeat else "none"

        return {
            'error_increase': round(error_increase, 1),
            'getting_worse': error_increase > 20,
            'stable': -20 <= error_increase <= 20,
            'top_repeat': top_repeat_name,
        }


if __name__ == '__main__':
    import argparse
    parser = argparse.ArgumentParser(description='Quality trend analysis')
    parser.add_argument('--days', type=int, default=7, help='Analysis window (7/30/90)')
    args = parser.parse_args()

    analyzer = QualityTrendAnalyzer()
    result = analyzer.analyze(days=args.days)

    import sys
    # Exit with warning if quality degrading
    sys.exit(1 if result['trend']['getting_worse'] else 0)
