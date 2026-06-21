#!/usr/bin/env python3
"""LoaderFacade - public interface for loader handlers.

This module provides facades that encapsulate private loader details and expose
only the public interface needed by handlers. This eliminates message chains
where handlers accessed private members of loaders across multiple levels.

Pattern:
    Before: handler.run(symbol, rows, loader._private_field)
    After:  loader_facade.run_signal_generation(symbol, rows)

Benefits:
1. Handlers don't access private members of loaders
2. Breaks message chain that crossed 3+ levels of encapsulation
3. Loader implementation details hidden behind facade
4. Easier to refactor loader internals without breaking handlers
"""

from typing import Any


class SignalsDailyLoaderFacade:
    """Public facade for SignalsDailyLoader.

    Provides a clean public interface for BuySignalGenerationHandler
    without exposing private loader implementation details.
    """

    def __init__(self, loader: Any) -> None:
        """Initialize facade with reference to SignalsDailyLoader.

        Args:
            loader: SignalsDailyLoader instance to wrap
        """
        self._loader = loader

    def run_signal_generation(
        self, symbol: str, rows: list[dict]
    ) -> list[dict]:
        """Generate buy/sell signals from technical indicator data.

        This is the public facade method that handlers should use instead of
        accessing private loader members directly.

        Args:
            symbol: Ticker symbol
            rows: List of technical data rows with OHLCV and indicators

        Returns:
            List of signal dicts with entry/exit levels and metrics
        """
        from loaders.buy_signal_generation_handler import BuySignalGenerationHandler

        handler = BuySignalGenerationHandler(self._loader)
        tech_data_age = (
            self._loader._batch_context.get("tech_data_age")
            if self._loader._batch_context
            else None
        )
        return handler.run(symbol, rows, tech_data_age)


class MarketHealthDailyLoaderFacade:
    """Public facade for MarketHealthDailyLoader.

    Provides a clean public interface for MarketHealthComputationHandler
    without exposing private loader implementation details.
    """

    def __init__(self, loader: Any) -> None:
        """Initialize facade with reference to MarketHealthDailyLoader.

        Args:
            loader: MarketHealthDailyLoader instance to wrap
        """
        self._loader = loader

    def run_market_health_computation(
        self, symbol: str, start: Any, end: Any
    ) -> dict[str, Any]:
        """Compute market health metrics for a symbol.

        This is the public facade method that handlers should use instead of
        accessing private loader members directly.

        Args:
            symbol: Ticker symbol
            start: Start date for computation
            end: End date for computation

        Returns:
            Dict with computed market health metrics
        """
        from loaders.market_health_computation_handler import (
            MarketHealthComputationHandler,
        )

        handler = MarketHealthComputationHandler(self._loader)
        return handler.compute(symbol, start, end)
