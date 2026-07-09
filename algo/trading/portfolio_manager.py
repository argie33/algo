#!/usr/bin/env python3
"""
Portfolio Manager - Query live portfolio value from Alpaca

Responsibilities:
- Fetch live portfolio value from Alpaca API
- Raise exception if Alpaca API unavailable (fail-fast, no stale fallback)
"""

import logging

import requests

from algo.infrastructure import get_api_timeout

logger = logging.getLogger(__name__)


class PortfolioManager:
    """Query live portfolio state from Alpaca only."""

    def __init__(self, alpaca_key: str, alpaca_secret: str, alpaca_base_url: str, config: dict | None = None) -> None:
        self.alpaca_key = alpaca_key
        self.alpaca_secret = alpaca_secret
        self.alpaca_base_url = alpaca_base_url
        self.config = config or {}

    def get_portfolio_value(self) -> float | None:
        """Live Alpaca equity only — raise exception if unavailable (no fallback to stale data)."""
        if not self.alpaca_key or not self.alpaca_secret:
            raise RuntimeError(
                "[PORTFOLIO] Critical: Alpaca credentials missing. Cannot fetch portfolio value without API access."
            )

        # PAPER MODE GRACEFUL DEGRADATION: In paper trading, if Alpaca API fails,
        # return a sensible default instead of crashing the orchestrator
        is_paper_mode = "paper" in (self.alpaca_base_url or "").lower()

        try:
            resp = requests.get(
                f"{self.alpaca_base_url}/v2/account",
                headers={
                    "APCA-API-KEY-ID": self.alpaca_key,
                    "APCA-API-SECRET-KEY": self.alpaca_secret,
                },
                timeout=get_api_timeout(),
            )
            if resp.status_code == 200:
                try:
                    data = resp.json()
                except (ValueError, Exception) as e:
                    raise RuntimeError(f"[PORTFOLIO] Critical: Invalid JSON response from Alpaca API: {e}") from e

                if "portfolio_value" in data and data["portfolio_value"] is not None:
                    pv_float = float(data["portfolio_value"])
                    logger.info(f"[PORTFOLIO] Live Alpaca equity: ${pv_float:.2f} (url={self.alpaca_base_url})")
                    return pv_float

                if "equity" in data and data["equity"] is not None:
                    pv_float = float(data["equity"])
                    logger.info(
                        f"[PORTFOLIO] Live Alpaca equity (from equity field): ${pv_float:.2f} (url={self.alpaca_base_url})"
                    )
                    return pv_float

                raise RuntimeError(
                    f"[PORTFOLIO] Critical: Alpaca API returned 200 but portfolio_value/equity missing or null. "
                    f"Cannot trade without portfolio value. Response keys: {list(data.keys())}"
                )
            elif resp.status_code == 401:
                if is_paper_mode:
                    initial_capital = self.config.get("initial_capital_paper_trading")
                    if not initial_capital:
                        raise RuntimeError(
                            "[PORTFOLIO] CRITICAL: Paper mode Alpaca 401 Unauthorized and initial_capital_paper_trading not configured. "
                            "Set initial_capital_paper_trading in algo_config table or provide credentials."
                        )
                    logger.warning(
                        f"[PORTFOLIO PAPER MODE] Alpaca 401 Unauthorized (credentials invalid/missing), "
                        f"using configured initial_capital_paper_trading=${initial_capital:.2f}"
                    )
                    return float(initial_capital)
                raise RuntimeError(
                    f"[PORTFOLIO] Critical: Alpaca 401 Unauthorized — APCA_API_KEY_ID/APCA_API_SECRET_KEY are wrong or expired. URL: {self.alpaca_base_url}"
                )
            elif resp.status_code == 403:
                if is_paper_mode:
                    initial_capital = self.config.get("initial_capital_paper_trading")
                    if not initial_capital:
                        raise RuntimeError(
                            "[PORTFOLIO] CRITICAL: Paper mode Alpaca 403 Forbidden and initial_capital_paper_trading not configured. "
                            "Set initial_capital_paper_trading in algo_config table or provide valid credentials."
                        )
                    logger.warning(
                        f"[PORTFOLIO PAPER MODE] Alpaca 403 Forbidden (key misconfiguration), "
                        f"using configured initial_capital_paper_trading=${initial_capital:.2f}"
                    )
                    return float(initial_capital)
                raise RuntimeError(
                    f"[PORTFOLIO] Critical: Alpaca 403 Forbidden — key may be live keys used with paper URL or vice versa. URL: {self.alpaca_base_url}"
                )
            else:
                if is_paper_mode:
                    initial_capital = self.config.get("initial_capital_paper_trading")
                    if not initial_capital:
                        raise RuntimeError(
                            f"[PORTFOLIO] CRITICAL: Paper mode Alpaca HTTP {resp.status_code} error and initial_capital_paper_trading not configured. "
                            "Set initial_capital_paper_trading in algo_config table to continue."
                        )
                    logger.warning(
                        f"[PORTFOLIO PAPER MODE] Alpaca API error (HTTP {resp.status_code}), "
                        f"using configured initial_capital_paper_trading=${initial_capital:.2f}"
                    )
                    return float(initial_capital)
                raise RuntimeError(
                    f"[PORTFOLIO] Critical: Alpaca /v2/account returned HTTP {resp.status_code}: {resp.text[:150]}"
                )
        except requests.RequestException as e:
            if is_paper_mode:
                initial_capital = self.config.get("initial_capital_paper_trading")
                if not initial_capital:
                    raise RuntimeError(
                        f"[PORTFOLIO] CRITICAL: Paper mode could not reach Alpaca API ({type(e).__name__}) "
                        "and initial_capital_paper_trading not configured. "
                        "Set initial_capital_paper_trading in algo_config table or fix network/credentials."
                    ) from e
                logger.warning(
                    f"[PORTFOLIO PAPER MODE] Could not reach Alpaca API ({type(e).__name__}), "
                    f"using configured initial_capital_paper_trading=${initial_capital:.2f}"
                )
                return float(initial_capital)
            raise RuntimeError(f"[PORTFOLIO] Critical: Could not fetch Alpaca account value: {e}") from e
        except RuntimeError:
            raise
