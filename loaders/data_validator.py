"""Data validation utilities for loader output quality checks.

Validates loader output against data quality rules before persistence.
Catches issues early: missing data, duplicates, schema violations, outliers.
"""

import logging
from datetime import datetime
from typing import Any

logger = logging.getLogger(__name__)


class DataValidator:
    """Validates loader output tables for data quality."""

    def __init__(self, conn: Any):
        self.conn = conn
        self.errors: list[str] = []
        self.warnings: list[str] = []

    def validate_table_not_empty(self, table_name: str, min_rows: int = 1) -> bool:
        cur = self.conn.cursor()
        cur.execute(f"SELECT COUNT(*) FROM {table_name}")
        count = cur.fetchone()[0]

        if count < min_rows:
            msg = f"{table_name}: Only {count} rows (expected >= {min_rows})"
            self.errors.append(msg)
            return False
        return True

    def validate_no_duplicates(self, table_name: str, key_columns: list[str]) -> bool:
        cur = self.conn.cursor()
        cols = ", ".join(key_columns)
        query = f"""
            SELECT COUNT(*) FROM (
                SELECT {cols}, COUNT(*) as cnt
                FROM {table_name}
                GROUP BY {cols}
                HAVING COUNT(*) > 1
            ) x
        """
        cur.execute(query)
        dup_count = cur.fetchone()[0]

        if dup_count > 0:
            msg = f"{table_name}: {dup_count} duplicate records on {key_columns}"
            self.warnings.append(msg)
            return False
        return True

    def validate_data_freshness(self, table_name: str, date_column: str, max_age_hours: int = 24) -> bool:
        cur = self.conn.cursor()
        query = f"""
            SELECT COUNT(*) FROM {table_name}
            WHERE {date_column} < CURRENT_TIMESTAMP - INTERVAL '{max_age_hours} hours'
        """
        cur.execute(query)
        stale_count = cur.fetchone()[0]

        cur.execute(f"SELECT COUNT(*) FROM {table_name}")
        total_count = cur.fetchone()[0]

        if total_count > 0:
            stale_pct = 100 * stale_count / total_count
            if stale_pct > 5:
                msg = f"{table_name}: {stale_pct:.1f}% data older than {max_age_hours}h"
                self.warnings.append(msg)
                return False
        return True

    def validate_no_null_columns(self, table_name: str, critical_columns: list[str]) -> bool:
        cur = self.conn.cursor()
        has_nulls = False

        for col in critical_columns:
            query = f"SELECT COUNT(*) FROM {table_name} WHERE {col} IS NULL"
            cur.execute(query)
            null_count = cur.fetchone()[0]

            if null_count > 0:
                msg = f"{table_name}.{col}: {null_count} NULL values"
                self.warnings.append(msg)
                has_nulls = True

        return not has_nulls

    def validate_value_range(self, table_name: str, column: str, min_val: float, max_val: float) -> bool:
        cur = self.conn.cursor()
        query = f"""
            SELECT COUNT(*) FROM {table_name}
            WHERE {column} < {min_val} OR {column} > {max_val}
        """
        cur.execute(query)
        outlier_count = cur.fetchone()[0]

        if outlier_count > 0:
            msg = f"{table_name}.{column}: {outlier_count} outliers outside [{min_val}, {max_val}]"
            self.warnings.append(msg)
            return False
        return True

    def validate_price_data(self) -> bool:
        try:
            self.validate_table_not_empty("price_daily", min_rows=100000)
            self.validate_no_duplicates("price_daily", ["symbol", "date"])
            self.validate_data_freshness("price_daily", "date", max_age_hours=24)
            self.validate_no_null_columns("price_daily", ["open", "high", "low", "close", "volume"])
            self.validate_value_range("price_daily", "volume", 0, 1e12)
            return len(self.errors) == 0
        except Exception as e:
            self.errors.append(f"price_daily validation error: {e!s}")
            return False

    def validate_technical_data(self) -> bool:
        try:
            self.validate_table_not_empty("technical_data_daily", min_rows=10000)
            self.validate_no_duplicates("technical_data_daily", ["symbol", "date"])
            self.validate_data_freshness("technical_data_daily", "date", max_age_hours=24)
            self.validate_value_range("technical_data_daily", "rsi", 0, 100)
            return len(self.errors) == 0
        except Exception as e:
            self.errors.append(f"technical_data_daily validation error: {e!s}")
            return False

    def validate_stock_scores(self) -> bool:
        try:
            self.validate_table_not_empty("stock_scores", min_rows=1000)
            self.validate_no_duplicates("stock_scores", ["symbol"])
            self.validate_value_range("stock_scores", "composite_score", 0, 100)
            return len(self.errors) == 0
        except Exception as e:
            self.errors.append(f"stock_scores validation error: {e!s}")
            return False

    def validate_buy_sell_signals(self) -> bool:
        try:
            self.validate_table_not_empty("buy_sell_daily", min_rows=1000)
            self.validate_no_duplicates("buy_sell_daily", ["symbol", "date", "signal"])
            self.validate_data_freshness("buy_sell_daily", "date", max_age_hours=24)
            self.validate_no_null_columns("buy_sell_daily", ["signal", "strength"])
            self.validate_value_range("buy_sell_daily", "strength", 0, 100)
            return len(self.errors) == 0
        except Exception as e:
            self.errors.append(f"buy_sell_daily validation error: {e!s}")
            return False

    def get_report(self) -> dict[str, Any]:
        return {
            "timestamp": datetime.now().isoformat(),
            "valid": len(self.errors) == 0,
            "errors": self.errors,
            "warnings": self.warnings,
        }

    def log_report(self) -> dict[str, Any]:
        """Log validation results."""
        report = self.get_report()
        if report["valid"]:
            logger.info("Data validation: ALL CHECKS PASSED")
        else:
            logger.error(f"Data validation FAILED: {len(report['errors'])} errors")
            for error in report["errors"]:
                logger.error(f"  - {error}")

        if report["warnings"]:
            for warning in report["warnings"]:
                logger.warning(f"  - {warning}")

        return report
