#!/usr/bin/env python3
"""
System Readiness Verification Script
Run this daily to verify the platform is production-ready for trading.

Usage:
    python3 verify_system_ready.py              # Run all checks
    python3 verify_system_ready.py --quick      # Just critical checks
    python3 verify_system_ready.py --data-only  # Just data freshness
"""

import sys
import os
import psycopg2
from datetime import datetime, date, timedelta
from pathlib import Path
from dotenv import load_dotenv
from typing import Dict, List, Tuple

env_file = Path(__file__).parent / '.env.local'
if env_file.exists():
    load_dotenv(env_file)

# ANSI colors
GREEN = '\033[92m'
RED = '\033[91m'
YELLOW = '\033[93m'
BLUE = '\033[94m'
RESET = '\033[0m'

class SystemVerifier:
    """Comprehensive system readiness verification."""

    def __init__(self):
        self.checks_passed = 0
        self.checks_failed = 0
        self.warnings = 0
        self.results = []

    def log(self, status: str, check: str, details: str = ""):
        """Log a check result."""
        if status == "PASS":
            symbol = f"{GREEN}✓{RESET}"
            self.checks_passed += 1
        elif status == "FAIL":
            symbol = f"{RED}✗{RESET}"
            self.checks_failed += 1
        else:  # WARN
            symbol = f"{YELLOW}⚠{RESET}"
            self.warnings += 1

        msg = f"  {symbol} {check}"
        if details:
            msg += f" — {details}"
        print(msg)
        self.results.append((status, check, details))

    def connect_db(self) -> Tuple[psycopg2.extensions.connection, psycopg2.extensions.cursor]:
        """Connect to PostgreSQL database."""
        try:
            conn = psycopg2.connect(
                host=os.getenv("DB_HOST", "localhost"),
                port=int(os.getenv("DB_PORT", 5432)),
                user=os.getenv("DB_USER", "stocks"),
                password=os.getenv("DB_PASSWORD", "postgres"),
                database=os.getenv("DB_NAME", "stocks"),
            )
            cur = conn.cursor()
            return conn, cur
        except Exception as e:
            self.log("FAIL", "Database Connection", str(e))
            return None, None

    def check_database_connectivity(self):
        """Verify database is accessible."""
        print(f"\n{BLUE}DATABASE CONNECTIVITY{RESET}")
        conn, cur = self.connect_db()
        if conn and cur:
            self.log("PASS", "Database Connection")
            return conn, cur
        return None, None

    def check_data_freshness(self, conn, cur):
        """Verify tables have recent data."""
        print(f"\n{BLUE}DATA FRESHNESS{RESET}")
        today = date.today()
        yesterday = today - timedelta(days=1)

        tables_to_check = [
            ("price_daily", "symbol", "date"),
            ("market_exposure_daily", "date", "date"),
            ("algo_risk_daily", "report_date", "report_date"),
            ("stock_scores", "symbol", "updated_at::date"),
            ("technical_data_daily", "symbol", "date"),
            ("buy_sell_daily", "symbol", "date"),
        ]

        for table, id_col, date_col in tables_to_check:
            try:
                cur.execute(f"SELECT MAX({date_col}) FROM {table}")
                max_date = cur.fetchone()[0]

                if max_date is None:
                    self.log("FAIL", f"{table}", "No data in table")
                elif max_date == today:
                    self.log("PASS", f"{table}", f"Updated today ({max_date})")
                elif max_date == yesterday:
                    self.log("PASS", f"{table}", f"Updated yesterday ({max_date})")
                elif max_date > yesterday:
                    self.log("WARN", f"{table}", f"Updated recently ({max_date})")
                else:
                    days_old = (today - max_date).days
                    self.log("FAIL", f"{table}", f"Data is {days_old} days old ({max_date})")
            except Exception as e:
                self.log("FAIL", f"{table}", f"Query error: {str(e)[:50]}")

    def check_calculations(self, conn, cur):
        """Verify calculation results are sensible."""
        print(f"\n{BLUE}CALCULATION CORRECTNESS{RESET}")

        # Check market exposure
        try:
            cur.execute("""
                SELECT market_exposure_pct, exposure_tier, is_entry_allowed
                FROM market_exposure_daily
                ORDER BY date DESC LIMIT 1
            """)
            row = cur.fetchone()
            if row:
                exposure_pct, tier, is_entry = row
                if 0 <= exposure_pct <= 100:
                    self.log("PASS", "Market Exposure (%)", f"{exposure_pct:.1f}% - {tier}")
                else:
                    self.log("FAIL", "Market Exposure (%)", f"Out of range: {exposure_pct}")
            else:
                self.log("FAIL", "Market Exposure (%)", "No data found")
        except Exception as e:
            self.log("FAIL", "Market Exposure (%)", str(e)[:50])

        # Check VaR
        try:
            cur.execute("""
                SELECT var_pct_95, cvar_pct_95, portfolio_beta
                FROM algo_risk_daily
                ORDER BY report_date DESC LIMIT 1
            """)
            row = cur.fetchone()
            if row:
                var, cvar, beta = row
                if var and var > 0 and cvar and beta:
                    self.log("PASS", "VaR (95%)", f"{var:.2f}% | CVaR: {cvar:.2f}% | Beta: {beta:.2f}")
                else:
                    self.log("FAIL", "VaR (95%)", "NULL or invalid values")
            else:
                self.log("WARN", "VaR (95%)", "No data found")
        except Exception as e:
            self.log("WARN", "VaR (95%)", str(e)[:50])

        # Check swing scores
        try:
            cur.execute("""
                SELECT COUNT(*) as score_count, AVG(score) as avg_score
                FROM swing_trader_scores
                WHERE date >= CURRENT_DATE - INTERVAL '1 day'
            """)
            row = cur.fetchone()
            if row and row[0] > 0:
                count, avg_score = row
                self.log("PASS", "Swing Scores", f"{count} stocks scored, avg: {avg_score:.1f}")
            else:
                self.log("WARN", "Swing Scores", "No recent scores")
        except Exception as e:
            self.log("WARN", "Swing Scores", str(e)[:50])

    def check_data_integrity(self, conn, cur):
        """Check for data quality issues."""
        print(f"\n{BLUE}DATA INTEGRITY{RESET}")

        # Check for NULL values in critical columns
        try:
            cur.execute("""
                SELECT COUNT(*) FROM market_exposure_daily
                WHERE market_exposure_pct IS NULL
                AND date >= CURRENT_DATE - INTERVAL '3 days'
            """)
            null_count = cur.fetchone()[0]
            if null_count == 0:
                self.log("PASS", "Market Exposure NULLs", "No NULL values in recent data")
            else:
                self.log("FAIL", "Market Exposure NULLs", f"{null_count} NULL values found")
        except Exception as e:
            self.log("WARN", "Market Exposure NULLs", str(e)[:50])

        # Check for duplicate dates in market_exposure_daily
        try:
            cur.execute("""
                SELECT date, COUNT(*) as cnt FROM market_exposure_daily
                GROUP BY date HAVING COUNT(*) > 1
                LIMIT 1
            """)
            row = cur.fetchone()
            if row:
                self.log("FAIL", "Market Exposure Duplicates", f"Duplicates found on {row[0]}")
            else:
                self.log("PASS", "Market Exposure Duplicates", "No duplicates")
        except Exception as e:
            self.log("WARN", "Market Exposure Duplicates", str(e)[:50])

    def check_orchestrator_status(self, conn, cur):
        """Check orchestrator health."""
        print(f"\n{BLUE}ORCHESTRATOR STATUS{RESET}")

        # Check last orchestrator audit log entry
        try:
            cur.execute("""
                SELECT action_type, created_at FROM algo_audit_log
                WHERE action_type IN ('orchestrator_start', 'ORCHESTRATOR_COMPLETE')
                ORDER BY created_at DESC LIMIT 1
            """)
            row = cur.fetchone()
            if row:
                action, timestamp = row
                age_minutes = (datetime.utcnow() - timestamp.replace(tzinfo=None)).total_seconds() / 60
                if age_minutes < 1440:  # Less than 24 hours
                    self.log("PASS", "Last Orchestrator Run", f"{action} ({int(age_minutes)}m ago)")
                else:
                    self.log("FAIL", "Last Orchestrator Run", f"No run in last 24h")
            else:
                self.log("FAIL", "Last Orchestrator Run", "No audit log entries")
        except Exception as e:
            self.log("WARN", "Last Orchestrator Run", str(e)[:50])

    def check_open_positions(self, conn, cur):
        """Check trading positions."""
        print(f"\n{BLUE}TRADING STATUS{RESET}")

        try:
            cur.execute("SELECT COUNT(*) FROM algo_positions WHERE status = 'open'")
            open_count = cur.fetchone()[0]
            self.log("PASS", "Open Positions", f"{open_count} positions")
        except Exception as e:
            self.log("WARN", "Open Positions", str(e)[:50])

        try:
            cur.execute("""
                SELECT COUNT(*) FROM algo_trades
                WHERE trade_date >= CURRENT_DATE - INTERVAL '1 day'
                AND status != 'cancelled'
            """)
            recent_trades = cur.fetchone()[0]
            self.log("PASS", "Recent Trades (24h)", f"{recent_trades} trades")
        except Exception as e:
            self.log("WARN", "Recent Trades (24h)", str(e)[:50])

    def run_all_checks(self):
        """Run all verification checks."""
        print(f"\n{BLUE}{'='*70}{RESET}")
        print(f"{BLUE}SYSTEM READINESS VERIFICATION{RESET}")
        print(f"{BLUE}{'='*70}{RESET}")
        print(f"Started: {datetime.now().strftime('%Y-%m-%d %H:%M:%S')}")

        # Connect to database
        conn, cur = self.check_database_connectivity()
        if not conn:
            print(f"\n{RED}Cannot proceed without database connection{RESET}")
            return False

        # Run all checks
        self.check_data_freshness(conn, cur)
        self.check_calculations(conn, cur)
        self.check_data_integrity(conn, cur)
        self.check_orchestrator_status(conn, cur)
        self.check_open_positions(conn, cur)

        # Summary
        print(f"\n{BLUE}{'='*70}{RESET}")
        print(f"{BLUE}SUMMARY{RESET}")
        print(f"{BLUE}{'='*70}{RESET}")
        print(f"{GREEN}✓ Passed:{RESET}  {self.checks_passed}")
        print(f"{RED}✗ Failed:{RESET}  {self.checks_failed}")
        print(f"{YELLOW}⚠ Warnings:{RESET} {self.warnings}")

        if self.checks_failed > 0:
            print(f"\n{RED}PRODUCTION READINESS: FAIL{RESET}")
            print("Issues must be resolved before trading")
            return False
        elif self.warnings > 0:
            print(f"\n{YELLOW}PRODUCTION READINESS: CAUTION{RESET}")
            print("Warnings should be reviewed")
            return True
        else:
            print(f"\n{GREEN}PRODUCTION READINESS: PASS{RESET}")
            print("System is ready for trading")
            return True

        if conn:
            cur.close()
            conn.close()

if __name__ == "__main__":
    verifier = SystemVerifier()
    success = verifier.run_all_checks()
    sys.exit(0 if success else 1)
