"""
SQL Safety utilities - Prevent injection attacks through table/column names.

Use parameterized queries for VALUES, but table and column names cannot be parameterized.
This module provides safe building blocks with whitelisting.
"""

import logging
import re

logger = logging.getLogger(__name__)

# Whitelisted tables - these are safe to use in f-strings
ALLOWED_TABLES = {
    # Price data
    'price_daily',
    'price_intraday',
    'price_weekly',
    'price_monthly',

    # Signals
    'buy_sell_daily',
    'buy_sell_signal',
    'sector_rotation_signal',

    # Scores
    'stock_scores',
    'swing_trader_scores',
    'technical_analysis_scores',

    # Positions & Trades
    'algo_positions',
    'algo_trades',
    'algo_orders',

    # Market data
    'market_health_daily',
    'sector_performance',
    'etf_data',
    'etf_signals',

    # Monitoring & Health
    'data_patrol_log',
    'loader_health',
    'data_freshness',
    'api_audit_log',
    'algo_audit_log',
    'filter_rejection_log',
    'error_log',

    # Configuration
    'stock_symbols',
    'sector_rotation_config',
    'watchlist',
    'portfolio_benchmark',

    # External data
    'earnings_data',
    'earnings_calendar',
    'economic_indicators',
    'fred_indicators',
    'vix_data',
    'breadth_data',

    # System
    'system_config',
    'user_settings',
    'api_keys',
    'credentials',
}

# Whitelisted columns
ALLOWED_COLUMNS = {
    # Common columns
    'id', 'symbol', 'date', 'created_at', 'updated_at',
    'status', 'severity', 'message', 'value', 'name',

    # Price columns
    'open', 'high', 'low', 'close', 'volume',
    'adjusted_close', 'dividend_amount', 'split_coefficient',

    # Score columns
    'composite_score', 'momentum_score', 'growth_score', 'stability_score',
    'value_score', 'quality_score', 'positioning_score', 'data_completeness',
    'confidence', 'percentile', 'rank', 'rs_percentile',

    # Position/Trade columns
    'position_id', 'trade_id', 'quantity', 'entry_price', 'exit_price',
    'current_price', 'stop_loss', 'target_1', 'target_2', 'target_3',
    'unrealized_pnl', 'realized_pnl', 'win_rate', 'entry_date', 'exit_date',
    'holding_days', 'r_multiple',

    # Signal columns
    'signal_strength', 'buy_price', 'sell_price', 'buy_signal', 'sell_signal',
    'tier', 'pass_reason', 'reject_reason',

    # Market columns
    'market_regime', 'trend', 'volatility', 'breadth', 'advances', 'declines',
    'advance_decline_line', 'mcclellan_oscillator', 'market_breadth',
    'sector', 'industry',

    # Monitoring columns
    'check', 'target', 'severity', 'details', 'count', 'threshold',
    'expected', 'actual', 'freshness_hours', 'rows_loaded', 'rows_expected',
    'error_count', 'warning_count',
}

# Maximum length for identifiers (table/column names)
MAX_IDENTIFIER_LENGTH = 63


def validate_table_name(table: str) -> str:
    """
    Validate and return table name, or raise ValueError if invalid.

    Args:
        table: Table name to validate

    Returns:
        table: Validated table name (lowercased)

    Raises:
        ValueError: If table is not whitelisted
    """
    if not table or not isinstance(table, str):
        raise ValueError(f"Invalid table name: {table}")

    table_lower = table.lower()

    # Check whitelist
    if table_lower not in ALLOWED_TABLES:
        raise ValueError(
            f"Table '{table}' not whitelisted. "
            f"Allowed: {', '.join(sorted(ALLOWED_TABLES))}"
        )

    # Check length
    if len(table_lower) > MAX_IDENTIFIER_LENGTH:
        raise ValueError(f"Table name too long: {table}")

    # Check format (alphanumeric + underscore only)
    if not re.match(r'^[a-z0-9_]+$', table_lower):
        raise ValueError(f"Invalid table name format: {table}")

    return table_lower


