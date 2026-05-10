"""
SQL Safety Module - Prevent Injection and Enforce Best Practices

Provides safe wrappers for dynamic SQL queries where table/column names
must be dynamically constructed (cannot use parameterized queries for identifiers).

All dynamic SQL patterns are validated against whitelists before execution.
"""

import psycopg2
from psycopg2 import sql
import re
from typing import List, Tuple, Optional

# Known safe tables (whitelist for dynamic table names)
SAFE_TABLES = {
    'price_daily', 'price_intraday', 'price_weekly',
    'market_health_daily', 'market_events',
    'algo_trades', 'algo_positions', 'algo_signals', 'algo_portfolio_snapshots',
    'algo_audit_log', 'algo_notifications', 'algo_data_patrol',
    'stock_fundamentals', 'stock_ownership', 'stock_ratings',
    'sector_performance', 'market_calendar',
    'data_quality_log', 'data_patrol_log',
    'technical_data_daily', 'buy_sell_daily', 'trend_template_data',
    'signal_quality_scores', 'sector_ranking', 'industry_ranking',
    'insider_transactions', 'analyst_upgrade_downgrade', 'stock_scores',
    'aaii_sentiment', 'growth_metrics', 'earnings_history',
}

# Known safe columns (whitelist for dynamic column names)
SAFE_COLUMNS = {
    'date', 'symbol', 'close', 'open', 'high', 'low', 'volume',
    'count', 'max_date', 'created_at', 'updated_at',
    'status', 'trade_id', 'position_id', 'signal_id',
    'entry_price', 'exit_price', 'quantity', 'value',
    'unrealized_pnl', 'profit_loss', 'profit_loss_pct',
    'signal_date', 'trade_date', 'exit_date',
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

    # Check whitelist
    if identifier not in whitelist:
        raise ValueError(f"Unknown {identifier_type} '{identifier}' (not in whitelist)")

    return identifier


def safe_select_count(
    cur,
    table: str,
    where_clause: Optional[str] = None,
    date_column: Optional[str] = None
) -> Tuple[int, Optional[str]]:
    """
    Safely execute a COUNT query on a table with optional WHERE and MAX(date) calculation.

    Args:
        cur: psycopg2 cursor
        table: Table name (validated against whitelist)
        where_clause: Optional WHERE clause (parameterized separately if needed)
        date_column: Optional column for MAX(date) calculation

    Returns:
        Tuple of (count, max_date_str) where max_date_str is ISO format or None
    """
    # Validate table name
    table = validate_identifier(table, SAFE_TABLES, 'table')

    # Validate date column if provided
    if date_column:
        date_column = validate_identifier(date_column, SAFE_COLUMNS, 'column')
        if where_clause:
            query = f"SELECT COUNT(*), MAX({date_column}::date) FROM {table} WHERE {where_clause}"
        else:
            query = f"SELECT COUNT(*), MAX({date_column}::date) FROM {table}"
    else:
        if where_clause:
            query = f"SELECT COUNT(*) FROM {table} WHERE {where_clause}"
        else:
            query = f"SELECT COUNT(*) FROM {table}"

    cur.execute(query)
    row = cur.fetchone()

    if not row:
        return (0, None)

    count = int(row[0] or 0)
    max_date = str(row[1]) if date_column and row[1] else None

    return (count, max_date)


def safe_select_with_date(
    cur,
    table: str,
    columns: List[str],
    date_column: Optional[str] = None,
    where_clause: Optional[str] = None
) -> List[Tuple]:
    """
    Safely execute a SELECT query with dynamic table/column names.

    Args:
        cur: psycopg2 cursor
        table: Table name (validated)
        columns: List of column names (each validated)
        date_column: Optional date column for MAX() calculation
        where_clause: Optional WHERE clause

    Returns:
        List of result tuples
    """
    # Validate identifiers
    table = validate_identifier(table, SAFE_TABLES, 'table')

    validated_cols = []
    for col in columns:
        validated_cols.append(validate_identifier(col, SAFE_COLUMNS, 'column'))

    if date_column:
        date_column = validate_identifier(date_column, SAFE_COLUMNS, 'column')

    # Build query
    col_str = ', '.join(validated_cols)
    if date_column:
        query = f"SELECT {col_str}, MAX({date_column}::date) FROM {table}"
    else:
        query = f"SELECT {col_str} FROM {table}"

    if where_clause:
        query += f" WHERE {where_clause}"

    cur.execute(query)
    return cur.fetchall()


def assert_safe_table(table: str) -> str:
    """Assertion wrapper for table name validation."""
    return validate_identifier(table, SAFE_TABLES, 'table')


def assert_safe_column(column: str) -> str:
    """Assertion wrapper for column name validation."""
    return validate_identifier(column, SAFE_COLUMNS, 'column')


# SQL identifier quoter for Identifier patterns (psycopg2)
def quote_identifier(name: str) -> sql.Identifier:
    """Return a psycopg2 SQL Identifier for safe quoting."""
    # Still validate
    validate_identifier(name, SAFE_TABLES | SAFE_COLUMNS, 'identifier')
    return sql.Identifier(name)


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
