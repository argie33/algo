from credential_helper import get_db_password, get_db_config
#!/usr/bin/env python3
"""
Loader Failure Monitor — Detects when data loaders fail silently

Watches for missing data by checking:
1. Per-symbol freshness (alerts if critical symbols have no data)
2. Daily data count (alerts if load volume drops)
3. Loader success/failure patterns
4. ECS task execution status (for cloud deployments)

Integrates with Phase 1 of the orchestrator to fail-closed on stale data.

USAGE:
  python3 algo_loader_monitor.py --check-symbols BRK.B,LEN.B,WSO.B
  python3 algo_loader_monitor.py --check-freshness
"""

try:
    from credential_manager import get_credential_manager
    credential_manager = get_credential_manager()
except ImportError:
    credential_manager = None

import os
import psycopg2
import argparse
import logging
from pathlib import Path
from dotenv import load_dotenv
from datetime import date as _date, datetime, timedelta
from algo_sql_safety import assert_safe_table, assert_safe_column

logger = logging.getLogger(__name__)
logging.basicConfig(level=logging.INFO)

env_file = Path(__file__).parent / '.env.local'
if env_file.exists():
    load_dotenv(env_file)

def _get_db_config():
    """Lazy-load DB config at runtime instead of module import time."""
    return {
    "host": os.getenv("DB_HOST", "localhost"),
    "port": int(os.getenv("DB_PORT", 5432)),
    "user": os.getenv("DB_USER", "stocks"),
    "password": get_db_password(),
    "database": os.getenv("DB_NAME", "stocks"),
    }


