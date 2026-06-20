#!/usr/bin/env python3
"""
UNIFIED Data Age Validator — Single Source of Truth for Data Freshness

Consolidates watermark tracking and freshness checking into one system.
Uses rules from utils/validation/freshness_config.py as ground truth.
"""

import logging
from datetime import date, datetime
from typing import Any, Dict, Optional, cast

from utils.db.context import DatabaseContext
from utils.validation.freshness_config import get_freshness_rule


logger = logging.getLogger(__name__)


class DataAgeValidator:
    """Single source of truth for data freshness checks."""

    @staticmethod
    def check(
        table_name: str,
        date_column: str = "date",
        current_date: Optional[date] = None,
        verbose: bool = False,
    ) -> Dict[str, Any]:
        """Check if table data is fresh.

        Args:
            table_name: Table to check
            date_column: Column containing the date (default: 'date')
            current_date: Reference date (default: today)
            verbose: Include additional details

        Returns:
            Dict with: is_fresh, age_days, max_date, rule, message, is_critical
        """
        if current_date is None:
            current_date = date.today()
        elif isinstance(current_date, datetime):
            current_date = current_date.date()

        # Get freshness rule
        rule = get_freshness_rule(table_name)
        if rule is None:
            return {
                "is_fresh": True,
                "age_days": None,
                "max_date": None,
                "rule": None,
                "message": f"✓ {table_name} (no rule defined, assuming fresh)",
                "is_critical": False,
            }

        # Query for latest date
        try:
            with DatabaseContext("read") as cur:
                import psycopg2.sql

                cur.execute(
                    psycopg2.sql.SQL("SELECT MAX({}) FROM {}").format(
                        psycopg2.sql.Identifier(date_column),
                        psycopg2.sql.Identifier(table_name),
                    )
                )
                result = cur.fetchone()
                max_date = result[0] if result else None
        except (psycopg2.DatabaseError, psycopg2.OperationalError) as e:
            logger.error(f"[{table_name}] Could not query {date_column}: {e}")
            return {
                "is_fresh": False,
                "age_days": None,
                "max_date": None,
                "rule": rule,
                "message": f"✗ {table_name}: Query failed — {e}",
                "is_critical": rule.get("critical", False),
            }

        # Parse and normalize date
        if max_date is None:
            return {
                "is_fresh": False,
                "age_days": None,
                "max_date": None,
                "rule": rule,
                "message": f"✗ {table_name}: No data in table",
                "is_critical": rule.get("critical", False),
            }

        if isinstance(max_date, datetime):
            max_date = max_date.date()
        elif isinstance(max_date, str):
            try:
                max_date = datetime.fromisoformat(max_date).date()
            except (ValueError, AttributeError):
                return {
                    "is_fresh": False,
                    "age_days": None,
                    "max_date": None,
                    "rule": rule,
                    "message": f"✗ {table_name}: Invalid date format {max_date}",
                    "is_critical": rule.get("critical", False),
                }

        # Calculate age
        age_days = (current_date - max_date).days

        # Adjust for weekends: Friday data stays "fresh" through Sunday
        weekday = current_date.weekday()  # 0=Mon ... 6=Sun
        threshold_days = rule["max_age_days"]
        if weekday == 5:  # Saturday: Friday data is 1 day old → +1
            adjusted_threshold = threshold_days + 1
        elif weekday == 6:  # Sunday: Friday data is 2 days old → +2
            adjusted_threshold = threshold_days + 2
        else:
            adjusted_threshold = threshold_days

        is_fresh = age_days <= adjusted_threshold

        # Format message
        if is_fresh:
            status = "✓"
            level = "OK"
        else:
            status = "✗"
            level = "STALE"
            logger.warning(
                f"[{table_name}] Data is {age_days} days old (threshold {adjusted_threshold}d)"
            )

        message = f"{status} {table_name}: {age_days}d old (threshold {adjusted_threshold}d) — {level}"
        if verbose and rule:
            message += f" [applies to: {', '.join(rule.get('applies_to', []))}]"

        return {
            "is_fresh": is_fresh,
            "age_days": age_days,
            "max_date": max_date,
            "threshold_days": adjusted_threshold,
            "rule": rule,
            "message": message,
            "is_critical": rule.get("critical", False),
        }

    @staticmethod
    def is_fresh(
        table_name: str,
        date_column: str = "date",
        current_date: Optional[date] = None,
    ) -> bool:
        """Quick boolean check: is table data fresh?"""
        result = DataAgeValidator.check(table_name, date_column, current_date)
        return cast(bool, result["is_fresh"])

    @staticmethod
    def check_multiple(
        tables: Dict[str, str],
        current_date: Optional[date] = None,
    ) -> Dict[str, Any]:
        """Check freshness of multiple tables at once.

        Args:
            tables: Dict of {table_name: date_column}
            current_date: Reference date

        Returns:
            Dict with: all_fresh, stale_tables, critical_stale, results, messages
        """
        if current_date is None:
            current_date = date.today()

        all_fresh = True
        stale_tables = []
        critical_stale = []
        results = {}
        messages = []

        for table_name, date_column in tables.items():
            result = DataAgeValidator.check(table_name, date_column, current_date)
            results[table_name] = result
            messages.append(result["message"])

            if not result["is_fresh"]:
                all_fresh = False
                stale_tables.append(table_name)
                if result["is_critical"]:
                    critical_stale.append(table_name)

        return {
            "all_fresh": all_fresh,
            "stale_tables": stale_tables,
            "critical_stale": critical_stale,
            "results": results,
            "messages": messages,
        }

    @staticmethod
    def get_loader_watermark(
        loader_name: str,
        table_name: str,
        symbol: Optional[str] = None,
        granularity: str = "symbol",
    ) -> Optional[date]:
        """Get the watermark (last successfully loaded date) for a loader."""
        try:
            from utils.data.watermark import WatermarkManager

            mgr = WatermarkManager(loader_name, table_name, granularity=granularity)
            return mgr.get_current_watermark(symbol=symbol)
        except Exception as e:
            raise RuntimeError(f"Operation failed: {e}") from e

    @staticmethod
    def record_loader_watermark(
        loader_name: str,
        table_name: str,
        new_watermark: date,
        symbol: Optional[str] = None,
        granularity: str = "symbol",
        rows_loaded: int = 0,
    ) -> bool:
        """Record successful watermark advance for incremental loading."""
        try:
            from utils.data.watermark import WatermarkManager

            mgr = WatermarkManager(loader_name, table_name, granularity=granularity)
            return mgr.advance_watermark(
                new_watermark, symbol=symbol, rows_loaded=rows_loaded
            )
        except Exception as e:
            raise RuntimeError(f"Operation failed: {e}") from e


