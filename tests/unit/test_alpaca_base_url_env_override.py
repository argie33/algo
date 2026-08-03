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

from algo.config.api_endpoints import get_alpaca_base_url


def test_honors_apca_api_base_url_env_var(monkeypatch):
    monkeypatch.setenv("APCA_API_BASE_URL", "https://api.alpaca.markets")
    assert get_alpaca_base_url() == "https://api.alpaca.markets"


def test_falls_back_to_paper_when_env_var_unset(monkeypatch):
    monkeypatch.delenv("APCA_API_BASE_URL", raising=False)
    assert get_alpaca_base_url() == "https://paper-api.alpaca.markets"


def test_falls_back_to_paper_when_env_var_empty(monkeypatch):
    monkeypatch.setenv("APCA_API_BASE_URL", "")
    assert get_alpaca_base_url() == "https://paper-api.alpaca.markets"


class TestExecutionModeAwareGate:
    """The env-var-presence-only check above closed the original bug (always paper) but
    introduced a narrower, inverted one: setting APCA_API_BASE_URL=<live> ahead of a future
    live cutover, before ALGO_LIVE_TRADING is acknowledged and while execution_mode is still
    "paper", would have pointed market_events/position_monitor at the LIVE account while
    order submission (executor.py) correctly stayed on paper. When execution_mode is passed,
    this must mirror AutoExecutionMode._check_live_intent()'s full gate exactly.
    """

    def test_paper_mode_always_returns_paper_even_with_live_url_configured(self, monkeypatch):
        monkeypatch.setenv("APCA_API_BASE_URL", "https://api.alpaca.markets")
        monkeypatch.setenv("ALGO_LIVE_TRADING", "I_UNDERSTAND_REAL_MONEY")
        monkeypatch.setenv("ALPACA_PAPER_TRADING", "false")
        assert get_alpaca_base_url("paper") == "https://paper-api.alpaca.markets"

    def test_review_mode_always_returns_paper_even_with_live_url_configured(self, monkeypatch):
        monkeypatch.setenv("APCA_API_BASE_URL", "https://api.alpaca.markets")
        monkeypatch.setenv("ALGO_LIVE_TRADING", "I_UNDERSTAND_REAL_MONEY")
        monkeypatch.setenv("ALPACA_PAPER_TRADING", "false")
        assert get_alpaca_base_url("review") == "https://paper-api.alpaca.markets"

    def test_auto_mode_without_live_acknowledgement_stays_paper(self, monkeypatch):
        """The exact live scenario: APCA_API_BASE_URL set ahead of a cutover, but
        ALGO_LIVE_TRADING not yet acknowledged - must NOT leak to the live account."""
        monkeypatch.setenv("APCA_API_BASE_URL", "https://api.alpaca.markets")
        monkeypatch.delenv("ALGO_LIVE_TRADING", raising=False)
        monkeypatch.setenv("ALPACA_PAPER_TRADING", "false")
        assert get_alpaca_base_url("auto") == "https://paper-api.alpaca.markets"

    def test_auto_mode_with_default_paper_flag_stays_paper(self, monkeypatch):
        """ALPACA_PAPER_TRADING defaults to 'true' when unset - must stay paper even if
        ALGO_LIVE_TRADING and the URL both say live."""
        monkeypatch.setenv("APCA_API_BASE_URL", "https://api.alpaca.markets")
        monkeypatch.setenv("ALGO_LIVE_TRADING", "I_UNDERSTAND_REAL_MONEY")
        monkeypatch.delenv("ALPACA_PAPER_TRADING", raising=False)
        assert get_alpaca_base_url("auto") == "https://paper-api.alpaca.markets"

    def test_auto_mode_all_conditions_met_goes_live(self, monkeypatch):
        monkeypatch.setenv("APCA_API_BASE_URL", "https://api.alpaca.markets")
        monkeypatch.setenv("ALGO_LIVE_TRADING", "I_UNDERSTAND_REAL_MONEY")
        monkeypatch.setenv("ALPACA_PAPER_TRADING", "false")
        assert get_alpaca_base_url("auto") == "https://api.alpaca.markets"

    def test_auto_mode_all_conditions_met_but_url_says_paper_stays_paper(self, monkeypatch):
        monkeypatch.setenv("APCA_API_BASE_URL", "https://paper-api.alpaca.markets")
        monkeypatch.setenv("ALGO_LIVE_TRADING", "I_UNDERSTAND_REAL_MONEY")
        monkeypatch.setenv("ALPACA_PAPER_TRADING", "false")
        assert get_alpaca_base_url("auto") == "https://paper-api.alpaca.markets"

    def test_auto_mode_live_intent_but_no_url_configured_defaults_to_live_endpoint(self, monkeypatch):
        monkeypatch.delenv("APCA_API_BASE_URL", raising=False)
        monkeypatch.setenv("ALGO_LIVE_TRADING", "I_UNDERSTAND_REAL_MONEY")
        monkeypatch.setenv("ALPACA_PAPER_TRADING", "false")
        assert get_alpaca_base_url("auto") == "https://api.alpaca.markets"
