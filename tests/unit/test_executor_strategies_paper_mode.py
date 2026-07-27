#!/usr/bin/env python3
"""AutoExecutionMode.resolve_paper_mode() re-derived live_intent by calling
resolve_base_url(None) - discarding the real APCA_API_BASE_URL env var executor.py itself
reads to resolve the base URL actually used for order submission. When that env var was
explicitly set to the paper endpoint while ALGO_LIVE_TRADING/ALPACA_PAPER_TRADING otherwise
signaled live intent, resolve_base_url() correctly forced orders to paper-api.alpaca.markets,
but resolve_paper_mode() (recomputing with configured_url=None) reported is_paper=False,
i.e. claimed LIVE. resolve_paper_mode() must reflect the same URL orders actually go to.
"""

from algo.trading.executor_strategies import AutoExecutionMode


def test_paper_mode_matches_actual_base_url_when_env_says_paper(monkeypatch):
    monkeypatch.setenv("ALGO_LIVE_TRADING", "I_UNDERSTAND_REAL_MONEY")
    monkeypatch.setenv("ALPACA_PAPER_TRADING", "false")
    monkeypatch.setenv("APCA_API_BASE_URL", "https://paper-api.alpaca.markets")

    strategy = AutoExecutionMode()
    resolved_url = strategy.resolve_base_url("https://paper-api.alpaca.markets")

    assert resolved_url == "https://paper-api.alpaca.markets"
    assert strategy.resolve_paper_mode() is True


def test_paper_mode_matches_actual_base_url_when_live(monkeypatch):
    monkeypatch.setenv("ALGO_LIVE_TRADING", "I_UNDERSTAND_REAL_MONEY")
    monkeypatch.setenv("ALPACA_PAPER_TRADING", "false")
    monkeypatch.setenv("APCA_API_BASE_URL", "https://api.alpaca.markets")

    strategy = AutoExecutionMode()
    resolved_url = strategy.resolve_base_url("https://api.alpaca.markets")

    assert resolved_url == "https://api.alpaca.markets"
    assert strategy.resolve_paper_mode() is False


def test_paper_mode_true_without_live_acknowledgement(monkeypatch):
    monkeypatch.delenv("ALGO_LIVE_TRADING", raising=False)
    monkeypatch.setenv("ALPACA_PAPER_TRADING", "false")
    monkeypatch.setenv("APCA_API_BASE_URL", "https://api.alpaca.markets")

    strategy = AutoExecutionMode()
    assert strategy.resolve_paper_mode() is True
