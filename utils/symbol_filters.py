"""Centralized symbol filtering logic - all filtering rules in one place.

This module enforces consistent filtering across:
- Data loaders (what data to ingest)
- API endpoints (what to return to clients)
- Dashboard queries (what to display)

Single source of truth prevents:
- Endpoint-specific ETF inclusion/exclusion inconsistencies
- Index symbol filtering copy-pasted in 6 places
- Dashboard filtering that differs from API filtering
"""

from typing import Any


def filter_etfs(cursor: Any) -> str:
    """SQL WHERE clause fragment to exclude ETFs.

    Uses two conditions for robustness:
    1. Explicit etf_symbols table lookup (definitive source)
    2. etf='N' flag (common data marker)

    Both conditions must be TRUE to include the symbol.
    This matches load_active_symbols(exclude_etfs=True) logic.
    """
    return "(ss.symbol NOT IN (SELECT symbol FROM etf_symbols) AND (ss.etf IS NULL OR ss.etf = 'N'))"


def filter_indices(cursor: Any) -> str:
    """SQL WHERE clause fragment to exclude index symbols.

    Indices are typically prefixed with '^' (e.g., '^GSPC' for S&P 500).
    This is a standard convention across market data providers.
    """
    return "sc.symbol NOT LIKE '^%'"


def build_symbol_filter_clause(
    exclude_etfs: bool = True,
    exclude_indices: bool = True,
) -> str:
    """Build combined symbol filter clause for use in SQL queries.

    Args:
        exclude_etfs: If True, exclude symbols in etf_symbols table
        exclude_indices: If True, exclude symbols starting with '^'

    Returns:
        SQL WHERE clause fragment that can be appended to queries
    """
    filters = []

    if exclude_etfs:
        filters.append(filter_etfs(None))

    if exclude_indices:
        filters.append(filter_indices(None))

    if not filters:
        return "1=1"

    return " AND ".join(filters)
