"""API Timeout Configuration - all timeouts in seconds, configurable via environment variables."""

import os

# Timeout constants (in seconds)
API_TIMEOUT = int(os.getenv('API_TIMEOUT', '5'))
MARKET_DATA_TIMEOUT = int(os.getenv('MARKET_DATA_TIMEOUT', '10'))
ALPACA_TIMEOUT = int(os.getenv('ALPACA_TIMEOUT', '5'))
WEBHOOK_TIMEOUT = int(os.getenv('WEBHOOK_TIMEOUT', '5'))
SUBPROCESS_TIMEOUT = int(os.getenv('SUBPROCESS_TIMEOUT', '5'))

# Deprecated: use constants directly
def get_api_timeout() -> int:
    return API_TIMEOUT

def get_market_data_timeout() -> int:
    return MARKET_DATA_TIMEOUT

def get_alpaca_timeout() -> int:
    return ALPACA_TIMEOUT

def get_webhook_timeout() -> int:
    return WEBHOOK_TIMEOUT

def get_subprocess_timeout() -> int:
    return SUBPROCESS_TIMEOUT
