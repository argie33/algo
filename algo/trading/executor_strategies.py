#!/usr/bin/env python3
"""Execution mode strategies for TradeExecutor.

Replaces if-elif chains with polymorphic strategy classes, enabling:
- Type-safe mode handling
- Easy mode-specific behavior injection
- Clear separation of concerns per execution mode
"""

import logging
import os
from abc import ABC, abstractmethod

logger = logging.getLogger(__name__)


class ExecutionModeStrategy(ABC):
    """Base class for execution mode strategies.

    Each strategy encapsulates the behavior for one execution mode:
    - paper: Alpaca paper trading (sandbox)
    - review: Manual review required before execution (dry-run)
    - auto: Live/real trading with safety checks
    """

    @abstractmethod
    def resolve_base_url(self, configured_url: str | None) -> str:
        """Resolve Alpaca API base URL.

        Args:
            configured_url: URL from APCA_API_BASE_URL env var

        Returns:
            Resolved API base URL for this mode
        """

    @abstractmethod
    def resolve_paper_mode(self) -> bool:
        """Whether this mode uses paper trading."""

    @abstractmethod
    def validate_and_log_initialization(
        self, alpaca_key: str | None, alpaca_secret: str | None, resolved_url: str
    ) -> None:
        """Validate configuration and log initialization details.

        Raises:
            ValueError: If critical configuration is missing
        """

    @property
    @abstractmethod
    def name(self) -> str:
        """Human-readable mode name."""


class PaperExecutionMode(ExecutionModeStrategy):
    """Paper trading mode: Alpaca sandbox for testing.

    Always uses Alpaca paper trading endpoint, regardless of environment
    variables. Intended for development and testing.
    """

    @property
    def name(self) -> str:
        return "paper"

    def resolve_base_url(self, configured_url: str | None) -> str:
        return "https://paper-api.alpaca.markets"

    def resolve_paper_mode(self) -> bool:
        return True

    def validate_and_log_initialization(
        self, alpaca_key: str | None, alpaca_secret: str | None, resolved_url: str
    ) -> None:
        logger.info(f"[EXECUTOR] mode=paper (sandbox) | key_set={bool(alpaca_key)} secret_set={bool(alpaca_secret)}")


class ReviewExecutionMode(ExecutionModeStrategy):
    """Review mode: Dry-run that logs trade signals without executing.

    Trades are validated but not executed, for manual review of signals
    before automatic execution is enabled.
    """

    @property
    def name(self) -> str:
        return "review"

    def resolve_base_url(self, configured_url: str | None) -> str:
        return "https://paper-api.alpaca.markets"

    def resolve_paper_mode(self) -> bool:
        return True

    def validate_and_log_initialization(
        self, alpaca_key: str | None, alpaca_secret: str | None, resolved_url: str
    ) -> None:
        logger.info(
            "[EXECUTOR] mode=review (dry-run, no execution) | "
            f"key_set={bool(alpaca_key)} secret_set={bool(alpaca_secret)}"
        )


class AutoExecutionMode(ExecutionModeStrategy):
    """Auto mode: Live/real trading with safety guards.

    Requires explicit ALGO_LIVE_TRADING environment variable and Alpaca live
    credentials. Falls back to paper trading if any guard fails.
    """

    @property
    def name(self) -> str:
        return "auto"

    def resolve_base_url(self, configured_url: str | None) -> str:
        live_intent = self._check_live_intent(configured_url)
        if not live_intent:
            return "https://paper-api.alpaca.markets"
        return configured_url or "https://api.alpaca.markets"

    def resolve_paper_mode(self) -> bool:
        # CRITICAL FIX: Auto mode should return True for paper mode when using paper API
        # The base URL is paper-api.alpaca.markets in dev/test, so paper_mode must match
        # Otherwise is_paper flag is inconsistent with actual URL being used
        return "paper" in (self.resolve_base_url(None) or "").lower()

    def validate_and_log_initialization(
        self, alpaca_key: str | None, alpaca_secret: str | None, resolved_url: str
    ) -> None:
        live_ack = os.getenv("ALGO_LIVE_TRADING", "").strip()
        paper_flag = os.getenv("ALPACA_PAPER_TRADING", "true").strip().lower()
        url_says_paper = "paper" in (resolved_url or "").lower()
        live_intent = live_ack == "I_UNDERSTAND_REAL_MONEY" and paper_flag != "true" and not url_says_paper

        logger.info(
            f"[EXECUTOR] mode=auto live_intent={live_intent} "
            f"({'LIVE TRADING  api.alpaca.markets' if live_intent else 'PAPER TRADING  paper-api.alpaca.markets'}) | "
            f"live_ack={'SET' if live_ack == 'I_UNDERSTAND_REAL_MONEY' else 'NOT SET'} "
            f"paper_flag={paper_flag} url_says_paper={url_says_paper} "
            f"key_set={bool(alpaca_key)} secret_set={bool(alpaca_secret)}"
        )

        if not live_intent:
            reasons = []
            if live_ack != "I_UNDERSTAND_REAL_MONEY":
                reasons.append(f"ALGO_LIVE_TRADING not set to 'I_UNDERSTAND_REAL_MONEY' (got '{live_ack}')")
            if paper_flag == "true":
                reasons.append("ALPACA_PAPER_TRADING=true")
            if url_says_paper:
                reasons.append(f"APCA_API_BASE_URL contains 'paper': {resolved_url}")
            logger.warning(
                f"[EXECUTOR] execution_mode=auto but forced to PAPER. Reason(s): {'; '.join(reasons) or 'unknown'}"
            )

    def _check_live_intent(self, configured_url: str | None) -> bool:
        live_ack = os.getenv("ALGO_LIVE_TRADING", "").strip()
        paper_flag = os.getenv("ALPACA_PAPER_TRADING", "true").strip().lower()
        url_says_paper = "paper" in (configured_url or "").lower()
        return live_ack == "I_UNDERSTAND_REAL_MONEY" and paper_flag != "true" and not url_says_paper


def create_execution_mode_strategy(mode: str) -> ExecutionModeStrategy:
    """Factory to create execution mode strategy.

    Args:
        mode: Execution mode string ('paper', 'review', 'auto')

    Returns:
        ExecutionModeStrategy: Concrete strategy instance

    Raises:
        ValueError: If mode is invalid
    """
    strategies = {
        "paper": PaperExecutionMode(),
        "review": ReviewExecutionMode(),
        "auto": AutoExecutionMode(),
    }

    if mode not in strategies:
        raise ValueError(f"Invalid execution_mode: '{mode}'. Must be one of: {', '.join(strategies.keys())}")

    return strategies[mode]
