#!/usr/bin/env python3
"""Regression test for algo/orchestrator/phase9_reconciliation.py's
_repair_missing_exit_prices(), found via systematic code audit 2026-08-10 (same
NaN-comparison-guard class fixed 40+ times elsewhere this session, inverted variant).

The pnl_pct_corrected calculation used `if entry_price != 0 else 0.0` as its guard against
division by zero - but `!=` is TRUE for NaN against everything, including 0 (`float('nan')
!= 0` is `True` in Python), so a NaN entry_price sailed straight past that "protection"
into a real division, writing a NaN profit_loss_pct for a real trade via the UPDATE.
Postgres numeric/float columns can genuinely store NaN, and entry_price here comes
directly from a raw SELECT with only a None check before this point.

Fixed by validating entry_price/stop_price/entry_qty for NaN/Infinity immediately after
the pre-existing None check, before any arithmetic uses them - matching this same
function's own recovered_exit_price guard a few lines further down.
"""

from collections.abc import Callable, Generator, Iterable
from contextlib import contextmanager
from datetime import date
from decimal import Decimal
from typing import Any
from unittest.mock import MagicMock, patch

from algo.orchestrator.phase9_reconciliation import _repair_missing_exit_prices


def _mock_db_context(
    corrupted_rows: Iterable[tuple[Any, ...]], price_row: tuple[Any, ...]
) -> tuple[Callable[..., Any], MagicMock]:
    """DatabaseContext("read") returns the corrupted-trades list; DatabaseContext("write")
    returns a cursor whose fetchone() answers the price_daily lookup and whose execute()
    calls (including any UPDATE) are all recorded on the same mock cursor."""
    write_cur = MagicMock()
    write_cur.fetchone.return_value = price_row
    write_cur.rowcount = 1

    read_cur = MagicMock()
    read_cur.fetchall.return_value = corrupted_rows

    @contextmanager
    def factory(mode: str, *args: Any, **kwargs: Any) -> Generator[MagicMock, None, None]:
        if mode == "read":
            yield read_cur
        else:
            yield write_cur

    return factory, write_cur


class TestRepairMissingExitPricesNanGuard:
    def test_nan_entry_price_skips_repair_instead_of_writing_nan_pnl(self) -> None:
        """The core bug: a NaN entry_price must not reach the UPDATE with a NaN
        profit_loss_pct."""
        corrupted_row = (
            "TRD-1", "AAPL", float("nan"), date(2026, 8, 10), None, 90.0, 100,
        )  # trade_id, symbol, entry_price, exit_date, _, stop_price, entry_qty
        factory, write_cur = _mock_db_context([corrupted_row], price_row=(105.0,))

        log_calls = []
        with patch("algo.orchestrator.phase9_reconciliation.DatabaseContext", side_effect=factory):
            _repair_missing_exit_prices(lambda *a, **kw: log_calls.append((a, kw)))

        update_calls = [
            c for c in write_cur.execute.call_args_list if c.args and "UPDATE algo_trades" in c.args[0]
        ]
        assert update_calls == [], (
            f"Expected the NaN entry_price to skip the repair entirely, but found an UPDATE call: {update_calls}"
        )

    def test_infinite_stop_price_skips_repair(self) -> None:
        corrupted_row = ("TRD-2", "MSFT", 100.0, date(2026, 8, 10), None, float("inf"), 50)
        factory, write_cur = _mock_db_context([corrupted_row], price_row=(110.0,))

        with patch("algo.orchestrator.phase9_reconciliation.DatabaseContext", side_effect=factory):
            _repair_missing_exit_prices(lambda *a, **kw: None)

        update_calls = [
            c for c in write_cur.execute.call_args_list if c.args and "UPDATE algo_trades" in c.args[0]
        ]
        assert update_calls == []

    def test_normal_finite_values_still_repair_correctly(self) -> None:
        """Sanity check: the fix must not accidentally reject legitimate repairs."""
        corrupted_row = ("TRD-3", "GOOG", 100.0, date(2026, 8, 10), None, 90.0, 10)
        factory, write_cur = _mock_db_context([corrupted_row], price_row=(105.0,))

        log_calls = []
        with patch("algo.orchestrator.phase9_reconciliation.DatabaseContext", side_effect=factory):
            _repair_missing_exit_prices(lambda *a, **kw: log_calls.append((a, kw)))

        update_calls = [
            c for c in write_cur.execute.call_args_list if c.args and "UPDATE algo_trades" in c.args[0]
        ]
        assert len(update_calls) == 1
        params = update_calls[0].args[1]
        exit_price, pnl_dollars, pnl_pct, r_multiple = params[0], params[1], params[2], params[3]
        assert exit_price == Decimal("105.0")
        assert pnl_dollars == 50.0  # (105-100) * 10
        assert pnl_pct == 5.0  # (5/100)*100
        assert r_multiple == 0.5  # 5 / (100-90)
