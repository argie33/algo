#!/usr/bin/env python3
"""
UNIFIED Data Age Validator — Single Source of Truth for Data Freshness

Consolidates watermark tracking and freshness checking into one system.
Uses rules from utils/validation/freshness_config.py as ground truth.
"""

import logging
from datetime import date, datetime
from typing import Any, cast

from utils.db.context import DatabaseContext
from utils.validation.freshness_config import get_freshness_rule

logger = logging.getLogger(__name__)


class DataAgeValidator:
    """Single source of truth for data freshness checks."""

    @staticmethod
    def check(
        table_name: str,
        date_column: str = "date",
        current_date: date | None = None,
        verbose: bool = False,
    ) -> dict[str, Any]:
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
            if "critical" not in rule or rule["critical"] is None:
                # A missing 'critical' flag is a config problem, not caused by the DB error above.
                raise ValueError(f"Rule for {table_name} missing required 'critical' flag") from None
            return {
                "is_fresh": False,
                "age_days": None,
                "max_date": None,
                "rule": rule,
                "message": f"✗ {table_name}: Query failed — {e}",
                "is_critical": rule["critical"],
            }

        # Parse and normalize date
        if max_date is None:
            if "critical" not in rule or rule["critical"] is None:
                raise ValueError(f"Rule for {table_name} missing required 'critical' flag")
            return {
                "is_fresh": False,
                "age_days": None,
                "max_date": None,
                "rule": rule,
                "message": f"✗ {table_name}: No data in table",
                "is_critical": rule["critical"],
            }

        if isinstance(max_date, datetime):
            max_date = max_date.date()
        elif isinstance(max_date, str):
            try:
                max_date = datetime.fromisoformat(max_date).date()
            except (ValueError, AttributeError):
                if "critical" not in rule or rule["critical"] is None:
                    # A missing 'critical' flag is a config problem, not caused by the parse error above.
                    raise ValueError(f"Rule for {table_name} missing required 'critical' flag") from None
                return {
                    "is_fresh": False,
                    "age_days": None,
                    "max_date": None,
                    "rule": rule,
                    "message": f"✗ {table_name}: Invalid date format {max_date}",
                    "is_critical": rule["critical"],
                }

        # Calculate age
        age_days = (current_date - max_date).days

        # Strictly enforce freshness thresholds
        # Markets are closed on weekends, so data from Friday may be used on Saturday/Sunday
        # BUT only if max_age_days explicitly allows it (e.g., price_weekly allows 7 days)
        # For daily data (max_age_days=1), we should NOT accept 2-day-old data on Sunday
        # just because markets are closed.
        threshold_days = rule["max_age_days"]

        # Apply strict threshold: only give slight grace for same-day-of-week data on weekends
        # (E.g., Friday data can be used Saturday morning, but not 2+ days old on Sunday)
        weekday = current_date.weekday()  # 0=Mon ... 6=Sun
        if weekday in (5, 6):  # Saturday or Sunday
            # Weekend data grace: allow data from 1 more day ago if markets are closed
            # But only for tables specifically marked as "market_data" (prices, ETF data)
            # For computed data (signals, scores, risk), enforce strict threshold
            # CRITICAL: False default masks missing criticality flag - should validate
            if "price" in rule.get("description", "").lower():
                # Price/market data can be 1 extra day old on weekends (Saturday allows Fri, Sunday allows Fri)
                adjusted_threshold = threshold_days + 1
            else:
                # Computed data must meet strict threshold regardless of day
                adjusted_threshold = threshold_days
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
            logger.warning(f"[{table_name}] Data is {age_days} days old (threshold {adjusted_threshold}d)")

        message = f"{status} {table_name}: {age_days}d old (threshold {adjusted_threshold}d) — {level}"
        if verbose and rule:
            applies_to = rule.get("applies_to")
            applies_to_str = ", ".join(applies_to) if applies_to else ""
            message += f" [applies to: {applies_to_str}]"

        if "critical" not in rule or rule["critical"] is None:
            raise ValueError(f"Rule for {table_name} missing required 'critical' flag")
        return {
            "is_fresh": is_fresh,
            "age_days": age_days,
            "max_date": max_date,
            "threshold_days": adjusted_threshold,
            "rule": rule,
            "message": message,
            "is_critical": rule["critical"],
        }

    @staticmethod
    def is_fresh(
        table_name: str,
        date_column: str = "date",
        current_date: date | None = None,
    ) -> bool:
        """Quick boolean check: is table data fresh?"""
        result = DataAgeValidator.check(table_name, date_column, current_date)
        return cast(bool, result["is_fresh"])

    @staticmethod
    def check_multiple(
        tables: dict[str, str],
        current_date: date | None = None,
    ) -> dict[str, Any]:
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
        symbol: str | None = None,
        granularity: str = "symbol",
    ) -> date | None:
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
        symbol: str | None = None,
        granularity: str = "symbol",
        rows_loaded: int = 0,
    ) -> bool:
        """Record successful watermark advance for incremental loading."""
        try:
            from utils.data.watermark import WatermarkManager

            mgr = WatermarkManager(loader_name, table_name, granularity=granularity)
            return mgr.advance_watermark(new_watermark, symbol=symbol, rows_loaded=rows_loaded)
        except Exception as e:
            raise RuntimeError(f"Operation failed: {e}") from e


# Backwards compatibility wrappers
def is_fresh(
    last_loaded_date: Any | None,
    data_type: str = "generic",
    today: date | None = None,
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
    last_loaded_date: Any | None,
    data_type: str = "generic",
    today: date | None = None,
    context: str = "",
) -> dict[str, Any]:
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
