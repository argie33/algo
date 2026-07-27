"""Freshness panel enhancements: data quality, coverage, and failure patterns.

These functions augment health item data with:
1. Data validity metrics (NULL ratios, duplicates, value ranges)
2. Coverage completeness (symbol/date/sector coverage)
3. Failure pattern analysis (failure rate, windows, MTTR)
4. API diagnostics (rate limits, retry strategy)

Each function returns enriched health item dict with new fields suitable for display.
"""

import logging
from datetime import datetime, timedelta, timezone
from typing import Any

from utils.db import DatabaseContext
from dashboard.data_validation import safe_int, safe_float

logger = logging.getLogger(__name__)


def _rollback_after_error(cur: Any) -> None:
    """Reset an aborted transaction after a caught-and-continue DB error.

    Postgres marks a transaction as failed after any statement error - every later query
    on the same connection raises InFailedSqlTransaction until a ROLLBACK runs. The checks
    below run per-table across ~48 tables on a single shared cursor (passed in from
    market.py's _get_data_status) and treat a single bad table (e.g. a column that doesn't
    exist on that table) as non-fatal, so without this the first such error silently
    cascades and blanks out every remaining table's enrichment for the rest of the request.
    """
    try:
        cur.connection.rollback()
    except Exception as rollback_err:
        logger.debug(f"[FRESHNESS] Failed to rollback after query error: {rollback_err}")


def enrich_health_item_with_data_quality(health_item: dict[str, Any], cur: Any = None) -> dict[str, Any]:
    """Enrich health item with data quality metrics (NULL ratios, duplicates, constraints).

    Args:
        health_item: Health status item dict
        cur: Database cursor (optional - if None, will create own connection)

    Returns:
        Enhanced health_item with new fields:
        - data_quality_issues: List of strings describing issues found
        - null_ratio: Percentage of NULLs in critical columns (if applicable)
        - duplicate_count: Number of duplicate rows detected (if applicable)
        - value_violations: Count of constraint/range violations (if applicable)
        - quality_status: "ok" | "warning" | "error"
    """
    if not isinstance(health_item, dict):
        return health_item

    table_name = health_item.get("tbl") or health_item.get("table_name") or health_item.get("name")
    if not table_name:
        return health_item

    # Only run quality checks for tables that exist and have data
    item_status = health_item.get("st") or health_item.get("status")
    if item_status in ("empty", "error") or health_item.get("row_count") == 0:
        health_item["quality_status"] = "unknown"  # No data to check
        return health_item

    issues = []
    quality_status = "ok"

    try:
        if cur is None:
            with DatabaseContext("read") as cur_new:
                issues, quality_status = _run_data_quality_checks(table_name, cur_new)
        else:
            issues, quality_status = _run_data_quality_checks(table_name, cur)

        health_item["data_quality_issues"] = issues
        health_item["quality_status"] = quality_status

    except Exception as e:
        logger.warning(f"[FRESHNESS] Data quality check failed for {table_name}: {e}")
        health_item["quality_status"] = "unknown"

    return health_item


