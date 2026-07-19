#!/usr/bin/env python3
"""Central symbol universe definitions for consistent ETF/non-trading-stock filtering.

GOVERNANCE RULE: Financial data loaders and trading signals are for STOCKS ONLY.
All trading-related endpoints must filter out:
- ETFs (sector = 'ETF', captured in etf_symbols table)
- Closed/delisted symbols
- Penny stocks (where applicable)

This module provides standard SQL WHERE clauses to enforce symbol universe rules
consistently across all routes and endpoints. Single source of truth prevents
symbol filtering inconsistencies between loaders and APIs.

Reference: GOVERNANCE.md "Trading Universe" section.
"""

from __future__ import annotations


def stock_only_where_clause(col_prefix: str = "s") -> str:
    """SQL WHERE clause to include STOCKS ONLY (exclude ETFs).

    CRITICAL: Two-condition AND for robustness:
    1. Explicit etf_symbols table (definitive source)
    2. ETF flag in stock_scores table (redundant safety check)

    Use this pattern in ALL queries fetching stock_scores or buy_sell_daily
    that will be used for trading decisions or recommendations.

    Args:
        col_prefix: Column alias for the table being filtered (default: "s").
                   Examples: "s" for stock_scores, "ss" for stock_scores s, "bsd" for buy_sell_daily.

    Returns:
        WHERE clause fragment: "AND ({col_prefix}.symbol NOT IN (SELECT symbol FROM etf_symbols) AND ({col_prefix}.etf IS NULL OR {col_prefix}.etf = 'N'))"
        This matches the etf_symbols table + etf column flag for defense in depth.
    """
    return f"AND ({col_prefix}.symbol NOT IN (SELECT symbol FROM etf_symbols) AND ({col_prefix}.etf IS NULL OR {col_prefix}.etf = 'N'))"


def buy_sell_only_where_clause(col_prefix: str = "bsd") -> str:
    """SQL WHERE clause for buy_sell_daily queries that should exclude ETFs.

    buy_sell_daily does NOT have an etf column, so we only check etf_symbols table.
    This is used for filtering signals to stock trading only.

    Args:
        col_prefix: Column alias for buy_sell_daily (default: "bsd").

    Returns:
        WHERE clause fragment: "AND {col_prefix}.symbol NOT IN (SELECT symbol FROM etf_symbols)"
    """
    return f"AND {col_prefix}.symbol NOT IN (SELECT symbol FROM etf_symbols)"


__all__ = ["stock_only_where_clause", "buy_sell_only_where_clause"]
