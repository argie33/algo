"""Regression test: Phase 8 must reject an entry candidate whose price is implausible
relative to the prior day's close, rather than sizing a real order off garbage data.

REAL-MONEY-READINESS FINDING (2026-09-06 audit): entry_price flows straight from
price_daily.close into position sizing with no cross-check against the prior close.
Phase 1 only checks table-level freshness/completeness, and data_patrol's
check_price_moves (algo/monitoring/data_patrol/checks/price_sanity.py) is a
disconnected diagnostic report never wired into any trading decision. A bad print,
stale cache, or decimal-shift error would pass both and flow straight into sizing.

Like test_phase8_min_entry_price_gate_wired_and_audited.py, the gate-wiring assertion
is a source-inspection test (run() has no full-mock harness), but _batch_fetch_prior_close
is a standalone, directly-testable function.
"""

import inspect
from datetime import date
from unittest.mock import MagicMock, patch

from algo.orchestrator import phase8_entry_execution as p8
from algo.orchestrator.validation_thresholds import MAX_PLAUSIBLE_ENTRY_PRICE_MOVE_PCT


def test_max_plausible_move_is_wide_not_a_volatility_filter() -> None:
    # Must stay wide enough to never reject a genuine outsized move (biotech trial
    # results, M&A, short squeezes) - this is a garbage-data filter, not a volatility cap.
    assert MAX_PLAUSIBLE_ENTRY_PRICE_MOVE_PCT >= 100.0


def test_batch_fetch_prior_close_empty_symbols_returns_empty_dict() -> None:
    assert p8._batch_fetch_prior_close([], date(2026, 9, 6)) == {}


def test_batch_fetch_prior_close_maps_symbol_to_second_most_recent_close() -> None:
    mock_cur = MagicMock()
    mock_cur.fetchall.return_value = [
        {"symbol": "AAPL", "close": 150.0},
        {"symbol": "MSFT", "close": 300.0},
    ]
    mock_ctx = MagicMock()
    mock_ctx.__enter__.return_value = mock_cur
    mock_ctx.__exit__.return_value = False

    with patch.object(p8, "DatabaseContext", return_value=mock_ctx):
        result = p8._batch_fetch_prior_close(["AAPL", "MSFT"], date(2026, 9, 6))

    assert result == {"AAPL": 150.0, "MSFT": 300.0}
    sql = mock_cur.execute.call_args.args[0]
    assert "rn = 2" in sql, "must select the SECOND most recent row (prior close), not the latest"


def test_batch_fetch_prior_close_skips_unresolvable_rows() -> None:
    mock_cur = MagicMock()
    mock_cur.fetchall.return_value = [{"symbol": "NEWCO", "close": None}]
    mock_ctx = MagicMock()
    mock_ctx.__enter__.return_value = mock_cur
    mock_ctx.__exit__.return_value = False

    with patch.object(p8, "DatabaseContext", return_value=mock_ctx):
        result = p8._batch_fetch_prior_close(["NEWCO"], date(2026, 9, 6))

    assert result == {}, "a symbol with no resolvable prior close must be absent, not mapped to None/0"


def test_price_plausibility_gate_is_wired_into_run_as_skip_not_raise() -> None:
    module_source = inspect.getsource(p8)
    gate_block = module_source.split("PRICE-PLAUSIBILITY GATE")[1].split("stop_loss = _calculate_dynamic_stop_loss")[0]
    assert "MAX_PLAUSIBLE_ENTRY_PRICE_MOVE_PCT" in gate_block
    assert "prior_close_by_symbol" in gate_block
    assert "continue" in gate_block, "must skip the one bad candidate, not raise/halt the rest of Phase 8"
    assert "raise " not in gate_block and "raise\n" not in gate_block, (
        "must not halt Phase 8 (comments may say 'not raise')"
    )
    assert "implausible_price_move" in gate_block
    assert "_log_signal_rejection" in gate_block, "rejection must be audited like every other business-rule skip"


def test_price_plausibility_gate_fails_open_when_no_prior_close_available() -> None:
    module_source = inspect.getsource(p8)
    gate_block = module_source.split("PRICE-PLAUSIBILITY GATE")[1].split("stop_loss = _calculate_dynamic_stop_loss")[0]
    # A symbol absent from prior_close_by_symbol (new listing, data gap) must not be
    # blocked - "cannot verify" must not be treated as "reject".
    assert "if prior_close is not None" in gate_block