def _run_data_quality_checks(table_name: str, cur: Any) -> tuple[list[str], str]:
    """Execute data quality checks for a table.

    Returns:
        (issues_list, quality_status)
        - issues_list: List of issue descriptions
        - quality_status: "ok" | "warning" | "error"
    """
    issues = []

    # Define critical columns per table (where NULLs are unacceptable)
    critical_columns_map = {
        "price_daily": ["symbol", "date", "close", "volume"],
        "stock_scores": ["symbol", "date", "signal_strength"],
        "market_health_daily": ["date", "vix_level", "market_regime"],
        "market_exposure_daily": ["date", "tech_exposure", "health_exposure"],
        "technical_data_daily": ["symbol", "date", "rsi", "macd"],
        "trend_template_data": ["symbol", "date", "weinstein_stage"],
        "buy_sell_daily": ["symbol", "date", "signal", "strength"],
        "algo_signals": ["symbol", "signal_date", "signal_active"],
        "algo_positions": ["symbol", "entry_date", "status"],
        "algo_trades": ["symbol", "entry_date", "side"],
    }

    critical_cols = critical_columns_map.get(table_name, ["created_at"])

    # Check 1: NULL ratio in critical columns
    # CRITICAL FIX: a bare `LIMIT 1000000` on a query with no FROM-clause subquery only
    # limits the aggregate's own 1-row result set, not the rows scanned to compute it - so
    # on price_daily (8.7M rows) this was a full unbounded table scan (confirmed live:
    # ~0.35s per column) run synchronously inside every /api/algo/data-status request, the
    # dashboard's core health-panel endpoint. Wrapping the scan itself in a LIMIT'd subquery
    # makes the cap actually bound the work done, matching the sampling this function's own
    # docstring ("Check 1: NULL ratio...") implies was intended.
    sample_size = 200_000
    for col in critical_cols:
        try:
            cur.execute(f"""
                SELECT
                    COUNT(*) as total,
                    COUNT(CASE WHEN "{col}" IS NULL THEN 1 END) as null_count
                FROM (SELECT "{col}" FROM "{table_name}" LIMIT %s) sample
            """, (sample_size,))
            result = cur.fetchone()
            if result:
                total = result[0] or 0
                null_count = result[1] or 0
                if total > 0:
                    null_ratio = (null_count / total) * 100
                    if null_ratio > 5:
                        issues.append(f"{col}: {null_ratio:.1f}% NULL (threshold 5%, sampled)")
        except Exception as e:
            _rollback_after_error(cur)
            logger.debug(f"[QUALITY] NULL check failed for {table_name}.{col}: {e}")

    # Check 2: Duplicate rows (on primary key columns if identifiable)
    # CRITICAL FIX: `COUNT(DISTINCT *::text)` is not valid Postgres syntax - `*` cannot be
    # cast directly (confirmed live: raises psycopg2.errors.SyntaxError every single call,
    # silently swallowed by the except below at debug level) - so this check has never once
    # actually run; "duplicate rows detected" was dead functionality from the day it shipped.
    # Fixed by casting the whole row via a table-qualified reference in a bounded subquery,
    # which is also what actually caps the scan (see Check 1's fix for why the old bare
    # LIMIT didn't bound anything).
    try:
        cur.execute(f"""
            SELECT COUNT(*) - COUNT(DISTINCT row_text) as duplicate_count
            FROM (
                SELECT (t.*)::text as row_text
                FROM "{table_name}" t
                LIMIT %s
            ) sample
        """, (sample_size,))
        result = cur.fetchone()
        if result and result[0]:
            dup_count = result[0]
            if dup_count > 0:
                issues.append(f"{dup_count} exact duplicate rows detected (sampled)")
    except Exception as e:
        _rollback_after_error(cur)
        logger.debug(f"[QUALITY] Duplicate check failed for {table_name}: {e}")

    # Check 3: Table-specific value range violations
    if table_name == "price_daily":
        try:
            cur.execute("""
                SELECT COUNT(*) as violations
                FROM price_daily
                WHERE close <= 0 OR volume < 0 OR high < low
                LIMIT 1000
            """)
            result = cur.fetchone()
            if result and result[0] and result[0] > 0:
                issues.append(f"{result[0]} price constraint violations (negative/inverted)")
        except Exception as e:
            _rollback_after_error(cur)
            logger.debug(f"[QUALITY] Price range check failed: {e}")

    elif table_name == "technical_data_daily":
        try:
            cur.execute("""
                SELECT COUNT(*) as violations
                FROM technical_data_daily
                WHERE rsi < 0 OR rsi > 100 OR macd_signal IS NULL
                LIMIT 1000
            """)
            result = cur.fetchone()
            if result and result[0] and result[0] > 0:
                issues.append(f"{result[0]} technical indicator violations (RSI out of range)")
        except Exception as e:
            _rollback_after_error(cur)
            logger.debug(f"[QUALITY] Technical check failed: {e}")

    elif table_name == "market_health_daily":
        try:
            cur.execute("""
                SELECT COUNT(*) as violations
                FROM market_health_daily
                WHERE vix_level < 0 OR vix_level > 150 OR market_regime NOT IN ('bull', 'bear', 'neutral')
                LIMIT 1000
            """)
            result = cur.fetchone()
            if result and result[0] and result[0] > 0:
                issues.append(f"{result[0]} market health violations (VIX or regime invalid)")
        except Exception as e:
            _rollback_after_error(cur)
            logger.debug(f"[QUALITY] Market health check failed: {e}")

    # Determine quality status based on issue severity
    if not issues:
        quality_status = "ok"
    elif any("NULL" in issue or "violation" in issue for issue in issues):
        quality_status = "error"  # Critical issues
    else:
        quality_status = "warning"

    return issues, quality_status


