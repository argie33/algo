#!/usr/bin/env python3
"""
Unified Alpaca Configuration - Single Source of Truth

All Alpaca API interactions use this module to get the correct base URL.
Supports both paper and live trading modes.
"""

import os
from config.credential_manager import get_secret


def get_alpaca_base_url() -> str:
    """Get Alpaca base URL (paper or live based on trading mode).

    Decision logic:
    1. Check ALPACA_BASE_URL env var (for explicit override)
    2. Check trading mode in Secrets Manager
    3. Default to paper trading

    Returns:
        str: 'https://paper-api.alpaca.markets' or 'https://api.alpaca.markets'
    """
    # Allow explicit env var override
    if os.getenv('ALPACA_BASE_URL'):
        return os.getenv('ALPACA_BASE_URL').rstrip('/')

    # Check trading mode from config/secrets
    try:
        trading_mode = os.getenv('ALPACA_TRADING_MODE', 'paper')
        if trading_mode.lower() == 'live':
            return 'https://api.alpaca.markets'
    except Exception:
        pass

    return 'https://paper-api.alpaca.markets'


def get_alpaca_data_url() -> str:
    """Get Alpaca Data API URL.

    Returns:
        str: 'https://data.alpaca.markets'
    """
    return 'https://data.alpaca.markets'
