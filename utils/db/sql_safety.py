"""
SQL Safety Module - Prevent Injection and Enforce Best Practices

Provides safe wrappers for dynamic SQL queries where table/column names
must be dynamically constructed (cannot use parameterized queries for identifiers).

All dynamic SQL patterns are validated against whitelists before execution.
"""

import re
from typing import Any

# Known safe tables (whitelist for dynamic table names)
# Security: M-001 SQL injection prevention - table names validated against whitelist
SAFE_TABLES = {
    # Algo core
    "algo_metrics_daily",
    "algo_performance_daily",
    "algo_performance_metrics",
    "algo_risk_daily",
    "algo_trades",
    "algo_trades_archive",
    "algo_positions",
    "algo_signals",
    "algo_signals_evaluated",
    "algo_portfolio_snapshots",
    "algo_audit_log",
    "algo_reconciliation_log",
    "algo_notifications",
    "algo_data_patrol",
    "algo_trade_adds",
    "algo_tca",
    "algo_information_coefficient",
    "algo_model_registry",
    "algo_champion_challenger",
    "algo_component_attribution",
    "algo_config",
    "algo_config_audit",
    "algo_orchestrator_runs",
    "algo_orchestrator_state",
    "algo_runtime_state",
    "algo_weight_history",
    "algo_signal_rejections",
    "algo_position_sizing_audit",
    "algo_stop_loss_audit",
    "algo_untracked_positions",
    "algo_daily_return_histogram",
    "algo_holding_period_histogram",
    "algo_exit_rules_distribution",
    "algo_trade_r_distribution",
    "positions_using_stale_fallback",
    # Pricing
    "price_daily",
    "price_intraday",
    "price_weekly",
    "price_monthly",
    "etf_price_daily",
    "etf_price_weekly",
    "etf_price_monthly",
    "etf_symbols",
    # Price-derived metrics (Session 234 quick wins)
    "price_extremes_52week",  # 52-week high/low computed from price_daily
    "market_cap_computed",  # Market cap computed from price x shares outstanding
    # Market
    "market_health_daily",
    "market_events",
    "market_exposure_daily",
    "market_breadth_daily",
    "ad_line_daily",
    "market_calendar",
    "sector_performance",
    "industry_performance",
    # Stock data
    "stock_scores",
    "stock_symbols",
    "stock_fundamentals",
    "stock_ownership",
    "stock_ratings",
    "company_profile",
    "sector_ranking",
    "industry_ranking",
    # Technical indicators
    "technical_data_daily",
    "technical_data_weekly",
    "technical_data_monthly",
    "technical_indicators_daily",
    "vcp_patterns",
    "equity_curve_daily",
    # Buy/sell signals
    "buy_sell_daily",
    "buy_sell_weekly",
    "buy_sell_monthly",
    "buy_sell_daily_etf",
    "buy_sell_weekly_etf",
    "buy_sell_monthly_etf",
    # Trading signals
    "trend_template_data",
    "signal_quality_scores",
    "signal_themes",
    # Market sentiment
    "aaii_sentiment",
    "market_sentiment",
    "naaim",
    "fear_greed",
    "fear_greed_index",
    "seasonality",
    "seasonality_monthly_stats",
    "sector_rotation_signal",
    "sentiment",
    "sentiment_aggregate",
    "sentiment_social",
    # Economic data
    "economic_data",
    "earnings_history",
    "earnings_calendar",
    "earnings_estimates",
    "earnings_estimate_revisions",
    "earnings_revisions",
    # ADDED 2026-08-19: created by migration 1146, populated once by migration 1147, but
    # never added to this allowlist - loaders/load_earnings_metrics.py (added the same day,
    # this table's first real ongoing loader) failed its very first run with "Unknown table
    # 'earnings_metrics' (not in whitelist)" until this entry existed.
    "earnings_metrics",
    # Fundamental metrics
    "growth_metrics",
    "quality_metrics",
    "value_metrics",
    "stability_metrics",
    "positioning_metrics",
    "momentum_metrics",
    "key_metrics",
    "short_interest_finra",  # Phase 1: FINRA short interest (replaces yfinance)
    "institutional_holdings_13f",  # Phase 2: SEC 13F institutional holdings
    "insider_holdings_sec",  # Phase 2: SEC Form 4/5 insider holdings
    "insider_transaction_velocity",  # Phase 2: Insider buy/sell velocity from SEC Form 4/5
    "current_reports_8k",  # Phase 2: SEC Form 8-K material events (acquisitions, bankruptcies, etc.)
    "dividend_data",  # Phase 2: Dividend ex-dates and payment dates (position management)
    "sec_segment_info",  # Phase 3: SEC XBRL segment disclosure data (ASC 280) - source for diversification metrics
    "sec_segment_metrics",  # Phase 3: Segment diversification metrics (Herfindahl index) from sec_segment_info
    "company_info_sec",  # Phase 3: SEC company master data (replaces yfinance company info)
    "earnings_calendar_sec",  # Phase 3: SEC earnings dates (replaces yfinance earnings_date)
    # Phase 1-4 Consolidation (Session 204+)
    "sec_valuations",  # Phase 1: SEC-derived PE/PB/PS/PEG/FCF (replaces yfinance quoteSummary)
    "sec_cash_flow_metrics",  # Working capital/CapEx/FCF from SEC statement tables (migration 1131, 2026-07-20)
    # Orphaned tables (0 rows, no loader anywhere in the codebase) - still present in the DB
    # schema and referenced by stale data_loader_status rows, so pipeline_health needs to be
    # able to query them (see KNOWN_DEPRECATED_TABLES in algo/monitoring/pipeline_health.py)
    # instead of erroring "not in whitelist" on every orchestrator run.
    "sec_dividends",  # Superseded by dividend_data (Phase 2) - never had a writer
    "sec_material_events",  # Superseded by current_reports_8k (Phase 2) - never had a writer
    "analyst_sentiment_analysis",  # No writer found; deleted with yfinance_snapshot (Session 275)
    # analyst_upgrade_downgrade now HAS a real writer (load_analyst_upgrade_downgrade.py,
    # yfinance-sourced, restored 2026-07-27) - kept in this allowlist (queryable table), just
    # correcting the stale "no writer" comment.
    "analyst_upgrade_downgrade",
    # Added 2026-08-03: real writer load_analyst_earnings_estimates.py (yfinance forward-EPS
    # consensus, feeds value_metrics.forward_pe - see that loader's module docstring).
    "analyst_earnings_estimates",
    # Market snapshots
    "yfinance_snapshot",
    "yfinance_derived_metrics",
    # Financial statements
    "balance_sheet",
    "cash_flow",
    "income_statement",
    "annual_balance_sheet",
    "annual_cash_flow",
    "annual_income_statement",
    "quarterly_balance_sheet",
    "quarterly_cash_flow",
    "quarterly_income_statement",
    "ttm_cash_flow",
    "ttm_income_statement",
    # Other traders
    "insider_transactions",
    # Backtest
    "backtest_results",
    "backtest_runs",
    "backtest_trades",
    # Portfolio
    "trades",
    "portfolio_holdings",
    "portfolio_history",
    "portfolio_performance",
    # Data management
    "data_quality_log",
    "data_patrol_log",
    "data_loader_status",
    "data_provenance_log",
    "circuit_breaker_status",
    # Distribution data (for dashboards)
    "grade_distribution_daily",
    # Russell/S&P constituents
    "russell2000_constituents",
    "sp500_constituents",
}

