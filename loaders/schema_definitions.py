#!/usr/bin/env python3
"""
Schema definitions for loader tables.

These definitions are used for pre-flight validation before loading data.
If a column type changes (e.g., price becomes TEXT instead of NUMERIC),
the validation will catch it and fail before any data is corrupted.
"""

# Price tables schema - validates that columns exist with correct types
PRICE_SCHEMA = {
    "symbol": "varchar",
    "date": "date",
    "open": "numeric",
    "high": "numeric",
    "low": "numeric",
    "close": "numeric",
    "volume": "integer",
    "adj_close": "numeric",
}

# ETF price tables schema
ETF_PRICE_SCHEMA = {
    "symbol": "varchar",
    "date": "date",
    "open": "numeric",
    "high": "numeric",
    "low": "numeric",
    "close": "numeric",
    "volume": "integer",
}

# Map table names to their schemas for easy lookup
TABLE_SCHEMAS = {
    "price_daily": PRICE_SCHEMA,
    "price_weekly": PRICE_SCHEMA,
    "price_monthly": PRICE_SCHEMA,
    "etf_price_daily": ETF_PRICE_SCHEMA,
    "etf_price_weekly": ETF_PRICE_SCHEMA,
    "etf_price_monthly": ETF_PRICE_SCHEMA,
}
