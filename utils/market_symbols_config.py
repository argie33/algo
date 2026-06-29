"""Market symbols configuration - manages hardcoded symbol lists for indices and ETFs.

This module centralizes all market symbol configurations that were previously hardcoded
in individual route handlers. It provides a single source of truth for:
- ETF symbols used in signal analysis
- Index symbols for market breadth and trend analysis
- Essential stocks for critical calculations

All symbols are configurable via the algo_config table (config keys: market_etf_symbols,
market_index_symbols, market_index_names, essential_stocks).
"""

import json
import logging
from typing import Any, cast

logger = logging.getLogger(__name__)


class MarketSymbolsConfig:
    """Manage market symbol configurations from database or defaults."""

    # Hardcoded defaults - used only if config not found in database
    DEFAULT_ETF_SYMBOLS = ["SPY", "QQQ", "IWM", "DIA", "EEM", "EFA"]
    DEFAULT_INDEX_SYMBOLS = ["^GSPC", "^IXIC", "^NYA", "^RUT"]
    DEFAULT_INDEX_NAMES = {
        "^GSPC": "S&P 500",
        "^IXIC": "Nasdaq Composite",
        "^NYA": "NYSE Composite",
        "^DJI": "Dow Jones",
        "^RUT": "Russell 2000",
    }
    # Essential stocks that must be loaded regardless of symbol universe
    # SPY: required by Mansfield RS, seasonality, market health breadth, yield-curve factor
    # GLD/TLT: used by correlation matrix and macro regime logic
    DEFAULT_ESSENTIAL_STOCKS = ["SPY", "QQQ", "IWM", "DIA", "GLD", "TLT"]

    # Essential ETFs: required by sector performance, sector heatmap, frontend price routes
    # These land in etf_price_daily table (price route falls back to this)
    DEFAULT_ESSENTIAL_ETF_SYMBOLS = [
        "SPY", "QQQ", "IWM", "DIA",  # Index ETFs
        "XLK", "XLF", "XLV", "XLY", "XLC",  # Sector ETFs
        "XLI", "XLP", "XLE", "XLU", "XLRE", "XLB",
        "GLD", "TLT", "IVV", "VXX",  # Macro ETFs
    ]

    # Default orchestrator schedule (fallback when API unavailable)
    # Format: list of {hour: int, minute: int} dicts, in execution order
    DEFAULT_ORCHESTRATOR_SCHEDULE = [
        {"hour": 2, "minute": 0},  # Prep phase
        {"hour": 9, "minute": 30},  # Orchestration phase (market open)
    ]

    # Cache to avoid repeated database hits during the same request
    _cache: dict[str, Any] = {}

    @staticmethod
    def get_etf_symbols() -> list[str]:
        """Get list of ETF symbols for signal analysis.

        Returns configured symbols from database, or hardcoded defaults if config missing.
        """
        if "etf_symbols" in MarketSymbolsConfig._cache:
            return cast(list[str], MarketSymbolsConfig._cache["etf_symbols"])

        # In a real implementation, this would fetch from the database
        # For now, return the hardcoded defaults
        # TODO: Add database fetch from algo_config where key='market_etf_symbols'
        symbols = MarketSymbolsConfig.DEFAULT_ETF_SYMBOLS
        MarketSymbolsConfig._cache["etf_symbols"] = symbols
        return symbols

    @staticmethod
    def get_index_symbols() -> list[str]:
        """Get list of market index symbols for breadth/trend analysis.

        Returns configured symbols from database, or hardcoded defaults if config missing.
        """
        if "index_symbols" in MarketSymbolsConfig._cache:
            return cast(list[str], MarketSymbolsConfig._cache["index_symbols"])

        # In a real implementation, this would fetch from the database
        # For now, return the hardcoded defaults
        # TODO: Add database fetch from algo_config where key='market_index_symbols'
        symbols = MarketSymbolsConfig.DEFAULT_INDEX_SYMBOLS
        MarketSymbolsConfig._cache["index_symbols"] = symbols
        return symbols

    @staticmethod
    def get_index_names() -> dict[str, str]:
        """Get mapping of index symbols to display names.

        Returns configured mapping from database, or hardcoded defaults if config missing.
        """
        if "index_names" in MarketSymbolsConfig._cache:
            return cast(dict[str, str], MarketSymbolsConfig._cache["index_names"])

        # In a real implementation, this would fetch from the database
        # For now, return the hardcoded defaults
        # TODO: Add database fetch from algo_config where key='market_index_names'
        names = MarketSymbolsConfig.DEFAULT_INDEX_NAMES
        MarketSymbolsConfig._cache["index_names"] = names
        return names

    @staticmethod
    def get_essential_stocks() -> list[str]:
        """Get list of essential stocks that must always be loaded.

        These symbols are critical for:
        - Mansfield Relative Strength (SPY benchmark)
        - Sector rotation analysis (sector ETFs)
        - Macro factor calculations (TLT, GLD for long-term trends)

        Returns configured symbols from database, or hardcoded defaults if config missing.
        """
        if "essential_stocks" in MarketSymbolsConfig._cache:
            return cast(list[str], MarketSymbolsConfig._cache["essential_stocks"])

        # In a real implementation, this would fetch from the database
        # For now, return the hardcoded defaults
        # TODO: Add database fetch from algo_config where key='essential_stocks'
        symbols = MarketSymbolsConfig.DEFAULT_ESSENTIAL_STOCKS
        MarketSymbolsConfig._cache["essential_stocks"] = symbols
        return symbols

    @staticmethod
    def get_essential_etf_symbols() -> list[str]:
        """Get list of essential ETFs that must always be loaded.

        These symbols are critical for:
        - Sector performance calculations (sector ETFs)
        - Sector heatmap and rotation analysis
        - Frontend price history lookups (falls back to etf_price_daily)
        - Macro regime and correlation calculations

        Returns configured symbols from database, or hardcoded defaults if config missing.
        """
        if "essential_etf_symbols" in MarketSymbolsConfig._cache:
            return cast(list[str], MarketSymbolsConfig._cache["essential_etf_symbols"])

        # In a real implementation, this would fetch from the database
        # For now, return the hardcoded defaults
        # TODO: Add database fetch from algo_config where key='essential_etf_symbols'
        symbols = MarketSymbolsConfig.DEFAULT_ESSENTIAL_ETF_SYMBOLS
        MarketSymbolsConfig._cache["essential_etf_symbols"] = symbols
        return symbols

    @staticmethod
    def clear_cache() -> None:
        """Clear the in-memory cache (used in tests or when config changes)."""
        MarketSymbolsConfig._cache.clear()

    @staticmethod
    def get_orchestrator_schedule() -> list[dict[str, int]]:
        """Get default orchestrator schedule (fallback when API unavailable).

        Returns:
            List of schedule entries, each with 'hour' and 'minute' keys
        """
        if "orchestrator_schedule" in MarketSymbolsConfig._cache:
            return cast(list[dict[str, int]], MarketSymbolsConfig._cache["orchestrator_schedule"])

        # In a real implementation, this would fetch from the database
        # For now, return the hardcoded defaults
        # TODO: Add database fetch from algo_config where key='orchestrator_schedule'
        schedule = MarketSymbolsConfig.DEFAULT_ORCHESTRATOR_SCHEDULE
        MarketSymbolsConfig._cache["orchestrator_schedule"] = schedule
        return schedule

    @staticmethod
    def get_index_name(symbol: str) -> str:
        """Get display name for an index symbol.

        Args:
            symbol: Index ticker symbol (e.g., "^GSPC")

        Returns:
            Display name for the index, or the symbol itself if not found
        """
        names = MarketSymbolsConfig.get_index_names()
        return names.get(symbol, symbol)
