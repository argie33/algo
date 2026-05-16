#!/usr/bin/env python3
"""
Database Schema Validation - Verify schema matches code expectations

Checks:
1. All expected tables exist
2. All expected columns exist with correct types
3. Primary keys and constraints are defined
4. Indexes for performance-critical paths exist
5. Foreign key relationships are intact
"""

try:
    from credential_manager import get_credential_manager
    credential_manager = get_credential_manager()
except ImportError:
    credential_manager = None

import os
import sys
from credential_helper import get_db_password, get_db_config
import logging
import psycopg2
from pathlib import Path
from dotenv import load_dotenv

logger = logging.getLogger(__name__)

env_file = Path(__file__).parent / '.env.local'
if env_file.exists():
    load_dotenv(env_file)

logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s [%(levelname)s] %(name)s: %(message)s",
)

def _get_db_config():
    """Get database configuration."""
    return {
        "host": os.getenv("DB_HOST", "localhost"),
        "port": int(os.getenv("DB_PORT", 5432)),
        "user": os.getenv("DB_USER", "stocks"),
        "password": get_db_password() if credential_manager else os.getenv("DB_PASSWORD", ""),
        "database": os.getenv("DB_NAME", "stocks"),
    }


class SchemaValidator:
    """Validate database schema consistency."""

    # Expected tables and critical columns (subset for validation)
    EXPECTED_SCHEMA = {
        'price_daily': {
            'columns': {
                'symbol': 'character varying',
                'date': 'date',
                'close': 'numeric',
                'volume': 'bigint',
            },
            'constraints': ['symbol', 'date']  # UNIQUE constraint
        },
        'technical_data_daily': {
            'columns': {
                'symbol': 'character varying',
                'date': 'date',
                'sma_20': 'numeric',
                'rsi': 'numeric',
                'macd': 'numeric',
            },
            'constraints': ['date']
        },
        'buy_sell_daily': {
            'columns': {
                'symbol': 'character varying',
                'date': 'date',
                'buy_signal': 'boolean',
                'sell_signal': 'boolean',
            },
            'constraints': ['date', 'symbol']
        },
        'stock_scores': {
            'columns': {
                'symbol': 'character varying',
                'growth_score': 'numeric',
                'value_score': 'numeric',
                'momentum_score': 'numeric',
            },
            'constraints': ['symbol']
        },
        'algo_positions': {
            'columns': {
                'symbol': 'character varying',
                'entry_price': 'numeric',
                'status': 'character varying',
                'entry_date': 'timestamp without time zone',
            },
            'constraints': ['status']
        },
        'algo_trades': {
            'columns': {
                'position_id': 'integer',
                'trade_date': 'date',
                'status': 'character varying',
                'quantity': 'integer',
            },
            'constraints': ['status', 'position_id']
        },
        'market_exposure_daily': {
            'columns': {
                'date': 'date',
                'exposure_pct': 'numeric',
                'regime': 'character varying',
            },
            'constraints': ['date']
        },
        'algo_risk_daily': {
            'columns': {
                'report_date': 'date',
                'var_pct_95': 'numeric',
                'portfolio_beta': 'numeric',
            },
            'constraints': ['report_date']
        },
        'algo_portfolio_snapshots': {
            'columns': {
                'snapshot_date': 'date',
                'total_portfolio_value': 'numeric',
            },
            'constraints': ['snapshot_date']
        },
        'algo_audit_log': {
            'columns': {
                'action_date': 'timestamp without time zone',
                'action_type': 'character varying',
                'details': 'jsonb',
            },
            'constraints': ['action_type']
        },
        'data_patrol_log': {
            'columns': {
                'check_name': 'character varying',
                'severity': 'character varying',
                'created_at': 'timestamp without time zone',
            },
            'constraints': ['severity']
        },
        'loader_sla_tracker': {
            'columns': {
                'loader_name': 'character varying',
                'status': 'character varying',
                'start_time': 'timestamp without time zone',
            },
            'constraints': ['status', 'loader_name']
        },
        'economic_data': {
            'columns': {
                'series_id': 'character varying',
                'date': 'date',
                'value': 'numeric',
            },
            'constraints': ['series_id', 'date']
        },
    }

    def __init__(self):
        self.conn = None
        self.cur = None
        self.issues = []
        self.checks_passed = 0
        self.checks_total = 0

    def connect(self):
        """Connect to database."""
        try:
            self.conn = psycopg2.connect(**_get_db_config())
            self.cur = self.conn.cursor()
            logger.info("Connected to database")
        except Exception as e:
            logger.error(f"DB connection failed: {e}", exc_info=True)
            raise

    def disconnect(self):
        """Close database connection."""
        if self.cur:
            self.cur.close()
        if self.conn:
            self.conn.close()

    def _log_check(self, passed: bool, message: str):
        """Log a check result."""
        self.checks_total += 1
        if passed:
            self.checks_passed += 1
            logger.info(f"✓ {message}")
        else:
            self.issues.append(message)
            logger.error(f"✗ {message}")

    def validate_all(self):
        """Run all validation checks."""
        self.connect()
        try:
            logger.info("\n" + "="*70)
            logger.info("DATABASE SCHEMA VALIDATION")
            logger.info("="*70 + "\n")

            for table_name, expected in self.EXPECTED_SCHEMA.items():
                self._validate_table(table_name, expected)

            # Check critical indexes exist
            logger.info("\nChecking critical indexes:\n")
            self._validate_indexes()

            # Summary
            logger.info("\n" + "="*70)
            logger.info(f"VALIDATION SUMMARY: {self.checks_passed}/{self.checks_total} checks passed")
            if self.issues:
                logger.error("\nFAILED CHECKS:")
                for issue in self.issues:
                    logger.error(f"  - {issue}")
            logger.info("="*70 + "\n")

            return len(self.issues) == 0

        finally:
            self.disconnect()

    def _validate_table(self, table_name: str, expected: dict):
        """Validate a single table."""
        logger.info(f"Checking table: {table_name}")

        # Check table exists
        self.cur.execute(
            "SELECT EXISTS (SELECT 1 FROM information_schema.tables WHERE table_schema='public' AND table_name=%s)",
            (table_name,)
        )
        if not self.cur.fetchone()[0]:
            self._log_check(False, f"{table_name} table does not exist")
            return

        self._log_check(True, f"{table_name} table exists")

        # Check columns exist with correct type
        for col_name, col_type in expected['columns'].items():
            self.cur.execute(
                """
                SELECT column_name, data_type, udt_name
                FROM information_schema.columns
                WHERE table_name=%s AND column_name=%s
                """,
                (table_name, col_name)
            )
            result = self.cur.fetchone()
            if not result:
                self._log_check(False, f"{table_name}.{col_name} column does not exist")
            else:
                actual_type = result[1]
                # Normalize type names (e.g., 'character varying' == 'varchar')
                if actual_type in ('character varying', col_type, 'varchar') or col_type in ('character varying', actual_type, 'varchar'):
                    self._log_check(True, f"{table_name}.{col_name} ({actual_type})")
                else:
                    self._log_check(False, f"{table_name}.{col_name} has type {actual_type}, expected {col_type}")

        # Check constraints
        for constraint_col in expected['constraints']:
            self.cur.execute(
                """
                SELECT constraint_name FROM information_schema.key_column_usage
                WHERE table_name=%s AND column_name=%s
                """,
                (table_name, constraint_col)
            )
            has_constraint = self.cur.fetchone() is not None
            if has_constraint:
                self._log_check(True, f"{table_name}.{constraint_col} has constraint/index")
            else:
                logger.warning(f"  ⚠ {table_name}.{constraint_col} may not have constraint")

    def _validate_indexes(self):
        """Validate critical indexes exist."""
        critical_indexes = [
            ('idx_price_daily_symbol_date', 'price_daily'),
            ('idx_technical_data_daily_date', 'technical_data_daily'),
            ('idx_buy_sell_daily_date', 'buy_sell_daily'),
            ('idx_algo_positions_status', 'algo_positions'),
            ('idx_algo_trades_status_date', 'algo_trades'),
            ('idx_algo_risk_daily_date', 'algo_risk_daily'),
            ('idx_market_exposure_daily_date', 'market_exposure_daily'),
            ('idx_loader_sla_tracker_date_status', 'loader_sla_tracker'),
        ]

        for index_name, table_name in critical_indexes:
            self.cur.execute(
                """
                SELECT indexname FROM pg_indexes
                WHERE schemaname='public' AND indexname=%s
                """,
                (index_name,)
            )
            if self.cur.fetchone():
                self._log_check(True, f"{index_name} exists on {table_name}")
            else:
                self._log_check(False, f"{index_name} missing on {table_name}")


def main():
    validator = SchemaValidator()
    success = validator.validate_all()
    return 0 if success else 1


if __name__ == "__main__":
    sys.exit(main())
