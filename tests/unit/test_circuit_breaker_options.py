"""Tests for algo/risk/circuit_breaker_options.py - phase 4 options-sleeve pretrade checks.

Uses a small fake cursor that dispatches canned results by recognizing which query was just
executed (the underlying SQL shapes issued by algo/risk/options_collateral.py are each
distinguishable by a unique substring) rather than a MagicMock with a fixed fetchone
side_effect list, since check_options_pretrade fans out to a variable number of underlying
queries depending on strategy_leg/sector branching.
"""

from decimal import Decimal
from unittest.mock import MagicMock

import pytest

from algo.risk.circuit_breaker_options import check_options_pretrade


class FakeOptionsCursor:
    def __init__(
        self,
        committed_collateral=Decimal("0"),
        symbol_exposure=(Decimal("0"), Decimal("0")),
        sector_exposure=(Decimal("0"), Decimal("0")),
        equity_open=False,
        sleeve_overlap=False,
    ):
        self.committed_collateral = committed_collateral
        self.symbol_exposure = symbol_exposure
        self.sector_exposure = sector_exposure
        self.equity_open = equity_open
        self.sleeve_overlap = sleeve_overlap
        self._last_sql = ""
        self.executed = []

    def execute(self, sql, params=None):
        self._last_sql = sql
        self.executed.append(sql)

    def fetchone(self):
        sql = self._last_sql
        if "SUM(collateral_amount), 0)" in sql and "FILTER" not in sql:
            return (self.committed_collateral,)
        if "WHERE symbol = %s" in sql and "FILTER" in sql:
            return self.symbol_exposure
        if "WHERE sector = %s" in sql:
            return self.sector_exposure
        if "FROM algo_positions WHERE symbol" in sql:
            return (1,) if self.equity_open else None
        if "FROM algo_options_positions WHERE symbol = %s AND status IN" in sql:
            return (1,) if self.sleeve_overlap else None
        raise AssertionError(f"Unrecognized query in fake cursor: {sql}")


def _noop_halt_manager():
    return MagicMock()


def test_clean_csp_candidate_passes_every_check():
    # $50 strike * 100 * 1 contract = $5,000 collateral, within the $10,000 sleeve cap
    # (5% of $200,000 equity).
    cur = FakeOptionsCursor()
    halt_mgr = _noop_halt_manager()
    result = check_options_pretrade(
        cur,
        symbol="AAPL",
        sector="Technology",
        strategy_leg="csp",
        strike=Decimal("50"),
        contracts=1,
        account_equity=Decimal("200000"),
        halt_manager=halt_mgr,
    )
    assert result["halted"] is False
    assert result["halt_reasons"] == []
    assert set(result["checks"]) == {
        "collateral_accounting_sane",
        "sleeve_cap",
        "per_underlying_cap",
        "sector_cap",
        "no_equity_overlap",
        "cash_collateral_available",
    }
    halt_mgr.set_halt_flag.assert_not_called()


def test_covered_call_requires_no_new_cash_collateral():
    cur = FakeOptionsCursor()
    result = check_options_pretrade(
        cur,
        symbol="AAPL",
        sector="Technology",
        strategy_leg="covered_call",
        strike=Decimal("160"),
        contracts=1,
        account_equity=Decimal("200000"),
        halt_manager=_noop_halt_manager(),
    )
    assert result["checks"]["sleeve_cap"]["halted"] is False
    assert result["checks"]["cash_collateral_available"]["halted"] is False


def test_negative_committed_collateral_halts_and_calls_halt_manager():
    cur = FakeOptionsCursor(committed_collateral=Decimal("-500"))
    halt_mgr = _noop_halt_manager()
    result = check_options_pretrade(
        cur,
        symbol="AAPL",
        sector="Technology",
        strategy_leg="csp",
        strike=Decimal("150"),
        contracts=1,
        account_equity=Decimal("200000"),
        halt_manager=halt_mgr,
    )
    assert result["halted"] is True
    assert result["checks"]["collateral_accounting_sane"]["halted"] is True
    halt_mgr.set_halt_flag.assert_called_once()
    call_kwargs = halt_mgr.set_halt_flag.call_args.kwargs
    assert call_kwargs["triggered_by"] == "circuit_breaker_options"


def test_committed_collateral_exceeding_sleeve_cap_halts():
    # $10,000 sleeve cap on $200,000 equity, $15,000 already committed - internally
    # inconsistent (should never happen if accounting is correct).
    cur = FakeOptionsCursor(committed_collateral=Decimal("15000"))
    halt_mgr = _noop_halt_manager()
    result = check_options_pretrade(
        cur,
        symbol="AAPL",
        sector="Technology",
        strategy_leg="csp",
        strike=Decimal("150"),
        contracts=1,
        account_equity=Decimal("200000"),
        halt_manager=halt_mgr,
    )
    assert result["checks"]["collateral_accounting_sane"]["halted"] is True
    halt_mgr.set_halt_flag.assert_called_once()


