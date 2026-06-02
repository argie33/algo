"""
SQL Safety Module - Prevent Injection and Enforce Best Practices

Provides safe wrappers for dynamic SQL queries where table/column names
must be dynamically constructed (cannot use parameterized queries for identifiers).

All dynamic SQL patterns are validated against whitelists before execution.
"""

import re
from typing import List, Tuple, Optional

# Known safe tables (whitelist for dynamic table names)
SAFE_TABLES = {
    'price_daily', 'price_intraday', 'price_weekly', 'price_monthly',
    'market_health_daily', 'market_events', 'market_exposure_daily',
    'algo_trades', 'algo_positions', 'algo_signals', 'algo_portfolio_snapshots',
    'algo_audit_log', 'algo_notifications', 'algo_data_patrol', 'algo_risk_daily',
    'algo_performance_daily', 'algo_signals_evaluated', 'algo_trade_adds',
    'algo_tca', 'algo_information_coefficient', 'algo_model_registry', 'algo_champion_challenger',
    'algo_config', 'algo_config_audit',
    'stock_fundamentals', 'stock_ownership', 'stock_ratings', 'stock_scores', 'stock_symbols',
    'company_profile', 'sector_performance', 'market_calendar', 'sector_ranking', 'industry_ranking', 'industry_performance',
    'data_quality_log', 'data_patrol_log', 'data_loader_status', 'data_provenance_log',
    'technical_data_daily', 'technical_data_weekly', 'technical_data_monthly', 'technical_indicators_daily',
    'buy_sell_daily', 'buy_sell_weekly', 'buy_sell_monthly', 'buy_sell_daily_etf', 'buy_sell_weekly_etf', 'buy_sell_monthly_etf',
    'trend_template_data', 'signal_quality_scores', 'swing_trader_scores',
    'insider_transactions', 'analyst_upgrade_downgrade', 'analyst_upgrades_downgrades', 'analyst_sentiment_analysis',
    'aaii_sentiment', 'economic_data', 'naaim', 'growth_metrics', 'earnings_history', 'earnings_calendar',
    'earnings_estimates', 'earnings_revisions', 'fear_greed', 'fear_greed_index', 'seasonality',
    'quality_metrics', 'value_metrics', 'momentum_metrics', 'stability_metrics',
    'backtest_results', 'backtest_runs', 'backtest_trades',
    'trades', 'portfolio_holdings', 'portfolio_history', 'portfolio_performance',
    'etf_symbols', 'etf_price_daily', 'etf_price_weekly', 'etf_price_monthly',
    'annual_balance_sheet', 'annual_cash_flow', 'annual_income_statement',
    'quarterly_balance_sheet', 'quarterly_cash_flow', 'quarterly_income_statement',
    'ttm_cash_flow', 'ttm_income_statement',
}

# Known safe columns (whitelist for dynamic column names)
SAFE_COLUMNS = {
    'date', 'symbol', 'close', 'open', 'high', 'low', 'volume',
    'count', 'max_date', 'created_at', 'updated_at',
    'status', 'trade_id', 'position_id', 'signal_id',
    'entry_price', 'exit_price', 'quantity', 'value',
    'unrealized_pnl', 'profit_loss', 'profit_loss_pct',
    'signal_date', 'trade_date', 'exit_date', 'earnings_date',
    'target_levels_hit', 'current_price', 'current_stop_price',
    'date_recorded', 'transaction_date', 'action_date', 'score_date', 'quarter',
}

def validate_identifier(identifier: str, whitelist: set, identifier_type: str = 'table') -> str:
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
    if any(char in identifier for char in [';', '--', '/*', '*/', 'DROP', 'DELETE', 'INSERT']):
        raise ValueError(f"Suspicious characters in {identifier_type}: {identifier}")

    # Must be alphanumeric + underscore
    if not re.match(r'^[a-zA-Z_][a-zA-Z0-9_]*$', identifier):
        raise ValueError(f"Invalid {identifier_type} format: {identifier}")

    if identifier not in whitelist:
        raise ValueError(f"Unknown {identifier_type} '{identifier}' (not in whitelist)")

    return identifier

def assert_safe_table(table: str) -> str:
    """Assertion wrapper for table name validation."""
    return validate_identifier(table, SAFE_TABLES, 'table')

def assert_safe_column(column: str) -> str:
    """Assertion wrapper for column name validation."""
    return validate_identifier(column, SAFE_COLUMNS, 'column')

# For backwards compatibility - direct safe execution
def safe_execute(cur, query_template: str, **kwargs) -> None:
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
                safe_kwargs[key] = validate_identifier(value, SAFE_TABLES, 'table')
            except ValueError:
                try:
                    safe_kwargs[key] = validate_identifier(value, SAFE_COLUMNS, 'column')
                except ValueError:
                    raise ValueError(f"Invalid identifier '{value}' for parameter '{key}'")
        else:
            safe_kwargs[key] = value

    query = query_template.format(**safe_kwargs)
    cur.execute(query)

def safe_select_count(cur, table: str, date_column: Optional[str] = None, where_clause: Optional[str] = None) -> Tuple[int, Optional[str]]:
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
    # These are always hardcoded internal strings — never user input (see docstring).
    # Validation catches the rare case of accidental user-input misuse.
    if where_clause:
        where_upper = where_clause.upper()

        # Reject SQL keywords that enable injection or data exfiltration.
        # DML/control keywords use word-boundary matching so column names like
        # "created_at" (contains CREATE) or "updated_at" (UPDATE) are not falsely rejected.
        word_keywords = [
            'DROP', 'DELETE', 'INSERT', 'UPDATE', 'UNION', 'TRUNCATE',
            'EXECUTE', 'ALTER', 'CAST', 'WITH', 'CASE', 'EXISTS', 'HAVING',
        ]
        for kw in word_keywords:
            if re.search(r'\b' + kw + r'\b', where_upper):
                raise ValueError(f"SQL keyword detected in where_clause (M-05): {where_clause}")
        # Pattern-based checks (prefixes, multi-word, special syntax)
        dangerous_patterns = [
            ';', '/*', '*/', 'pg_', 'SELECT INTO', '$$',
            'CROSS JOIN', 'INNER JOIN', 'LEFT JOIN', 'RIGHT JOIN', 'FULL JOIN',
            'COPY ', 'CREATE ',  # trailing space distinguishes from column prefixes
        ]
        if any(p in where_upper for p in dangerous_patterns):
            raise ValueError(f"SQL pattern detected in where_clause (M-05): {where_clause}")
        # SQL comment markers
        if '--' in where_clause:
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
        count, max_date = cur.fetchone()
        return int(count or 0), max_date
    else:
        cur.execute(f"SELECT COUNT(*) FROM {table_safe}{where_sql}")
        count = cur.fetchone()[0]
        return int(count or 0), None