# Backwards compatibility wrappers
def is_fresh(
    last_loaded_date: Optional[Any],
    data_type: str = "generic",
    today: Optional[date] = None,
) -> bool:
    """DEPRECATED: Use DataAgeValidator.check() instead."""
    if today is None:
        today = date.today()

    try:
        if isinstance(last_loaded_date, datetime):
            loaded_date = last_loaded_date.date()
        elif isinstance(last_loaded_date, date):
            loaded_date = last_loaded_date
        elif isinstance(last_loaded_date, str):
            loaded_date = date.fromisoformat(last_loaded_date)
        else:
            return False

        age = (today - loaded_date).days
        return age <= 3
    except (ValueError, TypeError, AttributeError):
        return False


def check_freshness(
    last_loaded_date: Optional[Any],
    data_type: str = "generic",
    today: Optional[date] = None,
    context: str = "",
) -> Dict[str, Any]:
    """DEPRECATED: Use DataAgeValidator.check() instead."""
    if today is None:
        today = date.today()

    if last_loaded_date is None:
        return {
            "is_fresh": False,
            "age_days": -1,
            "threshold_days": 3,
            "message": f"[{data_type}] Data missing {context}".strip(),
            "last_loaded_date": None,
        }

    try:
        if isinstance(last_loaded_date, datetime):
            loaded_date = last_loaded_date.date()
        elif isinstance(last_loaded_date, date):
            loaded_date = last_loaded_date
        elif isinstance(last_loaded_date, str):
            loaded_date = date.fromisoformat(last_loaded_date)
        else:
            return {
                "is_fresh": False,
                "age_days": -1,
                "threshold_days": 3,
                "message": f"[{data_type}] Invalid date type",
                "last_loaded_date": None,
            }

        age = (today - loaded_date).days
        is_fresh_val = age <= 3
        msg = f"[{data_type}] {'Fresh' if is_fresh_val else 'STALE'} ({age}d old) {context}".strip()
        return {
            "is_fresh": is_fresh_val,
            "age_days": age,
            "threshold_days": 3,
            "message": msg,
            "last_loaded_date": loaded_date,
        }
    except Exception as e:
        return {
            "is_fresh": False,
            "age_days": -1,
            "threshold_days": 3,
            "message": f"[{data_type}] Error checking freshness: {e}",
            "last_loaded_date": None,
        }
