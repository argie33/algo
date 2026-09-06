"""Regression test: pretrade_checks.py's four portfolio-aggregate risk checks (correlation
diversification, portfolio-beta cap, top-5 concentration cap, simulated portfolio-VaR cap)
must fail CLOSED on a genuine DB error, not fail open.

BUG FOUND 2026-09-05 (real-money-readiness audit): unlike every other check in
PreTradeChecks.run_all() - duplicate-position, symbol-universe, sector/industry concentration
all raise ValueError on a psycopg2.DatabaseError/OperationalError - these four caught the same
exceptions, logged a warning, and let the trade proceed anyway ("failing open"). A transient DB
blip during, say, the top-5-concentration query meant a new entry that would push the book past
max_top5_concentration_pct sailed through unchecked - exactly the case that check exists to
catch, since per-position caps alone can't catch it. Fixed: all four now raise ValueError like
every other check in this function, matching this codebase's fail-closed doctrine. This does
NOT change the "insufficient data" paths inside _check_correlation_concentration/
_check_portfolio_beta, which still correctly return (True, None) as a real pass - those are
unaffected by this fix and not exercised here.
"""

from unittest.mock import MagicMock, patch

import psycopg2
import pytest

from algo.trading.pretrade_checks import PreTradeChecks

_MODULE = "algo.trading.pretrade_checks"


def _config():
    return {
        "max_position_size_pct": 5.0,
        "min_order_size_dollars": 100,
        "max_positions_per_sector": 10,
        "max_positions_per_industry": 10,
        "max_top5_concentration_pct": 30.0,
    }


class _FakeCursor:
    """Returns benign "no conflict" answers for every query run_all() issues before reaching
    the aggregate-risk checks under test, keyed off a distinctive substring in the SQL."""

    def execute(self, query, params=None):
        self._last_query = query

    def fetchone(self):
        q = self._last_query
        if "FROM algo_positions" in q and "SELECT symbol" in q:
            return None  # no existing open position for this symbol
        if "FROM algo_trades" in q:
            return None  # no existing open/pending trade
        if "closed_at" in q:
            return None  # no recently-closed position (re-entry cooldown check)
        if "FROM stock_symbols" in q:
            return ("TEST",)  # symbol is in the universe
        if "FROM company_profile" in q:
            return ("Technology", "Software")  # sector, industry
        if "COUNT(*)" in q:
            return (0,)  # zero existing positions in this sector/industry
        if "FROM stability_metrics" in q:
            return None  # no beta data available - _check_portfolio_beta's own (True, None) path
        raise AssertionError(f"unexpected fetchone() query: {q}")

    def fetchall(self):
        return []


def _db_context_mock():
    mock_ctx = MagicMock()
    mock_ctx.__enter__.return_value = _FakeCursor()
    mock_ctx.__exit__.return_value = False
    return mock_ctx


def _run_all_sell(checks: PreTradeChecks) -> tuple[bool, str | None]:
    # side="SELL" skips the earnings-blackout check entirely (only gates BUY), keeping the
    # fake cursor simple - irrelevant to what's under test here.
    return checks.run_all(symbol="TEST", position_value=1000.0, portfolio_value=100_000.0, side="SELL")


class TestAggregateRiskChecksFailClosedOnDbError:
    def test_correlation_check_db_error_raises_not_passes(self):
        checks = PreTradeChecks(config=_config())
        with (
            patch(f"{_MODULE}.DatabaseContext", return_value=_db_context_mock()),
            patch.object(
                checks,
                "_check_correlation_concentration",
                side_effect=psycopg2.DatabaseError("connection reset"),
            ),
            pytest.raises(ValueError, match="correlation-diversification"),
        ):
            _run_all_sell(checks)

    def test_portfolio_beta_check_db_error_raises_not_passes(self):
        checks = PreTradeChecks(config=_config())
        with (
            patch(f"{_MODULE}.DatabaseContext", return_value=_db_context_mock()),
            patch.object(
                checks,
                "_check_portfolio_beta",
                side_effect=psycopg2.OperationalError("connection reset"),
            ),
            pytest.raises(ValueError, match="portfolio-beta"),
        ):
            _run_all_sell(checks)

    def test_top5_concentration_check_db_error_raises_not_passes(self):
        checks = PreTradeChecks(config=_config())
        with (
            patch(f"{_MODULE}.DatabaseContext", return_value=_db_context_mock()),
            patch.object(
                checks,
                "_check_top5_concentration",
                side_effect=psycopg2.DatabaseError("connection reset"),
            ),
            pytest.raises(ValueError, match="top-5 concentration"),
        ):
            _run_all_sell(checks)

    def test_simulated_var_check_db_error_raises_not_passes(self):
        checks = PreTradeChecks(config=_config())
        with (
            patch(f"{_MODULE}.DatabaseContext", return_value=_db_context_mock()),
            patch.object(
                checks,
                "_check_portfolio_simulated_var",
                side_effect=psycopg2.DatabaseError("connection reset"),
            ),
            pytest.raises(ValueError, match="simulated portfolio-VaR"),
        ):
            _run_all_sell(checks)

    def test_all_four_checks_pass_cleanly_when_no_db_error(self):
        """Sanity check: with no injected error, a clean run still approves the trade -
        confirms the fake cursor setup itself isn't accidentally causing a rejection."""
        checks = PreTradeChecks(config=_config())
        with (
            patch(f"{_MODULE}.DatabaseContext", return_value=_db_context_mock()),
            patch.object(checks, "_check_correlation_concentration", return_value=(True, None)),
            patch.object(checks, "_check_portfolio_beta", return_value=(True, None)),
            patch.object(checks, "_check_top5_concentration", return_value=(True, None)),
            patch.object(checks, "_check_portfolio_simulated_var", return_value=(True, None)),
        ):
            passed, reason = _run_all_sell(checks)
        assert passed is True, reason