def enrich_health_item_with_coverage(health_item: dict[str, Any], cur: Any = None) -> dict[str, Any]:
    """Enrich health item with coverage completeness metrics.

    Args:
        health_item: Health status item dict
        cur: Database cursor (optional)

    Returns:
        Enhanced health_item with new fields:
        - symbol_coverage_pct: Percentage of expected symbols present
        - missing_symbols: List of symbols not found (if applicable)
        - coverage_status: "complete" | "partial" | "sparse"
    """
    if not isinstance(health_item, dict):
        return health_item

    table_name = health_item.get("tbl") or health_item.get("table_name") or health_item.get("name")
    if not table_name:
        return health_item

    # Only check coverage for tables expected to hold the full active-symbol universe daily.
    # algo_positions/algo_signals/algo_trades are inherently selective (only symbols with an
    # open position, a generated signal, or an executed trade) - "coverage vs. full universe"
    # isn't a meaningful metric for them and would falsely flag a healthy, quiet trading day
    # as "SPARSE" coverage.
    symbol_tables = {
        "price_daily",
        "technical_data_daily",
        "stock_scores",
        "buy_sell_daily",
    }

    if table_name not in symbol_tables:
        return health_item

    try:
        if cur is None:
            with DatabaseContext("read") as cur_new:
                coverage_pct, missing_list = _calculate_coverage(table_name, cur_new)
        else:
            coverage_pct, missing_list = _calculate_coverage(table_name, cur)

        if coverage_pct is not None:
            health_item["symbol_coverage_pct"] = coverage_pct
            if missing_list:
                health_item["missing_symbols"] = missing_list[:5]  # Top 5 missing

            if coverage_pct >= 95:
                health_item["coverage_status"] = "complete"
            elif coverage_pct >= 80:
                health_item["coverage_status"] = "partial"
            else:
                health_item["coverage_status"] = "sparse"

    except Exception as e:
        logger.warning(f"[FRESHNESS] Coverage check failed for {table_name}: {e}")
        health_item["coverage_status"] = "unknown"

    return health_item