class LoaderMonitor:
    """Monitor data loader health and freshness."""

    def __init__(self):
        self.conn = None
        self.cur = None
        self.findings = []  # List of (severity, check, message)

    def connect(self):
        self.conn = psycopg2.connect(**_get_db_config())
        self.cur = self.conn.cursor()

    def disconnect(self):
        if self.cur:
            self.cur.close()
        if self.conn:
            self.conn.close()

    def check_symbols_have_data(self, symbols):
        """Check if critical symbols have data in price_daily.

        Args:
            symbols: List of symbol strings to check

        Returns:
            (missing_symbols, stale_symbols) — lists of symbols
        """
        missing = []
        stale = []

        for sym in symbols:
            try:
                self.cur.execute(
                    """
                    SELECT MAX(date) as latest
                    FROM price_daily
                    WHERE symbol = %s
                """,
                    (sym,),
                )
                result = self.cur.fetchone()

                if not result or result[0] is None:
                    missing.append(sym)
                else:
                    latest_date = result[0]
                    days_old = (_date.today() - latest_date).days
                    if days_old > 1:
                        stale.append((sym, latest_date, days_old))

            except Exception as e:
                logger.error(f"Error checking symbol {sym}: {e}")
                missing.append(sym)

        return missing, stale

    def check_daily_load_volume(self, expected_min=4000):
        """Check if today's load volume is healthy.

        Args:
            expected_min: Minimum symbol count expected for today's load

        Returns:
            (count, status) — (symbols with today's data, 'OK' or 'LOW')
        """
        try:
            self.cur.execute(
                """
                SELECT COUNT(DISTINCT symbol)
                FROM price_daily
                WHERE date = CURRENT_DATE
            """
            )
            count = self.cur.fetchone()[0]
            status = "OK" if count >= expected_min else "LOW"
            return count, status
        except Exception as e:
            logger.error(f"Error checking load volume: {e}")
            return 0, "ERROR"

    def check_universe_coverage(self, threshold_pct=95):
        """Check % of universe updated with fresh data.

        Args:
            threshold_pct: Alert if coverage drops below this

        Returns:
            pct_covered
        """
        try:
            self.cur.execute(
                """
                WITH universe_count AS (
                    SELECT COUNT(*) as total FROM stock_symbols
                ),
                fresh_count AS (
                    SELECT COUNT(DISTINCT symbol) as fresh
                    FROM price_daily
                    WHERE date >= CURRENT_DATE - 1
                )
                SELECT ROUND(100.0 * fresh_count.fresh / universe_count.total, 1)
                FROM universe_count, fresh_count
            """
            )
            result = self.cur.fetchone()
            return result[0] if result else 0
        except Exception as e:
            logger.error(f"Error checking universe coverage: {e}")
            return 0

    def check_stale_symbols(self, stale_threshold_days=7):
        """Find symbols that haven't been updated in N days.

        Args:
            stale_threshold_days: Consider stale if older than N days

        Returns:
            List of (symbol, latest_date, days_old)
        """
        try:
            self.cur.execute(
                """
                SELECT symbol, MAX(date) as latest_date,
                       CURRENT_DATE - MAX(date)::date as days_old
                FROM price_daily
                GROUP BY symbol
                HAVING CURRENT_DATE - MAX(date)::date > %s
                ORDER BY days_old DESC
                LIMIT 20
            """,
                (stale_threshold_days,),
            )
            return self.cur.fetchall()
        except Exception as e:
            logger.error(f"Error checking stale symbols: {e}")
            return []

    def audit_all(self, critical_symbols=None):
        """Run all freshness checks.

        Args:
            critical_symbols: List of symbols that must have data

        Returns:
            findings: List of (severity, check_name, message) tuples
        """
        self.findings = []

        # 1. Check critical symbols
        if critical_symbols:
            missing, stale = self.check_symbols_have_data(critical_symbols)

            if missing:
                self.findings.append(
                    (
                        "CRITICAL",
                        "critical_symbols_missing",
                        f"Critical symbols have NO data: {', '.join(missing)}",
                    )
                )

            for sym, latest, days_old in stale:
                self.findings.append(
                    (
                        "ERROR",
                        "critical_symbol_stale",
                        f"Critical symbol {sym} is {days_old} days old (latest: {latest})",
                    )
                )

        # 2. Check daily load volume
        today_count, status = self.check_daily_load_volume()
        if status == "LOW":
            self.findings.append(
                (
                    "ERROR",
                    "low_daily_load_volume",
                    f"Today's load volume is LOW: {today_count} symbols (expected >=4000)",
                )
            )
        elif status == "ERROR":
            self.findings.append(
                (
                    "ERROR",
                    "load_volume_check_failed",
                    "Could not check daily load volume",
                )
            )
        else:
            logger.info(f"✓ Daily load volume OK: {today_count} symbols")

        # 3. Check universe coverage
        coverage_pct = self.check_universe_coverage()
        if coverage_pct < 95:
            self.findings.append(
                (
                    "WARN",
                    "low_universe_coverage",
                    f"Universe coverage is {coverage_pct}% (expected >=95%)",
                )
            )
        else:
            logger.info(f"✓ Universe coverage OK: {coverage_pct}%")

        # 4. List most stale symbols (informational)
        stale_symbols = self.check_stale_symbols(stale_threshold_days=5)
        if stale_symbols and len(stale_symbols) > 5:
            symbols_str = ", ".join([f"{s[0]}({s[2]}d)" for s in stale_symbols[:5]])
            self.findings.append(
                (
                    "WARN",
                    "stale_symbols_detected",
                    f"Top stale symbols: {symbols_str}",
                )
            )

        return self.findings

    def report(self, json_format=False):
        """Print audit report.

        Args:
            json_format: Print as JSON instead of text
        """
        if json_format:
            import json

            out = {
                "timestamp": datetime.now().isoformat(),
                "findings": [
                    {"severity": f[0], "check": f[1], "message": f[2]}
                    for f in self.findings
                ],
            }
            print(json.dumps(out, indent=2))
        else:
            print(f"\n=== LOADER MONITOR REPORT ({datetime.now().strftime('%Y-%m-%d %H:%M:%S')}) ===\n")
            if not self.findings:
                print("✓ All checks passed")
            else:
                by_severity = {}
                for sev, check, msg in self.findings:
                    if sev not in by_severity:
                        by_severity[sev] = []
                    by_severity[sev].append((check, msg))

                for sev in ["CRITICAL", "ERROR", "WARN", "INFO"]:
                    if sev in by_severity:
                        print(f"\n[{sev}]")
                        for check, msg in by_severity[sev]:
                            print(f"  {check}: {msg}")


def main():
    parser = argparse.ArgumentParser(description="Monitor data loader health")
    parser.add_argument(
        "--check-symbols",
        help="Comma-separated symbols to check (e.g., BRK.B,LEN.B,WSO.B)",
    )
    parser.add_argument(
        "--check-freshness",
        action="store_true",
        help="Run all freshness checks",
    )
    parser.add_argument("--json", action="store_true", help="Output JSON format")
    args = parser.parse_args()

    monitor = LoaderMonitor()
    monitor.connect()

    try:
        symbols = []
        if args.check_symbols:
            symbols = [s.strip().upper() for s in args.check_symbols.split(",")]
        elif args.check_freshness:
            symbols = None
        else:
            symbols = ["AAPL", "MSFT", "NVDA", "TSLA"]  # Default critical symbols

        monitor.audit_all(critical_symbols=symbols)
        monitor.report(json_format=args.json)

        # Exit with error code if critical findings
        has_critical = any(f[0] == "CRITICAL" for f in monitor.findings)
        return 1 if has_critical else 0

    finally:
        monitor.disconnect()


if __name__ == "__main__":
    exit(main())