def test_halt_manager_raise_propagates_when_both_backends_fail():
    cur = FakeOptionsCursor(committed_collateral=Decimal("-1"))
    halt_mgr = MagicMock()
    halt_mgr.set_halt_flag.side_effect = RuntimeError("both DynamoDB and RDS failed")
    with pytest.raises(RuntimeError, match="halt flag could not be set"):
        check_options_pretrade(
            cur,
            symbol="AAPL",
            sector="Technology",
            strategy_leg="csp",
            strike=Decimal("150"),
            contracts=1,
            account_equity=Decimal("200000"),
            halt_manager=halt_mgr,
        )


def test_sleeve_cap_breached_by_oversized_csp():
    # $10,000 sleeve cap (5% of $200,000); a single 100-contract $150 strike CSP requires
    # $1,500,000 collateral - far beyond the sleeve.
    cur = FakeOptionsCursor()
    result = check_options_pretrade(
        cur,
        symbol="AAPL",
        sector="Technology",
        strategy_leg="csp",
        strike=Decimal("150"),
        contracts=100,
        account_equity=Decimal("200000"),
        halt_manager=_noop_halt_manager(),
    )
    assert result["halted"] is True
    assert result["checks"]["sleeve_cap"]["halted"] is True
    assert result["checks"]["cash_collateral_available"]["halted"] is True


def test_per_underlying_cap_breach():
    # $9,000 exposure on a $10,000 sleeve = 90%, well past the 20% per-underlying cap.
    cur = FakeOptionsCursor(symbol_exposure=(Decimal("9000"), Decimal("0")))
    result = check_options_pretrade(
        cur,
        symbol="AAPL",
        sector="Technology",
        strategy_leg="csp",
        strike=Decimal("1"),
        contracts=1,
        account_equity=Decimal("200000"),
        halt_manager=_noop_halt_manager(),
    )
    assert result["checks"]["per_underlying_cap"]["halted"] is True
    assert result["halted"] is True


def test_sector_cap_breach():
    cur = FakeOptionsCursor(sector_exposure=(Decimal("5000"), Decimal("0")))
    result = check_options_pretrade(
        cur,
        symbol="AAPL",
        sector="Technology",
        strategy_leg="csp",
        strike=Decimal("1"),
        contracts=1,
        account_equity=Decimal("200000"),
        halt_manager=_noop_halt_manager(),
    )
    assert result["checks"]["sector_cap"]["halted"] is True


def test_missing_sector_fails_closed():
    cur = FakeOptionsCursor()
    result = check_options_pretrade(
        cur,
        symbol="AAPL",
        sector=None,
        strategy_leg="csp",
        strike=Decimal("1"),
        contracts=1,
        account_equity=Decimal("200000"),
        halt_manager=_noop_halt_manager(),
    )
    assert result["checks"]["sector_cap"]["halted"] is True
    assert "Sector is missing" in result["checks"]["sector_cap"]["reason"]


def test_equity_overlap_halts_candidate():
    cur = FakeOptionsCursor(equity_open=True)
    result = check_options_pretrade(
        cur,
        symbol="AAPL",
        sector="Technology",
        strategy_leg="csp",
        strike=Decimal("1"),
        contracts=1,
        account_equity=Decimal("200000"),
        halt_manager=_noop_halt_manager(),
    )
    assert result["checks"]["no_equity_overlap"]["halted"] is True
    assert result["halted"] is True


def test_sleeve_overlap_halts_candidate():
    cur = FakeOptionsCursor(sleeve_overlap=True)
    result = check_options_pretrade(
        cur,
        symbol="AAPL",
        sector="Technology",
        strategy_leg="csp",
        strike=Decimal("1"),
        contracts=1,
        account_equity=Decimal("200000"),
        halt_manager=_noop_halt_manager(),
    )
    assert result["checks"]["no_equity_overlap"]["halted"] is True


def test_default_halt_manager_constructed_when_not_provided():
    """Calling without an explicit halt_manager must not raise - it lazily builds a real
    HaltFlagManager (mirrors algo/risk/intraday_risk_monitor.py's same default-construction
    pattern), which is only actually invoked on the collateral-accounting-sane check."""
    cur = FakeOptionsCursor()
    result = check_options_pretrade(
        cur,
        symbol="AAPL",
        sector="Technology",
        strategy_leg="csp",
        strike=Decimal("1"),
        contracts=1,
        account_equity=Decimal("200000"),
    )
    assert result["halted"] is False
