#!/usr/bin/env python3
"""
Schema validation — detect and prevent data quality issues at the source.

Validates that tables have required columns with correct types before loaders
insert data. Fails fast with clear error messages.

Usage:
    validator = SchemaValidator()
    issues = validator.validate_all()
    if issues:
        for severity, table, message in issues:
            print(f"[{severity}] {table}: {message}")

Or check specific table:
    validator.validate_table("price_daily", required_columns={
        "symbol": "varchar",
        "date": "date",
        "close": "numeric",
    })
"""

import logging
import psycopg2
from typing import Dict, List, Tuple, Optional, Any

logger = logging.getLogger(__name__)


class SchemaValidator:
    """Validates database schema matches expected structure."""

    # Critical tables and their required columns + types
    REQUIRED_SCHEMA = {
        "price_daily": {
            "symbol": "character varying",
            "date": "date",
            "open": "numeric",
            "high": "numeric",
            "low": "numeric",
            "close": "numeric",
            "volume": "bigint",
        },
        "technical_data_daily": {
            "symbol": "character varying",
            "date": "date",
            "sma_20": "numeric",
            "sma_50": "numeric",
            "sma_200": "numeric",
            "rsi": "numeric",
            "macd": "numeric",
            "atr": "numeric",
        },
        "buy_sell_daily": {
            "symbol": "character varying",
            "date": "date",
            "signal": "character varying",
        },
        "trend_template_data": {
            "symbol": "character varying",
            "date": "date",
            "minervini_trend_score": "integer",
            "weinstein_stage": "integer",
        },
        "signal_quality_scores": {
            "symbol": "character varying",
            "date": "date",
            "quality_score": "numeric",
        },
        "swing_trader_scores": {
            "symbol": "character varying",
            "eval_date": "date",
            "swing_score": "numeric",
            "grade": "character varying",
        },
        "algo_positions": {
            "symbol": "character varying",
            "entry_date": "date",
            "entry_price": "numeric",
            "quantity": "integer",
        },
        "algo_trades": {
            "symbol": "character varying",
            "trade_date": "date",
            "exit_price": "numeric",
            "pnl": "numeric",
        },
    }

    def __init__(self, conn=None):
        """
        Initialize validator.

        Args:
            conn: Existing psycopg2 connection, or None to create one
        """
        self.conn = conn
        self.issues: List[Tuple[str, str, str]] = []

    def connect(self, host="localhost", port=5432, user="stocks", password="", database="stocks"):
        """Create database connection."""
        if self.conn:
            return
        try:
            self.conn = psycopg2.connect(
                host=host,
                port=port,
                user=user,
                password=password,
                database=database,
            )
        except Exception as e:
            logger.error(f"Cannot connect to database: {e}")
            raise

    def disconnect(self):
        """Close database connection."""
        if self.conn:
            try:
                self.conn.close()
            except Exception:
                pass
            self.conn = None

    def validate_all(self) -> List[Tuple[str, str, str]]:
        """
        Validate all critical tables.

        Returns: List of (severity, table, message) tuples.
                 severity in ("CRITICAL", "ERROR", "WARNING")
        """
        self.issues = []

        for table_name, required_cols in self.REQUIRED_SCHEMA.items():
            self.validate_table(table_name, required_cols)

        return self.issues

    def validate_table(self, table_name: str, required_columns: Dict[str, str]) -> bool:
        """
        Validate a specific table has required columns with correct types.

        Args:
            table_name: Name of table to validate
            required_columns: Dict of column_name -> expected_type

        Returns:
            True if valid, False if issues found
        """
        if not self.conn:
            self.issues.append(("CRITICAL", table_name, "No database connection"))
            return False

        cur = self.conn.cursor()
        try:
            # Check table exists
            cur.execute("""
                SELECT EXISTS (
                    SELECT FROM information_schema.tables
                    WHERE table_name = %s
                )
            """, (table_name,))
            if not cur.fetchone()[0]:
                self.issues.append(("CRITICAL", table_name, "Table does not exist"))
                return False

            # Get actual columns
            cur.execute("""
                SELECT column_name, udt_name
                FROM information_schema.columns
                WHERE table_name = %s
                ORDER BY ordinal_position
            """, (table_name,))
            actual_cols = {row[0]: row[1] for row in cur.fetchall()}

            # Normalize PostgreSQL type names
            actual_cols = self._normalize_types(actual_cols)

            # Check required columns exist
            valid = True
            for col_name, expected_type in required_columns.items():
                if col_name not in actual_cols:
                    self.issues.append(
                        ("CRITICAL", table_name, f"Missing required column: {col_name}")
                    )
                    valid = False
                else:
                    # Check type compatibility
                    actual_type = actual_cols[col_name]
                    if not self._types_compatible(actual_type, expected_type):
                        self.issues.append(
                            ("ERROR", table_name,
                             f"Column {col_name}: expected {expected_type}, got {actual_type}")
                        )
                        valid = False

            return valid

        except Exception as e:
            self.issues.append(("ERROR", table_name, f"Validation error: {str(e)}"))
            return False
        finally:
            cur.close()

    def validate_data_content(self, table_name: str) -> bool:
        """
        Validate table has recent data (not empty or stale).

        Returns: True if table has recent data, False if empty or stale
        """
        if not self.conn:
            return False

        cur = self.conn.cursor()
        try:
            cur.execute(f"SELECT COUNT(*) FROM {table_name}")
            count = cur.fetchone()[0]

            if count == 0:
                self.issues.append(("WARNING", table_name, "Table is empty"))
                return False

            # Check if table has a date column
            cur.execute("""
                SELECT column_name FROM information_schema.columns
                WHERE table_name = %s AND (column_name LIKE '%%date%%' OR column_name LIKE '%%time%%')
                LIMIT 1
            """, (table_name,))
            date_col = cur.fetchone()
            if date_col:
                date_col_name = date_col[0]
                cur.execute(f"""
                    SELECT MAX({date_col_name}) FROM {table_name}
                """)
                max_date = cur.fetchone()[0]
                if max_date:
                    from datetime import date, timedelta
                    age_days = (date.today() - max_date).days
                    if age_days > 3:
                        self.issues.append(
                            ("WARNING", table_name, f"Data is {age_days} days old (>3 day threshold)")
                        )
                        return False

            return True

        except Exception as e:
            self.issues.append(("ERROR", table_name, f"Content validation error: {str(e)}"))
            return False
        finally:
            cur.close()

    @staticmethod
    def _normalize_types(cols: Dict[str, str]) -> Dict[str, str]:
        """
        Normalize PostgreSQL type names to canonical forms.

        PostgreSQL returns udt_name which may be abbreviated:
        - varchar → character varying
        - int4 → integer
        - float8 → numeric
        """
        mapping = {
            "varchar": "character varying",
            "int4": "integer",
            "int8": "bigint",
            "float8": "numeric",
            "date": "date",
            "timestamp": "timestamp without time zone",
            "bool": "boolean",
        }
        return {k: mapping.get(v, v) for k, v in cols.items()}

    @staticmethod
    def _types_compatible(actual: str, expected: str) -> bool:
        """
        Check if actual type is compatible with expected type.

        Allows some flexibility (e.g., numeric vs float8).
        """
        # Normalize both
        type_map = {
            "numeric": ["float8", "float4", "decimal"],
            "character varying": ["varchar", "text"],
            "integer": ["int4", "int8"],
            "bigint": ["int8"],
            "date": ["date"],
            "boolean": ["bool"],
        }

        # Exact match
        if actual == expected:
            return True

        # Check if actual is in compatible list for expected
        if expected in type_map:
            return actual in type_map[expected]

        return False

    def log_summary(self):
        """Log summary of validation issues."""
        if not self.issues:
            logger.info("✅ Schema validation passed — all tables and columns valid")
            return

        critical = [i for i in self.issues if i[0] == "CRITICAL"]
        errors = [i for i in self.issues if i[0] == "ERROR"]
        warnings = [i for i in self.issues if i[0] == "WARNING"]

        logger.warning(f"\n{'='*70}")
        logger.warning("SCHEMA VALIDATION RESULTS")
        logger.warning(f"{'='*70}")

        if critical:
            logger.error(f"\n❌ CRITICAL ({len(critical)} issues):")
            for _, table, msg in critical:
                logger.error(f"  {table:25s} {msg}")

        if errors:
            logger.error(f"\n⚠️  ERROR ({len(errors)} issues):")
            for _, table, msg in errors:
                logger.error(f"  {table:25s} {msg}")

        if warnings:
            logger.warning(f"\n⚡ WARNING ({len(warnings)} issues):")
            for _, table, msg in warnings:
                logger.warning(f"  {table:25s} {msg}")

        logger.warning(f"\n{'='*70}\n")


def main():
    """Run schema validation."""
    import os
    from pathlib import Path
    from dotenv import load_dotenv
    from credential_manager import get_credential_manager

    env_file = Path(__file__).parent / ".env.local"
    if env_file.exists():
        load_dotenv(env_file)

    credential_manager = get_credential_manager()

    validator = SchemaValidator()
    try:
        validator.connect(
            host=os.getenv("DB_HOST", "localhost"),
            port=int(os.getenv("DB_PORT", 5432)),
            user=os.getenv("DB_USER", "stocks"),
            password=credential_manager.get_db_credentials()["password"],
            database=os.getenv("DB_NAME", "stocks"),
        )

        issues = validator.validate_all()
        validator.log_summary()

        # Check data freshness
        logger.info("\nChecking data freshness...")
        for table in validator.REQUIRED_SCHEMA.keys():
            validator.validate_data_content(table)

        return 0 if not issues else 1

    except Exception as e:
        logger.error(f"Validation failed: {e}")
        return 1
    finally:
        validator.disconnect()


if __name__ == "__main__":
    import sys
    logging.basicConfig(
        level=logging.INFO,
        format="%(asctime)s [%(levelname)s] %(message)s",
    )
    sys.exit(main())
