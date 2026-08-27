#!/usr/bin/env python3
"""Regression tests for scripts/verify_live_trading_readiness.py's check_live_intent_env_vars().

This function is a deliberate re-implementation of AutoExecutionMode._check_live_intent()
(algo/trading/executor_strategies.py) - if the two ever drift apart, this pre-flight script
could report READY while the real executor still resolves to paper (or vice versa), which
defeats the entire point of a pre-flight check. These tests pin the exact three conditions
(ALGO_LIVE_TRADING, ALPACA_PAPER_TRADING, APCA_API_BASE_URL) that must all agree for live
intent, matching executor_strategies.py's own test coverage for the same logic.
"""

from scripts.verify_live_trading_readiness import check_live_intent_env_vars


def test_all_three_conditions_met_passes(monkeypatch):
    monkeypatch.setenv("ALGO_LIVE_TRADING", "I_UNDERSTAND_REAL_MONEY")
    monkeypatch.setenv("ALPACA_PAPER_TRADING", "false")
    monkeypatch.setenv("APCA_API_BASE_URL", "https://api.alpaca.markets")
    assert check_live_intent_env_vars() == []


def test_missing_live_ack_fails(monkeypatch):
    monkeypatch.delenv("ALGO_LIVE_TRADING", raising=False)
    monkeypatch.setenv("ALPACA_PAPER_TRADING", "false")
    monkeypatch.setenv("APCA_API_BASE_URL", "https://api.alpaca.markets")
    failures = check_live_intent_env_vars()
    assert len(failures) == 1
    assert "ALGO_LIVE_TRADING" in failures[0]


def test_paper_flag_true_fails(monkeypatch):
    monkeypatch.setenv("ALGO_LIVE_TRADING", "I_UNDERSTAND_REAL_MONEY")
    monkeypatch.setenv("ALPACA_PAPER_TRADING", "true")
    monkeypatch.setenv("APCA_API_BASE_URL", "https://api.alpaca.markets")
    failures = check_live_intent_env_vars()
    assert len(failures) == 1
    assert "ALPACA_PAPER_TRADING" in failures[0]


def test_paper_flag_unset_defaults_true_and_fails(monkeypatch):
    monkeypatch.setenv("ALGO_LIVE_TRADING", "I_UNDERSTAND_REAL_MONEY")
    monkeypatch.delenv("ALPACA_PAPER_TRADING", raising=False)
    monkeypatch.setenv("APCA_API_BASE_URL", "https://api.alpaca.markets")
    failures = check_live_intent_env_vars()
    assert len(failures) == 1
    assert "ALPACA_PAPER_TRADING" in failures[0]


def test_missing_base_url_fails(monkeypatch):
    monkeypatch.setenv("ALGO_LIVE_TRADING", "I_UNDERSTAND_REAL_MONEY")
    monkeypatch.setenv("ALPACA_PAPER_TRADING", "false")
    monkeypatch.delenv("APCA_API_BASE_URL", raising=False)
    failures = check_live_intent_env_vars()
    assert len(failures) == 1
    assert "APCA_API_BASE_URL is not set" in failures[0]


def test_base_url_still_paper_fails_even_with_other_flags_correct(monkeypatch):
    """This is the exact real-world state confirmed live this session: someone sets the
    ack + paper flag but forgets the URL still points at paper-api.alpaca.markets."""
    monkeypatch.setenv("ALGO_LIVE_TRADING", "I_UNDERSTAND_REAL_MONEY")
    monkeypatch.setenv("ALPACA_PAPER_TRADING", "false")
    monkeypatch.setenv("APCA_API_BASE_URL", "https://paper-api.alpaca.markets")
    failures = check_live_intent_env_vars()
    assert len(failures) == 1
    assert "contains 'paper'" in failures[0]


def test_all_three_wrong_reports_all_three(monkeypatch):
    monkeypatch.delenv("ALGO_LIVE_TRADING", raising=False)
    monkeypatch.delenv("ALPACA_PAPER_TRADING", raising=False)
    monkeypatch.delenv("APCA_API_BASE_URL", raising=False)
    failures = check_live_intent_env_vars()
    assert len(failures) == 3
