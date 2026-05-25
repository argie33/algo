#!/usr/bin/env python3
"""
End-to-end system integration test.

Tests all critical components:
1. Database connectivity
2. Data in critical tables
3. API endpoint responses
4. Orchestrator execution
5. Data freshness

Run this to diagnose what's broken in the deployed system.
"""

import sys
from pathlib import Path
sys.path.insert(0, str(Path(__file__).parent.parent))

import psycopg2
import logging
import json
from datetime import date, timedelta
from typing import Dict, List, Tuple

logging.basicConfig(level=logging.INFO, format='%(asctime)s [%(levelname)s] %(message)s')
logger = logging.getLogger(__name__)

class SystemIntegrationTest:
    """Test complete system functionality."""

    def __init__(self):
        self.conn = None
        self.results = {}

    def run(self):
        """Execute all tests."""
        logger.info("Starting system integration tests...")

        try:
            self.test_database()
            self.test_data_presence()
            self.test_data_freshness()
            self.test_api_routes()
            self.test_orchestrator()
            self.generate_report()
        except Exception as e:
            logger.error(f"Tests failed: {e}", exc_info=True)
            return False
        finally:
            if self.conn:
                self.conn.close()

        return True

    def test_database(self):
        """Test database connectivity."""
        logger.info("\n=== DATABASE CONNECTIVITY TEST ===")
        try:
            from config.credential_helper import get_db_config
            config = get_db_config()
            self.conn = psycopg2.connect(**config)
            cur = self.conn.cursor()
            cur.execute("SELECT version()")
            version = cur.fetchone()[0]
            cur.close()
            logger.info(f"✓ Database connected: {version.split(',')[0]}")
            self.results['database'] = {'status': 'PASS', 'version': version}
        except Exception as e:
            logger.error(f"✗ Database connection failed: {e}")
            self.results['database'] = {'status': 'FAIL', 'error': str(e)}
            raise

    def test_data_presence(self):
        """Check if critical tables have any data."""
        logger.info("\n=== DATA PRESENCE TEST ===")
        if not self.conn:
            logger.error("Skipped: Database not connected")
            return

        cur = self.conn.cursor()
        tables = [
            'stock_symbols',
            'price_daily',
            'technical_data_daily',
            'buy_sell_daily',
            'stock_scores',
            'data_loader_status',
        ]

        self.results['data_presence'] = {}
        for table in tables:
            try:
                cur.execute(f"SELECT COUNT(*) FROM {table}")
                count = cur.fetchone()[0]
                status = 'PASS' if count > 0 else 'EMPTY'
                symbol = '✓' if count > 0 else '✗'
                logger.info(f"{symbol} {table:30} {count:10,} rows")
                self.results['data_presence'][table] = {'rows': count, 'status': status}
            except Exception as e:
                logger.error(f"✗ {table:30} Error: {str(e)[:50]}")
                self.results['data_presence'][table] = {'status': 'ERROR', 'error': str(e)}

        cur.close()

    def test_data_freshness(self):
        """Check data age in critical tables."""
        logger.info("\n=== DATA FRESHNESS TEST ===")
        if not self.conn:
            logger.error("Skipped: Database not connected")
            return

        cur = self.conn.cursor()
        today = date.today()

        tables_with_dates = [
            'price_daily',
            'technical_data_daily',
            'buy_sell_daily',
        ]

        self.results['data_freshness'] = {}
        for table in tables_with_dates:
            try:
                cur.execute(f"""
                    SELECT MAX(date) as max_date,
                           COUNT(*) as row_count
                    FROM {table}
                """)
                max_date, row_count = cur.fetchone()
                if max_date is None:
                    logger.warning(f"⚠ {table:30} No data")
                    self.results['data_freshness'][table] = {'status': 'EMPTY'}
                else:
                    age = (today - max_date).days
                    if age == 0:
                        status = 'FRESH'
                        symbol = '✓'
                    elif age <= 7:
                        status = 'STALE'
                        symbol = '⚠'
                    else:
                        status = 'CRITICAL'
                        symbol = '✗'
                    logger.info(f"{symbol} {table:30} {age} days old ({row_count} rows)")
                    self.results['data_freshness'][table] = {'age_days': age, 'status': status, 'rows': row_count}
            except Exception as e:
                logger.error(f"✗ {table:30} Error: {str(e)[:50]}")
                self.results['data_freshness'][table] = {'status': 'ERROR', 'error': str(e)}

        cur.close()

    def test_api_routes(self):
        """Test API route implementations."""
        logger.info("\n=== API ROUTES TEST ===")
        if not self.conn:
            logger.error("Skipped: Database not connected")
            return

        cur = self.conn.cursor()

        # Test that critical routes have underlying data
        tests = [
            ("Scores", "SELECT COUNT(*) FROM stock_scores WHERE composite_score > 0"),
            ("Signals", "SELECT COUNT(*) FROM buy_sell_daily WHERE signal IN ('BUY', 'SELL')"),
            ("Prices", "SELECT COUNT(*) FROM price_daily"),
            ("Market", "SELECT COUNT(*) FROM market_health_daily"),
            ("Economic", "SELECT COUNT(*) FROM economic_data"),
        ]

        self.results['api_routes'] = {}
        for route, query in tests:
            try:
                cur.execute(query)
                count = cur.fetchone()[0]
                status = 'PASS' if count > 0 else 'NO_DATA'
                symbol = '✓' if count > 0 else '✗'
                logger.info(f"{symbol} /api/{route.lower():20} {count:10,} items")
                self.results['api_routes'][route] = {'items': count, 'status': status}
            except Exception as e:
                logger.error(f"✗ /api/{route.lower():20} Error: {str(e)[:50]}")
                self.results['api_routes'][route] = {'status': 'ERROR', 'error': str(e)}

        cur.close()

    def test_orchestrator(self):
        """Test orchestrator configuration and recent runs."""
        logger.info("\n=== ORCHESTRATOR TEST ===")
        if not self.conn:
            logger.error("Skipped: Database not connected")
            return

        cur = self.conn.cursor()

        # Check environment variables
        import os
        env_vars = {
            'ORCHESTRATOR_DRY_RUN': os.getenv('ORCHESTRATOR_DRY_RUN'),
            'ALPACA_PAPER_TRADING': os.getenv('ALPACA_PAPER_TRADING'),
            'DEV_MODE': os.getenv('DEV_MODE'),
        }

        logger.info("Environment Configuration:")
        for var, value in env_vars.items():
            logger.info(f"  {var:30} = {value or 'NOT SET'}")

        # Check recent orchestrator runs
        try:
            cur.execute("""
                SELECT
                    action_date,
                    action_type,
                    status,
                    details->>'summary' as summary
                FROM algo_audit_log
                ORDER BY action_date DESC
                LIMIT 5
            """)

            runs = cur.fetchall()
            if not runs:
                logger.warning("⚠ No orchestrator runs found")
                self.results['orchestrator'] = {'status': 'NO_RUNS'}
            else:
                logger.info("Recent Orchestrator Runs:")
                for run_date, action_type, status, summary in runs:
                    logger.info(f"  {run_date} [{action_type}] {status}: {summary[:50] if summary else 'N/A'}")
                self.results['orchestrator'] = {'status': 'PASS', 'recent_runs': len(runs)}
        except Exception as e:
            logger.error(f"✗ Could not check orchestrator runs: {str(e)[:50]}")
            self.results['orchestrator'] = {'status': 'ERROR', 'error': str(e)}

        cur.close()

    def generate_report(self):
        """Generate final test report."""
        logger.info("\n=== TEST SUMMARY ===")

        total_tests = 0
        passed_tests = 0

        for section, tests in self.results.items():
            if isinstance(tests, dict):
                for key, value in tests.items():
                    if isinstance(value, dict) and 'status' in value:
                        total_tests += 1
                        if value['status'] in ['PASS', 'FRESH']:
                            passed_tests += 1

        logger.info(f"\nPassed: {passed_tests}/{total_tests} tests")

        # Critical issues
        issues = []

        # Check for empty critical tables
        for table, info in self.results.get('data_presence', {}).items():
            if info.get('status') == 'EMPTY' and table in ['price_daily', 'stock_scores']:
                issues.append(f"CRITICAL: {table} has no data - loaders not running?")

        # Check for stale data
        for table, info in self.results.get('data_freshness', {}).items():
            if info.get('status') == 'CRITICAL':
                age = info.get('age_days', 999)
                issues.append(f"WARNING: {table} is {age}+ days old")

        if issues:
            logger.warning("\n⚠️  ISSUES FOUND:")
            for issue in issues:
                logger.warning(f"  • {issue}")
        else:
            logger.info("\n✓ No critical issues found")

        # Write JSON report
        report_path = Path(__file__).parent.parent / 'test_results.json'
        with open(report_path, 'w') as f:
            json.dump(self.results, f, indent=2, default=str)
        logger.info(f"\nDetailed report: {report_path}")

if __name__ == '__main__':
    tester = SystemIntegrationTest()
    success = tester.run()
    sys.exit(0 if success else 1)
