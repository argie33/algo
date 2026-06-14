#!/usr/bin/env python3
"""
API Endpoint Configuration

Provides URL construction for external data APIs used by the system.
"""

import os


def get_alpaca_data_url() -> str:
    """Get the Alpaca Data API base URL.

    Returns the appropriate URL based on market data subscription tier.
    """
    # Standard free tier uses the main API domain
    return "https://data.alpaca.markets"
