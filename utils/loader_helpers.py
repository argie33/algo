#!/usr/bin/env python3
"""
Shared loader utilities - consolidates duplicated functions across loaders.

Functions that were defined identically in 19+ loader files, now centralized here.
"""

from config.env_loader import load_env
import os
from utils.db_connection import get_db_connection
from typing import List
from pathlib import Path

# Load .env for local development


def get_active_symbols() -> List[str]:
    """Get list of active stock symbols from database.

    Used by: load_balance_sheet.py, load_buysell_aggregate.py, load_buysell_etf_aggregate.py,
             load_cash_flow.py, load_etf_price_aggregate.py, load_income_statement.py,
             load_key_metrics.py, load_market_data_batch.py, load_price_aggregate.py,
             load_quality_metrics.py, load_technical_indicators.py, and 8 others

    Originally defined identically in 19 different files. Consolidated 2026-05-18.
    """
    conn = get_db_connection()
    try:
        cur = conn.cursor()
        cur.execute("SELECT symbol FROM stock_symbols ORDER BY symbol")
        symbols = [row[0] for row in cur.fetchall()]
        return symbols
    finally:
        cur.close()
        conn.close()


def _resolve_timeframe(cli_arg: str = None) -> str:
    """Resolve timeframe from CLI arg or environment variable for aggregate loaders.

    Used by: load_buysell_aggregate.py, load_buysell_etf_aggregate.py,
             load_etf_price_aggregate.py, load_price_aggregate.py

    Originally defined identically in 4 different files. Consolidated 2026-05-18.

    Priority:
    1. CLI argument (if provided)
    2. LOADER_TYPE environment variable (if contains "monthly" -> "monthly", else "weekly")
    """
    if cli_arg:
        return cli_arg
    loader_type = os.getenv("LOADER_TYPE", "")
    return "monthly" if "monthly" in loader_type else "weekly"


def _resolve_period(cli_arg: str = None) -> str:
    """Resolve period from CLI arg or environment variable.

    Used by: load_balance_sheet.py, load_cash_flow.py, load_income_statement.py

    Originally defined identically in 3 different files. Consolidated 2026-05-18.

    Priority:
    1. CLI argument (if provided)
    2. LOADER_PERIOD environment variable (default "quarterly")
    """
    if cli_arg:
        return cli_arg
    return os.getenv("LOADER_PERIOD", "quarterly")
