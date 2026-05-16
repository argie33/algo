#!/usr/bin/env python3
"""
Startup Validation Module
Runs on system startup to verify all prerequisites are met before trading.
Prevents silent failures from misconfiguration or missing data.
"""

import os
import sys
import logging
from datetime import datetime, timedelta
from typing import Dict, List, Tuple

logger = logging.getLogger(__name__)


class StartupValidator:
    """Validates system readiness before trading operations."""

    def __init__(self):
        self.checks_passed = []
        self.checks_failed = []
        self.checks_warnings = []

    def check_database_connectivity(self) -> bool:
        """Verify database connection works."""
        try:
            # Try to import and get credentials
            from credential_helper import get_db_config
            config = get_db_config()

            # Try to connect
            import psycopg2
            conn = psycopg2.connect(**config)
            conn.close()

            self.checks_passed.append("✓ Database connectivity")
            return True
        except Exception as e:
            self.checks_failed.append(f"✗ Database connectivity: {e}")
            return False

    def check_database_schema(self) -> bool:
        """Verify all required tables exist."""
        try:
            from credential_helper import get_db_config
            import psycopg2

            required_tables = [
                'stock_scores', 'price_daily', 'technical_data_daily',
                'algo_positions', 'algo_trades', 'algo_risk_daily',
                'market_exposure_daily', 'market_health_daily',
                'algo_audit_log', 'algo_notifications'
            ]

            config = get_db_config()
            conn = psycopg2.connect(**config)
            cur = conn.cursor()

            missing = []
            for table in required_tables:
                cur.execute(f"SELECT EXISTS (SELECT 1 FROM information_schema.tables WHERE table_name = %s);", (table,))
                exists = cur.fetchone()[0]
                if not exists:
                    missing.append(table)

            conn.close()

            if missing:
                self.checks_failed.append(f"✗ Schema: Missing tables: {', '.join(missing)}")
                return False

            self.checks_passed.append("✓ Database schema")
            return True
        except Exception as e:
            self.checks_failed.append(f"✗ Schema check: {e}")
            return False

    def check_data_freshness(self) -> bool:
        """Verify recent data exists (within last 2 days)."""
        try:
            from credential_helper import get_db_config
            import psycopg2

            config = get_db_config()
            conn = psycopg2.connect(**config)
            cur = conn.cursor()

            # Check critical tables for recent data
            critical_checks = [
                ("stock_scores", "score_date"),
                ("price_daily", "date"),
                ("technical_data_daily", "date"),
                ("market_health_daily", "date"),
            ]

            all_fresh = True
            stale_tables = []

            for table, date_col in critical_checks:
                cur.execute(f"SELECT MAX({date_col}) FROM {table};")
                max_date = cur.fetchone()[0]

                if max_date is None:
                    stale_tables.append(f"{table} (empty)")
                    all_fresh = False
                else:
                    days_old = (datetime.now().date() - max_date).days
                    if days_old > 2:
                        stale_tables.append(f"{table} ({days_old} days old)")
                        all_fresh = False

            conn.close()

            if not all_fresh:
                self.checks_warnings.append(f"⚠ Data freshness: {', '.join(stale_tables)}")
                return False

            self.checks_passed.append("✓ Data freshness")
            return True
        except Exception as e:
            self.checks_warnings.append(f"⚠ Data freshness check: {e}")
            return False

    def check_credentials(self) -> bool:
        """Verify API credentials are available."""
        try:
            # Check Alpaca API key
            alpaca_key = os.getenv("APCA_API_KEY_ID")
            alpaca_secret = os.getenv("APCA_API_SECRET_KEY")

            if not alpaca_key or not alpaca_secret:
                self.checks_failed.append("✗ Alpaca credentials missing (APCA_API_KEY_ID or APCA_API_SECRET_KEY)")
                return False

            self.checks_passed.append("✓ Alpaca credentials")
            return True
        except Exception as e:
            self.checks_failed.append(f"✗ Credential check: {e}")
            return False

    def check_configuration(self) -> bool:
        """Verify all required configuration is present."""
        try:
            from algo_config import AlgoConfig
            config = AlgoConfig()

            # Check critical config values
            if config.max_positions <= 0:
                self.checks_failed.append(f"✗ Config: max_positions invalid ({config.max_positions})")
                return False

            if config.max_position_size_pct <= 0 or config.max_position_size_pct > 100:
                self.checks_failed.append(f"✗ Config: max_position_size_pct invalid ({config.max_position_size_pct})")
                return False

            if config.max_drawdown_pct <= 0 or config.max_drawdown_pct > 100:
                self.checks_failed.append(f"✗ Config: max_drawdown_pct invalid ({config.max_drawdown_pct})")
                return False

            self.checks_passed.append("✓ Configuration valid")
            return True
        except Exception as e:
            self.checks_failed.append(f"✗ Configuration check: {e}")
            return False

    def check_api_connectivity(self) -> bool:
        """Verify API Gateway is accessible."""
        try:
            import requests
            api_url = os.getenv("API_URL", "https://2iqq1qhltj.execute-api.us-east-1.amazonaws.com")

            response = requests.get(f"{api_url}/api/health", timeout=5)
            if response.status_code != 200:
                self.checks_warnings.append(f"⚠ API Gateway: returned {response.status_code} (expected 200)")
                return False

            self.checks_passed.append("✓ API Gateway connectivity")
            return True
        except requests.exceptions.ConnectionError as e:
            self.checks_failed.append(f"✗ API Gateway: Connection failed - {e}")
            return False
        except Exception as e:
            self.checks_warnings.append(f"⚠ API check: {e}")
            return False

    def check_portfolio_state(self) -> bool:
        """Verify portfolio exists and is in valid state."""
        try:
            from credential_helper import get_db_config
            import psycopg2

            config = get_db_config()
            conn = psycopg2.connect(**config)
            cur = conn.cursor()

            # Check portfolio snapshots exist
            cur.execute("SELECT COUNT(*) FROM algo_portfolio_snapshots;")
            count = cur.fetchone()[0]

            if count == 0:
                self.checks_warnings.append("⚠ Portfolio: No snapshots yet (first run?)")
            else:
                self.checks_passed.append("✓ Portfolio state")

            conn.close()
            return True
        except Exception as e:
            self.checks_warnings.append(f"⚠ Portfolio check: {e}")
            return False

    def run_all_checks(self) -> bool:
        """Run all startup checks. Returns True if critical checks pass."""
        logger.info("Running startup validation checks...")

        # Critical checks (must pass)
        critical = [
            self.check_database_connectivity,
            self.check_database_schema,
            self.check_credentials,
            self.check_configuration,
        ]

        # Warning checks (should pass but non-blocking)
        warnings = [
            self.check_data_freshness,
            self.check_api_connectivity,
            self.check_portfolio_state,
        ]

        # Run critical checks
        for check in critical:
            try:
                check()
            except Exception as e:
                logger.error(f"Startup check exception: {e}")
                self.checks_failed.append(f"✗ {check.__name__}: {e}")

        # Run warning checks
        for check in warnings:
            try:
                check()
            except Exception as e:
                logger.warning(f"Startup warning: {e}")
                self.checks_warnings.append(f"⚠ {check.__name__}: {e}")

        # Report results
        self._report_results()

        # Return success only if no critical failures
        return len(self.checks_failed) == 0

    def _report_results(self):
        """Print startup check results."""
        print("\n" + "="*60)
        print("STARTUP VALIDATION RESULTS")
        print("="*60)

        if self.checks_passed:
            print("\n✓ PASSED:")
            for msg in self.checks_passed:
                print(f"  {msg}")

        if self.checks_warnings:
            print("\n⚠ WARNINGS:")
            for msg in self.checks_warnings:
                print(f"  {msg}")

        if self.checks_failed:
            print("\n✗ FAILED:")
            for msg in self.checks_failed:
                print(f"  {msg}")

        print("\n" + "="*60)

        if self.checks_failed:
            print("SYSTEM NOT READY - Fix failures above before trading\n")
            sys.exit(1)
        elif self.checks_warnings:
            print("SYSTEM READY with WARNINGS - Proceed with caution\n")
        else:
            print("SYSTEM READY - All checks passed\n")


def validate_startup() -> bool:
    """Run startup validation. Call this at system startup."""
    validator = StartupValidator()
    return validator.run_all_checks()


if __name__ == "__main__":
    validate_startup()