def _calculate_coverage(table_name: str, cur: Any) -> tuple[float | None, list[str]]:
    """Calculate symbol coverage for a table.

    Returns:
        (coverage_percentage, missing_symbol_list)
    """
    try:
        # CRITICAL FIX: `universe_stocks` does not exist in this schema at all (confirmed live:
        # psycopg2.errors.UndefinedTable on every call) - the real active-symbol table is
        # `stock_symbols`, and its boolean column is named `active`, not `is_active` (also
        # confirmed live - `is_active` doesn't exist there either, per
        # information_schema.columns). This made every coverage check silently fail on every
        # request for every symbol table (price_daily, stock_scores, algo_positions, etc.),
        # logging a warning each time and never once actually reporting coverage.
        cur.execute("SELECT COUNT(*) as total_symbols FROM stock_symbols WHERE active = true")
        result = cur.fetchone()
        expected_count = result[0] if result else 0

        if expected_count == 0:
            return None, []

        # stock_scores holds one current row per symbol (no `date` column - see
        # information_schema.columns) rather than a daily snapshot history like price_daily/
        # technical_data_daily/buy_sell_daily, so "latest date" filtering doesn't apply there.
        latest_date_filter = "" if table_name == "stock_scores" else f'WHERE date = (SELECT MAX(date) FROM "{table_name}")'

        # Get symbols in table for latest date
        cur.execute(f"""
            SELECT COUNT(DISTINCT symbol) as loaded_symbols
            FROM "{table_name}"
            {latest_date_filter}
        """)
        result = cur.fetchone()
        loaded_count = result[0] if result else 0

        coverage_pct = (loaded_count / expected_count) * 100 if expected_count > 0 else 0

        # Get list of missing symbols (top 5)
        # CRITICAL FIX: same universe_stocks/is_active/market_cap issues as the count query
        # above - stock_symbols has no market_cap column at all, so ordering by it would still
        # fail even after fixing the table/column names. Ordered alphabetically instead; this
        # is a "which symbols are missing" list, not a ranked-by-importance one.
        missing_symbols = []
        try:
            cur.execute(f"""
                SELECT symbol
                FROM stock_symbols
                WHERE active = true
                AND symbol NOT IN (
                    SELECT DISTINCT symbol FROM "{table_name}"
                    {latest_date_filter}
                )
                ORDER BY symbol
                LIMIT 5
            """)
            missing_symbols = [row[0] for row in cur.fetchall()]
        except Exception as e:
            _rollback_after_error(cur)
            logger.debug(f"[COVERAGE] Could not retrieve missing symbols for {table_name}: {e}")

        return coverage_pct, missing_symbols

    except Exception as e:
        _rollback_after_error(cur)
        logger.warning(f"[COVERAGE] Coverage calculation failed for {table_name}: {e}")
        return None, []


def enrich_health_item_with_failure_pattern(health_item: dict[str, Any], cur: Any = None) -> dict[str, Any]:
    """Enrich health item with failure pattern analysis (rate, windows, MTTR).

    Args:
        health_item: Health status item dict
        cur: Database cursor (optional)

    Returns:
        Enhanced health_item with new fields:
        - failure_rate_30d: % of failures in last 30 runs
        - failure_pattern: Description of failure windows (e.g. "Mondays only")
        - mttr_hours: Mean time to recovery in hours
        - last_5_runs: String showing last 5 run statuses (✓ ✗ ✓ ✓ ✓)
        - recovery_trend: "improving" | "stable" | "degrading"
    """
    if not isinstance(health_item, dict):
        return health_item

    table_name = health_item.get("tbl") or health_item.get("table_name") or health_item.get("name")
    if not table_name:
        return health_item

    try:
        if cur is None:
            with DatabaseContext("read") as cur_new:
                pattern_data = _analyze_failure_patterns(table_name, cur_new)
        else:
            pattern_data = _analyze_failure_patterns(table_name, cur)

        health_item.update(pattern_data)

    except Exception as e:
        logger.warning(f"[FRESHNESS] Failure pattern analysis failed for {table_name}: {e}")

    return health_item


