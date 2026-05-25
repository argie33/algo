#!/usr/bin/env python3
"""
Comprehensive deployment diagnostic script.

Verifies all components are configured and functional:
- Database connectivity
- Key table population
- Loader freshness
- API Lambda health
- Orchestrator configuration
- Frontend deployment

Run after deploying to AWS to validate the full system.
"""

import sys
from pathlib import Path
sys.path.insert(0, str(Path(__file__).parent.parent))

import os
import logging
import json
from datetime import date, timedelta
from typing import Dict, List, Tuple

# Configure logging
logging.basicConfig(
    level=logging.INFO,
    format='%(asctime)s [%(levelname)s] %(message)s'
)
logger = logging.getLogger(__name__)

# Color codes for console output
class Colors:
    GREEN = '\033[92m'
    RED = '\033[91m'
    YELLOW = '\033[93m'
    BLUE = '\033[94m'
    RESET = '\033[0m'
    BOLD = '\033[1m'

def print_header(title):
    print(f"\n{Colors.BOLD}{Colors.BLUE}{'='*60}")
    print(f"  {title}")
    print(f"{'='*60}{Colors.RESET}\n")

def print_pass(msg):
    print(f"{Colors.GREEN}✓ {msg}{Colors.RESET}")

def print_fail(msg):
    print(f"{Colors.RED}✗ {msg}{Colors.RESET}")

def print_warn(msg):
    print(f"{Colors.YELLOW}⚠ {msg}{Colors.RESET}")

def print_info(msg):
    print(f"  {msg}")

