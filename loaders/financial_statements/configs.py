"""Statement/period combo enumeration and the get_statement_config() dispatcher.

Split out of load_financial_statements.py (see that module's top docstring).
"""

from typing import Any

from utils.loaders.enum_validator import validate_period, validate_statement_type

from .configs_balance import get_balance_sheet_config
from .configs_cashflow import get_cash_flow_config
from .configs_income import get_income_statement_config


def get_all_statement_configs() -> list[tuple[str, str]]:
    """Enumerate all statement/period combinations for 'all' mode.

    NOTE: the ("income", "ttm") and ("balance", "ttm") combos were removed
    2026-07-13. They never worked: SecEdgarStatementLoader.__init__ only
    accepts period 'annual'/'quarterly' and rejected period='ttm' at init on
    every run, so both combos crashed immediately and were merely logged as
    failed. Reinstating TTM requires actual TTM aggregation support in the
    SEC client/loader, not just a config entry here.

    Returns:
        List of (statement_type, period) tuples in execution order
    """
    return [
        ("income", "annual"),
        ("income", "quarterly"),
        ("balance", "annual"),
        ("balance", "quarterly"),
        ("cashflow", "annual"),
        ("cashflow", "quarterly"),
    ]


def get_statement_config(statement_type: str, period: str) -> dict[str, Any]:
    """Return configuration for a specific statement type and period.

    Args:
        statement_type: 'income', 'balance', 'cashflow', or 'all' (loads all combos)
        period: 'annual', 'quarterly', 'ttm', or ignored if statement_type='all'

    Returns:
        Dict with table_name, primary_key, schema_cols, field_mapping
    """
    # ISSUE #12 FIX: Enum validation
    if statement_type != "all":
        validate_statement_type(statement_type, context="get_statement_config")
        validate_period(period, context="get_statement_config")

    if statement_type == "income":
        return get_income_statement_config(period)
    elif statement_type == "balance":
        return get_balance_sheet_config(period)
    elif statement_type == "cashflow":
        return get_cash_flow_config(period)
    elif statement_type == "all":
        raise ValueError("Use load_all_statements() for statement_type='all', not get_statement_config()")
    else:
        raise ValueError(f"Unknown statement type: {statement_type}")
