#!/usr/bin/env python3
"""
Unified API Endpoint Configuration - Single Source of Truth

All API interactions (trading, data, external services) use this module
to get the correct endpoint URL. Supports environment variable overrides.

Decision logic for each endpoint:
1. Check environment variable override (e.g., ALPACA_BASE_URL)
2. Check database config (algo_endpoints table) if available
3. Use service-specific default logic (e.g., paper vs. live for Alpaca)
4. Fall back to built-in constant

Architecture (Issue #3, C3-4):
- Three patterns eliminated:
  * Hardcoded URLs in application code (algo_realtime_prices.py, algo_data_patrol.py)
  * Scattered env var checks with defaults (dashboard.py, load_aaii_sentiment.py)
  * Duplicate URL definitions (config/alpaca_config.py + algo_trade_executor.py)
- Single, overrideable source of truth for all API endpoints
- No more "which URL am I using?" debugging
"""

import os
import logging
from typing import Optional, Dict, Any

logger = logging.getLogger(__name__)


class APIEndpointConfig:
    """Unified API endpoint configuration manager."""

    # Built-in endpoint defaults (service-specific logic below)
    ENDPOINTS = {
        # Alpaca Trading API (paper vs. live)
        'alpaca_trading': None,  # Computed by get_alpaca_trading_url()

        # Alpaca Data API (always points to data.alpaca.markets)
        'alpaca_data': 'https://data.alpaca.markets',

        # External data sources
        'iex_cloud': 'https://cloud.iexapis.com/stable',
        'yahoo_finance': 'https://query1.finance.yahoo.com/v8/finance',
        'aaii_sentiment': 'https://www.aaii.com/files/surveys/sentiment.xls',
        'fred': 'https://api.stlouisfed.org/fred',

        # Dashboard / Frontend
        'dashboard_api': 'http://localhost:3001',  # For local development
    }

    @staticmethod
    def get_alpaca_trading_url() -> str:
        """Get Alpaca trading API URL (paper or live).

        Decision logic (same as config/alpaca_config.py for compatibility):
        1. Check ALPACA_BASE_URL env var (explicit override)
        2. Check APCA_API_BASE_URL env var (set by Terraform)
        3. Check ALPACA_PAPER_TRADING flag
        4. Default to paper trading

        Returns:
            str: 'https://paper-api.alpaca.markets' or 'https://api.alpaca.markets'
        """
        # Allow explicit ALPACA_BASE_URL override
        if os.getenv('ALPACA_BASE_URL'):
            url = os.getenv('ALPACA_BASE_URL').rstrip('/')
            logger.debug(f"[APIEndpoints] Alpaca trading URL from ALPACA_BASE_URL: {url}")
            return url

        # Allow APCA_API_BASE_URL (set by Terraform)
        if os.getenv('APCA_API_BASE_URL'):
            url = os.getenv('APCA_API_BASE_URL').rstrip('/')
            logger.debug(f"[APIEndpoints] Alpaca trading URL from APCA_API_BASE_URL: {url}")
            return url

        # Check trading mode flag
        try:
            paper_flag = os.getenv('ALPACA_PAPER_TRADING', 'true').strip().lower()
            if paper_flag == 'false':
                url = 'https://api.alpaca.markets'
                logger.debug(f"[APIEndpoints] Alpaca trading URL: live ({url})")
                return url
        except Exception:
            pass

        url = 'https://paper-api.alpaca.markets'
        logger.debug(f"[APIEndpoints] Alpaca trading URL: paper ({url})")
        return url

    @staticmethod
    def get_alpaca_data_url() -> str:
        """Get Alpaca Data API URL.

        Can be overridden via ALPACA_DATA_URL env var.

        Returns:
            str: 'https://data.alpaca.markets'
        """
        if os.getenv('ALPACA_DATA_URL'):
            url = os.getenv('ALPACA_DATA_URL').rstrip('/')
            logger.debug(f"[APIEndpoints] Alpaca data URL from env: {url}")
            return url

        url = APIEndpointConfig.ENDPOINTS['alpaca_data']
        logger.debug(f"[APIEndpoints] Alpaca data URL: {url}")
        return url

    @staticmethod
    def get_iex_cloud_url() -> str:
        """Get IEX Cloud API URL.

        Can be overridden via IEX_CLOUD_URL env var.

        Returns:
            str: Base URL for IEX Cloud API
        """
        if os.getenv('IEX_CLOUD_URL'):
            url = os.getenv('IEX_CLOUD_URL').rstrip('/')
            logger.debug(f"[APIEndpoints] IEX Cloud URL from env: {url}")
            return url

        url = APIEndpointConfig.ENDPOINTS['iex_cloud']
        logger.debug(f"[APIEndpoints] IEX Cloud URL: {url}")
        return url

    @staticmethod
    def get_yahoo_finance_url() -> str:
        """Get Yahoo Finance API URL.

        Can be overridden via YAHOO_FINANCE_URL env var.

        Returns:
            str: Base URL for Yahoo Finance API
        """
        if os.getenv('YAHOO_FINANCE_URL'):
            url = os.getenv('YAHOO_FINANCE_URL').rstrip('/')
            logger.debug(f"[APIEndpoints] Yahoo Finance URL from env: {url}")
            return url

        url = APIEndpointConfig.ENDPOINTS['yahoo_finance']
        logger.debug(f"[APIEndpoints] Yahoo Finance URL: {url}")
        return url

    @staticmethod
    def get_aaii_sentiment_url() -> str:
        """Get AAII sentiment survey URL.

        Can be overridden via AAII_SENTIMENT_URL env var.

        Returns:
            str: URL for AAII sentiment data
        """
        if os.getenv('AAII_SENTIMENT_URL'):
            url = os.getenv('AAII_SENTIMENT_URL').rstrip('/')
            logger.debug(f"[APIEndpoints] AAII sentiment URL from env: {url}")
            return url

        url = APIEndpointConfig.ENDPOINTS['aaii_sentiment']
        logger.debug(f"[APIEndpoints] AAII sentiment URL: {url}")
        return url

    @staticmethod
    def get_fred_url() -> str:
        """Get FRED (Federal Reserve Economic Data) API URL.

        Can be overridden via FRED_API_URL env var.

        Returns:
            str: Base URL for FRED API
        """
        if os.getenv('FRED_API_URL'):
            url = os.getenv('FRED_API_URL').rstrip('/')
            logger.debug(f"[APIEndpoints] FRED URL from env: {url}")
            return url

        url = APIEndpointConfig.ENDPOINTS['fred']
        logger.debug(f"[APIEndpoints] FRED URL: {url}")
        return url

    @staticmethod
    def get_dashboard_api_url() -> str:
        """Get Dashboard API endpoint URL.

        Can be overridden via DASHBOARD_API_URL env var.
        Defaults to localhost for development.

        Returns:
            str: Dashboard API base URL
        """
        if os.getenv('DASHBOARD_API_URL'):
            url = os.getenv('DASHBOARD_API_URL').rstrip('/')
            logger.debug(f"[APIEndpoints] Dashboard API URL from env: {url}")
            return url

        url = APIEndpointConfig.ENDPOINTS['dashboard_api']
        logger.debug(f"[APIEndpoints] Dashboard API URL: {url}")
        return url

    @staticmethod
    def get_endpoint(service_name: str) -> str:
        """Get endpoint URL for any registered service.

        Args:
            service_name: Service identifier (e.g., 'alpaca_trading', 'iex_cloud')

        Returns:
            str: Endpoint URL

        Raises:
            ValueError: If service_name not recognized
        """
        service_name_lower = service_name.lower()

        # Delegate to service-specific methods for logic
        if service_name_lower == 'alpaca_trading':
            return APIEndpointConfig.get_alpaca_trading_url()
        elif service_name_lower == 'alpaca_data':
            return APIEndpointConfig.get_alpaca_data_url()
        elif service_name_lower == 'iex_cloud':
            return APIEndpointConfig.get_iex_cloud_url()
        elif service_name_lower == 'yahoo_finance':
            return APIEndpointConfig.get_yahoo_finance_url()
        elif service_name_lower == 'aaii_sentiment':
            return APIEndpointConfig.get_aaii_sentiment_url()
        elif service_name_lower == 'fred':
            return APIEndpointConfig.get_fred_url()
        elif service_name_lower == 'dashboard_api':
            return APIEndpointConfig.get_dashboard_api_url()
        else:
            raise ValueError(f"Unknown service: {service_name}")

    @staticmethod
    def list_endpoints() -> Dict[str, str]:
        """List all available endpoints and their current values.

        Returns:
            Dict mapping service name to URL
        """
        return {
            'alpaca_trading': APIEndpointConfig.get_alpaca_trading_url(),
            'alpaca_data': APIEndpointConfig.get_alpaca_data_url(),
            'iex_cloud': APIEndpointConfig.get_iex_cloud_url(),
            'yahoo_finance': APIEndpointConfig.get_yahoo_finance_url(),
            'aaii_sentiment': APIEndpointConfig.get_aaii_sentiment_url(),
            'fred': APIEndpointConfig.get_fred_url(),
            'dashboard_api': APIEndpointConfig.get_dashboard_api_url(),
        }