def validate_column_name(column: str) -> str:
    """
    Validate and return column name, or raise ValueError if invalid.

    Args:
        column: Column name to validate

    Returns:
        column: Validated column name (lowercased)

    Raises:
        ValueError: If column is not whitelisted
    """
    if not column or not isinstance(column, str):
        raise ValueError(f"Invalid column name: {column}")

    column_lower = column.lower()

    # Check whitelist
    if column_lower not in ALLOWED_COLUMNS:
        raise ValueError(
            f"Column '{column}' not whitelisted. "
            f"Allowed: {', '.join(sorted(ALLOWED_COLUMNS))}"
        )

    # Check length
    if len(column_lower) > MAX_IDENTIFIER_LENGTH:
        raise ValueError(f"Column name too long: {column}")

    # Check format
    if not re.match(r'^[a-z0-9_]+$', column_lower):
        raise ValueError(f"Invalid column name format: {column}")

    return column_lower


def safe_identifier(name: str, allow_type: str = 'column') -> str:
    """
    Validate identifier (table or column).

    Args:
        name: Table or column name
        allow_type: 'table', 'column', or 'any'

    Returns:
        Validated identifier (lowercased)

    Raises:
        ValueError: If validation fails
    """
    if allow_type == 'table':
        return validate_table_name(name)
    elif allow_type == 'column':
        return validate_column_name(name)
    elif allow_type == 'any':
        try:
            return validate_table_name(name)
        except ValueError:
            return validate_column_name(name)
    else:
        raise ValueError(f"Unknown allow_type: {allow_type}")


def build_safe_query(template: str, **kwargs) -> str:
    """
    Build SQL query with safe table/column name substitution.

    Args:
        template: SQL template with {table_name}, {column_name} placeholders
        **kwargs: Table and column names to substitute

    Returns:
        Safe SQL query with validated identifiers

    Raises:
        ValueError: If any identifier fails validation

    Example:
        safe_query = build_safe_query(
            "SELECT {cols} FROM {tbl} WHERE date = DATE(%s)",
            cols='close, volume',
            tbl='price_daily'
        )
    """
    validated = {}

    for key, value in kwargs.items():
        if key.startswith('tbl') or key == 'table':
            validated[key] = validate_table_name(value)
        elif key.startswith('col') or key == 'column':
            # Handle comma-separated columns
            if ',' in value:
                cols = [validate_column_name(c.strip()) for c in value.split(',')]
                validated[key] = ', '.join(cols)
            else:
                validated[key] = validate_column_name(value)
        else:
            # Unknown key, pass through (might be other template vars)
            validated[key] = value

    try:
        return template.format(**validated)
    except KeyError as e:
        raise ValueError(f"Missing template variable: {e}")


# Common SQL patterns with safety built-in
def select_from_table(table: str, columns: str = '*', where: str = '', params: tuple = ()) -> tuple[str, tuple]:
    """
    Build safe SELECT query.

    Args:
        table: Table name (will be validated)
        columns: Column list (comma-separated, will be validated)
        where: WHERE clause (use %s for parameterized values)
        params: Parameters for WHERE clause

    Returns:
        (query, params): SQL query and parameters

    Example:
        query, params = select_from_table('price_daily', 'close, volume', 'symbol = %s AND date > %s', ('AAPL', '2026-01-01'))
    """
    safe_table = validate_table_name(table)

    if columns and columns != '*':
        cols = [validate_column_name(c.strip()) for c in columns.split(',')]
        safe_columns = ', '.join(cols)
    else:
        safe_columns = '*'

    query = f"SELECT {safe_columns} FROM {safe_table}"

    if where:
        query += f" WHERE {where}"

    return query, params


def count_from_table(table: str, where: str = '', params: tuple = ()) -> tuple[str, tuple]:
    """
    Build safe COUNT query.

    Args:
        table: Table name
        where: WHERE clause
        params: Parameters

    Returns:
        (query, params)
    """
    safe_table = validate_table_name(table)
    query = f"SELECT COUNT(*) FROM {safe_table}"

    if where:
        query += f" WHERE {where}"

    return query, params


def max_from_table(table: str, column: str, where: str = '', params: tuple = ()) -> tuple[str, tuple]:
    """
    Build safe MAX query.

    Args:
        table: Table name
        column: Column to get MAX of
        where: WHERE clause
        params: Parameters

    Returns:
        (query, params)
    """
    safe_table = validate_table_name(table)
    safe_column = validate_column_name(column)
    query = f"SELECT MAX({safe_column}) FROM {safe_table}"

    if where:
        query += f" WHERE {where}"

    return query, params


# Audit logging for security
def log_sql_attempt(query: str, allowed: bool, reason: str = ''):
    """Log SQL safety check attempt for audit trail."""
    if not allowed:
        logger.warning(f"Blocked SQL with unsafe identifiers: {query}")
    if reason:
        logger.debug(f"SQL safety: {reason}")