# Known safe columns (whitelist for dynamic column names)
# Security: M-001 SQL injection prevention - column names validated against whitelist
SAFE_COLUMNS = {
    # Time columns
    "date",
    "created_at",
    "updated_at",
    "last_updated_at",
    "date_added",
    "executed_at",
    "timestamp",
    "signal_date",
    "trade_date",
    "exit_date",
    "earnings_date",
    "quarter",
    "date_recorded",
    "transaction_date",
    "action_date",
    "score_date",
    # algo_portfolio_snapshots' date column - added 2026-08-16 alongside pipeline_health.py's
    # CRITICAL_TABLES entry for that table; check_table_health() rejected it with "not in
    # whitelist" despite being a real column (confirmed via information_schema).
    "snapshot_date",
    # earnings_metrics.report_date (watermark_field) - added 2026-08-19 alongside that
    # table's earnings_metrics SAFE_TABLES entry above, same load_earnings_metrics.py
    # first-run gap.
    "report_date",
    # Common columns
    "symbol",
    "count",
    "max_date",
    "status",
    "active",
    "correlation_id",
    # OHLCV data
    "open",
    "high",
    "low",
    "close",
    "volume",
    "adj_close",
    # Trading data
    "trade_id",
    "position_id",
    "signal_id",
    "order_id",
    "entry_price",
    "exit_price",
    "quantity",
    "value",
    "unrealized_pnl",
    "profit_loss",
    "profit_loss_pct",
    "return_pct",
    "current_price",
    "current_stop_price",
    "target_levels_hit",
    # Application/audit
    "application_name",
    "execution_started",
    "execution_completed",
    "last_updated",
    # Watermark/incremental
    "watermark",
    "high_water_mark",
    "checkpoint",
    # Generic
    "id",
    "result",
}


def validate_identifier(identifier: str, whitelist: set[str], identifier_type: str = "table") -> str:
    """
    Validate a dynamic identifier (table or column name) against whitelist.

    Args:
        identifier: The identifier to validate (e.g., table or column name)
        whitelist: Set of allowed identifiers
        identifier_type: 'table' or 'column' (for error messages)

    Returns:
        The validated identifier if safe

    Raises:
        ValueError: If identifier is not in whitelist or contains suspicious chars
    """
    if not identifier:
        raise ValueError(f"Empty {identifier_type} name")

    # Reject obvious SQL injection attempts
    if any(char in identifier for char in [";", "--", "/*", "*/", "DROP", "DELETE", "INSERT"]):
        raise ValueError(f"Suspicious characters in {identifier_type}: {identifier}")

    # Must be alphanumeric + underscore
    if not re.match(r"^[a-zA-Z_][a-zA-Z0-9_]*$", identifier):
        raise ValueError(f"Invalid {identifier_type} format: {identifier}")

    if identifier not in whitelist:
        raise ValueError(f"Unknown {identifier_type} '{identifier}' (not in whitelist)")

    return identifier


