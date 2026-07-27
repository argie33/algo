#!/usr/bin/env python3
"""config.api_endpoints.get_alpaca_base_url() previously ignored APCA_API_BASE_URL entirely
and unconditionally returned the paper-trading URL. Every caller that hits this function
directly (market_events.py, position_monitor.py's order-cancellation and corporate-action
quantity checks, lambda/execution-monitor/index.py) bypasses executor.py's mode-aware
execution_mode_strategy.resolve_base_url() - the only place execution_mode/ALGO_LIVE_TRADING
actually gets consulted. Since this codebase uses a single shared Alpaca key/secret pair for
both paper and live (see config/credential_manager.py - there is no separate live-credential
concept, only the base URL differs), those callers would silently operate against the PAPER
account with live credentials once real trading is enabled, unless this function also honors
APCA_API_BASE_URL.
"""

from config.api_endpoints import get_alpaca_base_url


def test_honors_apca_api_base_url_env_var(monkeypatch):
    monkeypatch.setenv("APCA_API_BASE_URL", "https://api.alpaca.markets")
    assert get_alpaca_base_url() == "https://api.alpaca.markets"


def test_falls_back_to_paper_when_env_var_unset(monkeypatch):
    monkeypatch.delenv("APCA_API_BASE_URL", raising=False)
    assert get_alpaca_base_url() == "https://paper-api.alpaca.markets"


def test_falls_back_to_paper_when_env_var_empty(monkeypatch):
    monkeypatch.setenv("APCA_API_BASE_URL", "")
    assert get_alpaca_base_url() == "https://paper-api.alpaca.markets"