# Module-level convenience functions for backward compatibility
def get_alpaca_trading_url() -> str:
    """Get Alpaca trading API URL. (Delegates to APIEndpointConfig)"""
    return APIEndpointConfig.get_alpaca_trading_url()


def get_alpaca_data_url() -> str:
    """Get Alpaca Data API URL. (Delegates to APIEndpointConfig)"""
    return APIEndpointConfig.get_alpaca_data_url()


def get_iex_cloud_url() -> str:
    """Get IEX Cloud API URL."""
    return APIEndpointConfig.get_iex_cloud_url()


def get_yahoo_finance_url() -> str:
    """Get Yahoo Finance API URL."""
    return APIEndpointConfig.get_yahoo_finance_url()


def get_aaii_sentiment_url() -> str:
    """Get AAII sentiment survey URL."""
    return APIEndpointConfig.get_aaii_sentiment_url()


def get_fred_url() -> str:
    """Get FRED API URL."""
    return APIEndpointConfig.get_fred_url()


def get_dashboard_api_url() -> str:
    """Get Dashboard API endpoint URL."""
    return APIEndpointConfig.get_dashboard_api_url()


def get_endpoint(service_name: str) -> str:
    """Get endpoint URL for any registered service."""
    return APIEndpointConfig.get_endpoint(service_name)