def _analyze_failure_patterns(table_name: str, cur: Any) -> dict[str, Any]:
    """Analyze failure patterns from loader execution history.

    Returns:
        Dict with failure metrics
    """
    result = {
        "failure_rate_30d": None,
        "failure_pattern": None,
        "mttr_hours": None,
        "last_5_runs": None,
        "recovery_trend": None,
    }

    try:
        # Get last 30 runs
        cur.execute("""
            SELECT status, execution_completed, execution_started
            FROM data_loader_status_history
            WHERE table_name = %s
            ORDER BY execution_completed DESC
            LIMIT 30
        """, (table_name,))

        runs = cur.fetchall()
        if not runs:
            return result

        # Calculate failure rate
        failures = sum(1 for r in runs if r[0] in ("FAILED", "TIMEOUT"))
        failure_rate = (failures / len(runs) * 100) if runs else 0
        result["failure_rate_30d"] = round(failure_rate, 1)

        # Analyze failure windows (time-of-day patterns)
        failure_times = []
        for run in runs:
            if run[0] in ("FAILED", "TIMEOUT") and run[1]:  # execution_completed
                if hasattr(run[1], "hour"):
                    failure_times.append(run[1].hour)

        if failure_times:
            # Check if failures cluster around specific hours
            hour_counts = {}
            for h in failure_times:
                hour_counts[h] = hour_counts.get(h, 0) + 1

            most_common_hour = max(hour_counts, key=hour_counts.get)
            if hour_counts[most_common_hour] >= len(failure_times) * 0.6:
                result["failure_pattern"] = f"Typically around {most_common_hour}:00"

        # Calculate MTTR (mean time to recovery)
        mttr_times = []
        in_failure = False
        failure_start = None

        for run in reversed(runs):  # Process chronologically
            status, exec_completed = run[0], run[1]
            if status in ("FAILED", "TIMEOUT"):
                if not in_failure:
                    in_failure = True
                    failure_start = exec_completed
            else:  # Success
                if in_failure and failure_start and exec_completed:
                    recovery_time = (exec_completed - failure_start).total_seconds() / 3600
                    mttr_times.append(recovery_time)
                    in_failure = False

        if mttr_times:
            avg_mttr = sum(mttr_times) / len(mttr_times)
            result["mttr_hours"] = round(avg_mttr, 1)

        # Last 5 runs status summary
        last_5 = [("✓" if r[0] == "COMPLETED" else "✗") for r in runs[:5]]
        result["last_5_runs"] = " ".join(last_5)

        # Recovery trend (are recent runs more successful?)
        if len(runs) >= 10:
            recent_5_failures = sum(1 for r in runs[:5] if r[0] in ("FAILED", "TIMEOUT"))
            older_5_failures = sum(1 for r in runs[5:10] if r[0] in ("FAILED", "TIMEOUT"))

            if recent_5_failures < older_5_failures:
                result["recovery_trend"] = "improving"
            elif recent_5_failures > older_5_failures:
                result["recovery_trend"] = "degrading"
            else:
                result["recovery_trend"] = "stable"

    except Exception as e:
        _rollback_after_error(cur)
        logger.debug(f"[FAILURE_PATTERN] Analysis failed for {table_name}: {e}")

    return result


def enrich_health_item_with_api_diagnostics(health_item: dict[str, Any]) -> dict[str, Any]:
    """Enrich health item with API diagnostics (rate limits, retry strategy, credentials).

    Args:
        health_item: Health status item dict

    Returns:
        Enhanced health_item with new fields:
        - api_status: "ok" | "rate_limited" | "auth_failed" | "service_down"
        - rate_limit_quota: String like "98/100 daily calls used"
        - rate_limit_resets: Timestamp when quota resets
        - retry_strategy: String like "exponential backoff, next 3:35pm"
        - credential_expiry: Days until credentials expire
    """
    if not isinstance(health_item, dict):
        return health_item

    # Extract API diagnostics from error message if available
    error_msg = health_item.get("loader_error") or health_item.get("error_message") or ""

    # NOTE: no real quota-reset/backoff-schedule data is tracked anywhere yet (the loader
    # status columns this was meant to read - http_status_code/rate_limit_quota, added by
    # migration 1164 - have no production callers populating them). Report the category only;
    # do not fabricate specific reset times or retry windows not backed by real data.
    if "rate limit" in error_msg.lower() or "quota" in error_msg.lower():
        health_item["api_status"] = "rate_limited"
        health_item["retry_strategy"] = "exponential backoff (reset time not tracked)"
    elif "auth" in error_msg.lower() or "credential" in error_msg.lower():
        health_item["api_status"] = "auth_failed"
        health_item["retry_strategy"] = "credentials need rotation"
    elif "503" in error_msg or "service" in error_msg.lower():
        health_item["api_status"] = "service_down"
        health_item["retry_strategy"] = "service unavailable (retry timing not tracked)"
    else:
        health_item["api_status"] = "ok"

    return health_item
