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
    2. Check APCA_API_BASE_URL env var (set by Terraform)
    3. Check ALPACA_PAPER_TRADING flag
    4. Default to paper trading

    Returns:
        str: 'https://paper-api.alpaca.markets' or 'https://api.alpaca.markets'
    """
    # Allow explicit APCA_API_BASE_URL env var (set by Terraform)
    apca_url = os.getenv('APCA_API_BASE_URL')
    if apca_url:
        return apca_url.rstrip('/')

    # Allow explicit ALPACA_BASE_URL override
    alpaca_url = os.getenv('ALPACA_BASE_URL')
    if alpaca_url:
        return alpaca_url.rstrip('/')

    # Check trading mode from ALPACA_PAPER_TRADING flag
    try:
        paper_flag = os.getenv('ALPACA_PAPER_TRADING', 'true').strip().lower()
        if paper_flag == 'false':
            return 'https://api.alpaca.markets'
    except Exception as e:
        import logging
        logging.debug(f"Could not parse ALPACA_PAPER_TRADING: {e}, using default")

    return 'https://paper-api.alpaca.markets'

def get_alpaca_data_url() -> str:
    """Get Alpaca Data API URL.

    Returns:
        str: 'https://data.alpaca.markets'
    """
    return 'https://data.alpaca.markets'
