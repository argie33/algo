"""API endpoint URLs for external data sources.

Centralizes endpoint configuration to support:
- Swapping between different API versions
- Environment-specific endpoints (test vs production)
- Rate limit and feature parity considerations
"""

def get_yahoo_finance_url() -> str:
    """Return Yahoo Finance API base URL.

    Used by: algo_data_patrol (cross-validation), intraday pricing
    Pattern: https://query1.finance.yahoo.com
    """
    return "https://query1.finance.yahoo.com"

def get_fred_url() -> str:
    """Return FRED (Federal Reserve Economic Data) API base URL.

    Used by: load_fred_economic_data, load_economic_calendar
    Pattern: https://api.stlouisfed.org/fred
    Requires: FRED_API_KEY environment variable or credential manager
    """
    return "https://api.stlouisfed.org/fred"

def get_aaii_sentiment_url() -> str:
    """Return AAII (American Association of Individual Investors) sentiment URL.

    Used by: load_aaii_sentiment loader
    Pattern: https://www.aaii.com/sentiment
    Note: Web scraping endpoint (no API key required, rate-limited)
    """
    return "https://www.aaii.com/sentiment"