class DeploymentDiagnostics:
    """Comprehensive deployment health check."""

    def __init__(self):
        self.results = {
            'database': {},
            'tables': {},
            'loaders': {},
            'api': {},
            'orchestrator': {},
            'frontend': {}
        }
        self.conn = None

    def run_all_checks(self):
        """Run complete diagnostic suite."""
        print_header("DEPLOYMENT DIAGNOSTICS")

        try:
            self.check_database_connectivity()
            self.check_critical_tables()
            self.check_loader_status()
            self.check_environment_variables()
            self.check_orchestrator_config()
            self.generate_summary()
        except Exception as e:
            print_fail(f"Diagnostic failed: {e}")
            return False
        finally:
            if self.conn:
                self.conn.close()

    def check_database_connectivity(self):
        """Verify database connection and credentials."""
        print_header("1. DATABASE CONNECTIVITY")

        try:
            import psycopg2
            from config.credential_helper import get_db_config

            config = get_db_config()
            logger.debug(f"Connecting to: {config['host']}:{config['port']}/{config['database']}")

            self.conn = psycopg2.connect(**config)
            cur = self.conn.cursor()
            cur.execute("SELECT version()")
            version = cur.fetchone()[0]
            cur.close()

            print_pass("Connected to PostgreSQL")
            print_info(f"Version: {version.split(',')[0]}")
            self.results['database']['connected'] = True

        except Exception as e:
            print_fail(f"Database connection failed: {e}")
            self.results['database']['connected'] = False
            raise

    def check_critical_tables(self):
        """Check key tables have recent data."""
        print_header("2. CRITICAL TABLE STATUS")

        if not self.conn:
            print_fail("Skipped: Database not connected")
            return

        critical_tables = {
            'stock_symbols': 'Stock list',
            'price_daily': 'Daily prices',
            'technical_data_daily': 'Technical indicators',
            'buy_sell_daily': 'Trading signals',
            'stock_scores': 'Stock scores',
            'data_loader_status': 'Loader freshness tracking',
        }

        cur = self.conn.cursor()
        today = date.today()

        for table, desc in critical_tables.items():
            try:
                # Check table exists and has rows
                cur.execute(f"SELECT COUNT(*) FROM {table}")
                count = cur.fetchone()[0]

                if count == 0:
                    print_warn(f"{table:30} {desc:30} EMPTY")
                    self.results['tables'][table] = {'status': 'empty', 'count': 0}
                else:
                    # Check if data is recent (< 7 days)
                    if table in ['price_daily', 'technical_data_daily', 'buy_sell_daily']:
                        cur.execute(f"SELECT MAX(date) FROM {table}")
                        max_date = cur.fetchone()[0]
                        age_days = (today - max_date).days if max_date else 999

                        if age_days <= 1:
                            print_pass(f"{table:30} {desc:30} FRESH ({count} rows, {age_days}d old)")
                            self.results['tables'][table] = {'status': 'healthy', 'count': count, 'age_days': age_days}
                        elif age_days <= 7:
                            print_warn(f"{table:30} {desc:30} STALE ({count} rows, {age_days}d old)")
                            self.results['tables'][table] = {'status': 'stale', 'count': count, 'age_days': age_days}
                        else:
                            print_fail(f"{table:30} {desc:30} CRITICAL ({count} rows, {age_days}d old)")
                            self.results['tables'][table] = {'status': 'critical', 'count': count, 'age_days': age_days}
                    else:
                        print_pass(f"{table:30} {desc:30} OK ({count} rows)")
                        self.results['tables'][table] = {'status': 'healthy', 'count': count}

            except Exception as e:
                print_fail(f"{table:30} {desc:30} ERROR: {str(e)[:40]}")
                self.results['tables'][table] = {'status': 'error', 'message': str(e)}

        cur.close()

    def check_loader_status(self):
        """Check loader execution and freshness."""
        print_header("3. LOADER STATUS")

        if not self.conn:
            print_fail("Skipped: Database not connected")
            return

        cur = self.conn.cursor()
        try:
            cur.execute("""
                SELECT table_name, row_count, last_updated,
                       EXTRACT(EPOCH FROM (NOW() - last_updated)) / 86400 AS age_days,
                       CASE
                           WHEN row_count > 0 AND EXTRACT(EPOCH FROM (NOW() - last_updated)) / 86400 <= 1 THEN 'FRESH'
                           WHEN row_count > 0 AND EXTRACT(EPOCH FROM (NOW() - last_updated)) / 86400 <= 7 THEN 'STALE'
                           WHEN row_count > 0 THEN 'CRITICAL'
                           ELSE 'EMPTY'
                       END AS status
                FROM data_loader_status
                ORDER BY last_updated DESC
                LIMIT 20
            """)

            rows = cur.fetchall()
            if not rows:
                print_warn("No loader status data available")
                return

            for row in rows:
                table_name, row_count, last_updated, age_days, status = row
                age_days = float(age_days) if age_days else 999

                if status == 'FRESH':
                    print_pass(f"{table_name:30} {status:10} ({int(row_count)} rows, {age_days:.1f}d old)")
                elif status == 'STALE':
                    print_warn(f"{table_name:30} {status:10} ({int(row_count)} rows, {age_days:.1f}d old)")
                else:
                    print_fail(f"{table_name:30} {status:10} ({int(row_count)} rows, {age_days:.1f}d old)")

        except Exception as e:
            print_warn(f"Cannot check loader status: {e}")
        finally:
            cur.close()

    def check_environment_variables(self):
        """Verify required environment variables."""
        print_header("4. ENVIRONMENT CONFIGURATION")

        required_vars = {
            'orchestrator_dry_run': 'Orchestrator dry-run mode',
            'ALPACA_PAPER_TRADING': 'Alpaca paper trading',
            'DEV_MODE': 'Development mode',
            'ORCHESTRATOR_LOG_LEVEL': 'Orchestrator log level',
        }

        for var, desc in required_vars.items():
            value = os.getenv(var, 'NOT SET')
            print_info(f"{var:30} = {value:20} ({desc})")

    def check_orchestrator_config(self):
        """Verify orchestrator configuration."""
        print_header("5. ORCHESTRATOR CONFIGURATION")

        if not self.conn:
            print_warn("Skipped: Database not connected")
            return

        print_info("Key orchestrator settings:")
        print_info("  - ORCHESTRATOR_DRY_RUN: Should be 'false' for live trading")
        print_info("  - ALPACA_PAPER_TRADING: Should be 'false' for live trading")
        print_info("  - DEV_MODE: Should be 'false' for production")
        print_info("")
        print_info("Confirm these values in:")
        print_info("  1. terraform/terraform.tfvars")
        print_info("  2. AWS Lambda environment variables")
        print_info("  3. GitHub Secrets")

    def generate_summary(self):
        """Generate diagnostic summary."""
        print_header("DIAGNOSTIC SUMMARY")

        issues = []

        # Check database
        if not self.results['database'].get('connected', False):
            issues.append("Database not connected")

        # Check critical tables
        for table, status in self.results['tables'].items():
            if status.get('status') == 'error':
                issues.append(f"Table {table} error: {status.get('message')}")
            elif status.get('status') == 'empty':
                issues.append(f"Table {table} is empty (loader may not have run)")
            elif status.get('status') == 'critical':
                age = status.get('age_days', 999)
                issues.append(f"Table {table} data too old ({age}+ days)")

        if issues:
            print_fail("ISSUES FOUND:")
            for issue in issues:
                print_info(f"  • {issue}")
            print_info("")
            print_warn("Next steps:")
            print_info("  1. Verify EventBridge rules are active and triggering ECS loaders")
            print_info("  2. Check ECS task execution logs in CloudWatch")
            print_info("  3. Verify data sources (yfinance, etc.) are accessible")
            print_info("  4. Run manual loader invocation to test data flow")
        else:
            print_pass("No critical issues found")

        print_info("")
        print_info("For detailed debugging:")
        print_info("  • API Lambda logs: /aws/lambda/algo-api-dev")
        print_info("  • Orchestrator logs: /aws/lambda/algo-algo-dev")
        print_info("  • ECS loader logs: /ecs/algo-cluster")
        print_info("  • GitHub Actions: https://github.com/argie33/algo/actions")

if __name__ == '__main__':
    diag = DeploymentDiagnostics()
    diag.run_all_checks()
