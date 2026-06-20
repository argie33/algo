#!/usr/bin/env python3
"""
Unified Alpaca Configuration - Single Source of Truth

All Alpaca API interactions use this module to get the correct base URL.
Supports both paper and live trading modes.
"""

import os


def get_alpaca_base_url() -> str:
    """Get Alpaca base URL (paper or live based on trading mode).

    Decision logic:
    1. Check ALPACA_BASE_URL env var (for explicit override)
    2. Check APCA_API_BASE_URL env var (set by Terraform)
    3. Check ALPACA_PAPER_TRADING flag (required — no default to paper trading)

    Returns:
        str: 'https://paper-api.alpaca.markets' or 'https://api.alpaca.markets'

    Raises:
        ValueError: If ALPACA_PAPER_TRADING is not explicitly set or is invalid
    """
    # Allow explicit APCA_API_BASE_URL env var (set by Terraform)
    apca_url = os.getenv("APCA_API_BASE_URL")
    if apca_url:
        return apca_url.rstrip("/")

    # Allow explicit ALPACA_BASE_URL override
    alpaca_url = os.getenv("ALPACA_BASE_URL")
    if alpaca_url:
        return alpaca_url.rstrip("/")

    # Check trading mode from ALPACA_PAPER_TRADING flag — REQUIRED, no default
    paper_flag = os.getenv("ALPACA_PAPER_TRADING")
    if paper_flag is None:
        raise ValueError(
            "ALPACA_PAPER_TRADING environment variable is REQUIRED. "
            "Set to 'true' for paper trading or 'false' for live trading."
        )

    paper_flag = paper_flag.strip().lower()
    if paper_flag not in ("true", "false"):
        raise ValueError(
            f"ALPACA_PAPER_TRADING must be 'true' or 'false', got '{paper_flag}'"
        )
    if paper_flag == "false":
        return "https://api.alpaca.markets"

    return "https://paper-api.alpaca.markets"


def get_alpaca_data_url() -> str:
    """Get Alpaca Data API URL.

    Returns:
        str: 'https://data.alpaca.markets'
    """
    return "https://data.alpaca.markets"