def assert_safe_table(table: str) -> str:
    """Assertion wrapper for table name validation."""
    return validate_identifier(table, SAFE_TABLES, "table")


def assert_safe_column(column: str) -> str:
    """Assertion wrapper for column name validation."""
    return validate_identifier(column, SAFE_COLUMNS, "column")


# For backwards compatibility - direct safe execution
def safe_execute(cur: Any, query_template: str, **kwargs: Any) -> None:
    """
    Execute a query with validated dynamic parts.

    Example:
        safe_execute(cur, "SELECT COUNT(*) FROM {table}",
                     table='price_daily')
    """
    # Replace placeholders with validated identifiers
    safe_kwargs = {}
    for key, value in kwargs.items():
        if isinstance(value, str):
            # Try to validate as table name first, then column
            try:
                safe_kwargs[key] = validate_identifier(value, SAFE_TABLES, "table")
            except ValueError:
                try:
                    safe_kwargs[key] = validate_identifier(value, SAFE_COLUMNS, "column")
                except ValueError as e:
                    raise ValueError(f"Invalid identifier '{value}' for parameter '{key}'") from e
        else:
            safe_kwargs[key] = value

    query = query_template.format(**safe_kwargs)
    cur.execute(query)


def safe_select_count(
    cur: Any,
    table: str,
    date_column: str | None = None,
    where_clause: str | None = None,
) -> tuple[int, str | None]:
    """
    Count rows in table and get max date if date_column specified.

    Args:
        cur: Database cursor
        table: Validated table name
        date_column: Optional date column name to get MAX(date_column)
        where_clause: Optional WHERE clause condition (must be hardcoded/static SQL, NEVER user-controlled)

    Returns:
        (row_count, max_date_as_string)

    SECURITY M-05: where_clause must be static/hardcoded SQL only. Never accept user input here.
    The whitelist approach below is deprecated. For new code: use parameterized queries with %s placeholders.
    Example: cur.execute(f"SELECT COUNT(*) FROM {table_safe} WHERE status = %s", (status,))
    """
    table_safe = assert_safe_table(table)

    # SECURITY FIX M-05: Validate where_clause against SQL injection
    # These are always hardcoded internal strings - never user input (see docstring).
    # Validation catches the rare case of accidental user-input misuse.
    if where_clause:
        where_upper = where_clause.upper()

        # Reject SQL keywords that enable injection or data exfiltration.
        # DML/control keywords use word-boundary matching so column names like
        # "created_at" (contains CREATE) or "updated_at" (UPDATE) are not falsely rejected.
        word_keywords = [
            "DROP",
            "DELETE",
            "INSERT",
            "UPDATE",
            "UNION",
            "TRUNCATE",
            "EXECUTE",
            "ALTER",
            "CAST",
            "WITH",
            "CASE",
            "EXISTS",
            "HAVING",
        ]
        for kw in word_keywords:
            if re.search(r"\b" + kw + r"\b", where_upper):
                raise ValueError(f"SQL keyword detected in where_clause (M-05): {where_clause}")
        # Pattern-based checks (prefixes, multi-word, special syntax)
        dangerous_patterns = [
            ";",
            "/*",
            "*/",
            "pg_",
            "SELECT INTO",
            "$$",
            "CROSS JOIN",
            "INNER JOIN",
            "LEFT JOIN",
            "RIGHT JOIN",
            "FULL JOIN",
            "COPY ",
            "CREATE ",  # trailing space distinguishes from column prefixes
        ]
        if any(p in where_upper for p in dangerous_patterns):
            raise ValueError(f"SQL pattern detected in where_clause (M-05): {where_clause}")
        # SQL comment markers
        if "--" in where_clause:
            raise ValueError(f"SQL comment detected in where_clause (M-05): {where_clause}")

        # Character allowlist: comparison operators, INTERVAL literals (single quotes),
        # IN lists (parentheses, commas), date arithmetic (hyphens), standard identifiers
        if not re.match(r"^[a-zA-Z0-9_\s=<>!'(),.\-\+\%]+$", where_clause):
            raise ValueError(f"where_clause contains disallowed characters (M-05): {where_clause}")

        where_sql = f" WHERE {where_clause}"
    else:
        where_sql = ""

    if date_column:
        col_safe = assert_safe_column(date_column)
        cur.execute(f"SELECT COUNT(*), MAX({col_safe})::TEXT FROM {table_safe}{where_sql}")
        result = cur.fetchone()
        if result is None or result[0] is None:
            raise RuntimeError(f"COUNT query returned unexpected None for {table_safe}")
        count, max_date = result
        return int(count), max_date
    else:
        cur.execute(f"SELECT COUNT(*) FROM {table_safe}{where_sql}")
        result = cur.fetchone()
        if result is None or result[0] is None:
            raise RuntimeError(f"COUNT query returned unexpected None for {table_safe}")
        count = result[0]
        return int(count), None
