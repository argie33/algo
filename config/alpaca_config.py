"""
Alpaca configuration — unified base URL resolution.

Single source of truth for Alpaca API endpoint selection.
Respects ALPACA_PAPER_TRADING flag for environment selection.
"""

import os
import logging

logger = logging.getLogger(__name__)

ALPACA_PAPER_URL = "https://paper-api.alpaca.markets"
ALPACA_LIVE_URL = "https://api.alpaca.markets"


def get_alpaca_base_url() -> str:
    """Get Alpaca API base URL based on trading mode.

    Returns:
        str: Paper or live API endpoint URL

    Raises:
        ValueError: If ALPACA_PAPER_TRADING is explicitly set to an invalid value
    """
    paper_trading_raw = os.getenv("ALPACA_PAPER_TRADING", "true").lower().strip()

    if paper_trading_raw in ("true", "1", "yes"):
        url = ALPACA_PAPER_URL
        logger.debug("Using Alpaca paper trading API")
    elif paper_trading_raw in ("false", "0", "no"):
        url = ALPACA_LIVE_URL
        logger.debug("Using Alpaca LIVE trading API")
    else:
        raise ValueError(
            f"Invalid ALPACA_PAPER_TRADING value: {paper_trading_raw!r} "
            f"(must be 'true'/'false')"
        )

    return url
