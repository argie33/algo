"""
API Timeout Configuration

All HTTP request timeouts centralized here for easy tuning per environment.
Uses environment variables with sensible defaults.
"""

import os

# Default timeouts (in seconds)
DEFAULT_API_TIMEOUT = int(os.getenv('API_TIMEOUT', '5'))
DEFAULT_MARKET_DATA_TIMEOUT = int(os.getenv('MARKET_DATA_TIMEOUT', '10'))
DEFAULT_ALPACA_TIMEOUT = int(os.getenv('ALPACA_TIMEOUT', '5'))
DEFAULT_WEBHOOK_TIMEOUT = int(os.getenv('WEBHOOK_TIMEOUT', '5'))
DEFAULT_SUBPROCESS_TIMEOUT = int(os.getenv('SUBPROCESS_TIMEOUT', '5'))

def get_api_timeout() -> int:
    """Get API request timeout."""
    return DEFAULT_API_TIMEOUT

def get_market_data_timeout() -> int:
    """Get market data request timeout (more lenient for external APIs)."""
    return DEFAULT_MARKET_DATA_TIMEOUT

def get_alpaca_timeout() -> int:
    """Get Alpaca API request timeout."""
    return DEFAULT_ALPACA_TIMEOUT

def get_webhook_timeout() -> int:
    """Get webhook POST timeout."""
    return DEFAULT_WEBHOOK_TIMEOUT

def get_subprocess_timeout() -> int:
    """Get subprocess execution timeout."""
    return DEFAULT_SUBPROCESS_TIMEOUT
