"""Regression test: SignalTrendMixin.mansfield_rs() used to compute relative strength as
(stock_return / spy_return) - 1, a ratio that only has the correct sign when spy_return > 0.
Whenever SPY's trailing return over the lookback window was negative (any correction/pullback/
bear-market period - not rare), the ratio inverted: a stock outperforming a falling market could
score as NEGATIVE relative strength. Fixed 2026-08-25 by switching to a plain excess-return
spread (stock_return - spy_return), which is correctly signed regardless of SPY's return, and
has no division-by-near-zero instability either.

This feeds real signal-quality scoring via
algo/signals/advanced_filters.py::_mansfield_rs_score() -> SignalAPI.rank_rs_percentile(), part
of the live BUY-signal momentum subscore (algo/signals/advanced_filters.py:311) - not a
cosmetic/display-only bug.
"""

from datetime import date
from typing import Any
from unittest.mock import patch

from algo.signals.signal_computer import SignalComputer

EVAL_DATE = date(2026, 1, 15)


def _mansfield_rs(stock_ret: float, spy_ret: float) -> dict[str, Any]:
    computer = SignalComputer({})
    with (
        patch.object(computer, "_with_cursor", side_effect=lambda op: op(None)),
        patch.object(
            computer,
            "_period_return",
            side_effect=lambda cur, symbol, end_date, lookback: stock_ret if symbol != "SPY" else spy_ret,
        ),
    ):
        return computer.mansfield_rs("TEST", EVAL_DATE, lookback=60)


class TestMansfieldRSSignCorrectness:
    def test_stock_outperforms_falling_market_is_positive(self) -> None:
        """SPY -10%, stock +5%: the stock clearly beat the market. Must score POSITIVE.
        The old ratio formula produced (0.05 / -0.10) - 1 = -1.5 here - backwards."""
        result = _mansfield_rs(stock_ret=0.05, spy_ret=-0.10)

        assert result["positive"] is True
        assert result["mansfield_rs"] > 0
        assert result["mansfield_rs"] == 0.15  # 0.05 - (-0.10)

    def test_stock_falls_less_than_market_is_positive(self) -> None:
        """SPY -10%, stock -5%: the stock fell less - real outperformance. Must score POSITIVE.
        The old ratio formula produced (-0.05 / -0.10) - 1 = -0.5 here - also backwards."""
        result = _mansfield_rs(stock_ret=-0.05, spy_ret=-0.10)

        assert result["positive"] is True
        assert result["mansfield_rs"] > 0

    def test_stock_underperforms_rising_market_is_negative(self) -> None:
        """SPY +10%, stock +2%: the stock lagged a rising market. Must score NEGATIVE."""
        result = _mansfield_rs(stock_ret=0.02, spy_ret=0.10)

        assert result["positive"] is False
        assert result["mansfield_rs"] < 0

    def test_zero_spy_return_does_not_raise(self) -> None:
        """A flat SPY (0% return) must not raise - subtraction has no division, so this is a
        perfectly normal input (unlike the old ratio formula, which explicitly rejected it)."""
        result = _mansfield_rs(stock_ret=0.08, spy_ret=0.0)

        assert result["mansfield_rs"] == 0.08
        assert result["positive"] is True
