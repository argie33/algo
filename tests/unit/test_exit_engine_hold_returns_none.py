#!/usr/bin/env python3
"""Regression test for the 2026-07-27 fix: _evaluate_position returned a truthy "hold"
dict ({"stage": "hold", "fraction": 0.0}, no "new_stop" key) whenever no exit strategy
triggered - which is the single most common outcome for a healthy, currently-holding
position. check_and_execute_exits' `if not exit_signal:` guard treats any non-empty
dict as an actionable signal, so this fell through into the stop-raise-only branch
downstream (fraction == 0 requires new_stop) and raised
"[EXIT_ENGINE] {symbol}: Stop-raise-only (fraction=0) requires new_stop price."

Live-reproduced 2026-07-27: a single run crashed this way for 7/7 open positions, every
one of them simply holding with no exit condition currently met.

_evaluate_position must return None (falsy) when there's nothing to do - exactly what the
caller's guard already checks for.
"""

from datetime import date
from decimal import Decimal
from unittest.mock import MagicMock, patch

from algo.trading.exit_engine import ExitEngine


def _engine(config):
    with patch("algo.trading.exit_engine.TradeExecutor"):
        return ExitEngine(config)


def _mock_config():
    return {
        "min_hold_days": 1,
        "max_hold_days": 60,
        "eight_week_rule_threshold_pct": 20.0,
        "eight_week_rule_window_days": 21,
        "exit_on_distribution_day": False,
        "max_distribution_days": 3,
        "move_be_at_r": 1.0,
        "chandelier_atr_mult": 3.0,
        "use_chandelier_trail": False,
        "exit_on_td_sequential": False,
        "exit_on_rs_line_break_50dma": False,
        "require_target_pullback": True,
        "execution_mode": "paper",
        "alpaca_paper_trading": True,
    }


def test_no_exit_condition_met_returns_none_not_a_hold_dict():
    """A position with no exit condition currently triggered (the common, everyday case)
    must return None, not a truthy dict that the caller misreads as actionable.

    ExitStrategyChain is mocked to a non-triggered signal (the real chain instantiates a
    fresh ExitEngine per strategy internally, which pulls in full TradeExecutor/
    TradeValidator config validation unrelated to what's under test here) - this isolates
    exactly the return-value contract this fix is about.
    """
    from algo.trading.exit_strategies import ExitSignal

    engine = _engine(_mock_config())

    with patch("algo.trading.exit_strategies.ExitStrategyChain") as mock_chain_cls:
        mock_chain_cls.return_value.evaluate.return_value = ExitSignal(
            triggered=False, stage="hold", reason="", fraction=0.0
        )
        decision = engine._evaluate_position(
            cur=None,
            symbol="HEALTHY",
            current_date=date(2026, 7, 27),
            cur_price=Decimal("101.00"),  # above stop, below t1 - nothing should trigger
            prev_close=Decimal("100.50"),
            entry_price=Decimal("100.00"),
            active_stop=Decimal("90.00"),
            init_stop=Decimal("90.00"),
            t1_price=Decimal("115.00"),
            t2_price=Decimal("130.00"),
            t3_price=Decimal("140.00"),
            target_hits=0,
            days_held=5,  # past min_hold_days, so the min-hold gate isn't what's being tested
            dist_days_today=0,
        )

    assert decision is None


def test_min_hold_days_gate_also_returns_none():
    """The min_hold_days gate (entry-day/near-entry hold) is a separate early-return with
    the exact same bug shape - must also return None, not a truthy 'hold' dict."""
    engine = _engine(_mock_config())

    decision = engine._evaluate_position(
        cur=None,
        symbol="TOONEW",
        current_date=date(2026, 7, 27),
        cur_price=Decimal("101.00"),
        prev_close=Decimal("100.50"),
        entry_price=Decimal("100.00"),
        active_stop=Decimal("90.00"),
        init_stop=Decimal("90.00"),
        t1_price=Decimal("115.00"),
        t2_price=Decimal("130.00"),
        t3_price=Decimal("140.00"),
        target_hits=0,
        days_held=0,
        dist_days_today=0,
    )

    assert decision is None


def test_check_and_execute_exits_does_not_crash_on_a_holding_position():
    """End-to-end: a single open position with nothing triggered must be processed as a
    clean hold (exits_executed=0, stop_raises_executed=0, trade_errors=0), not raise."""
    trade_row = (
        "TRD-1",  # trade_id
        "HEALTHY",  # symbol
        100.0,  # entry_price
        90.0,  # stop_loss_price
        115.0,
        130.0,
        140.0,  # t1/t2/t3 price
        date(2026, 7, 20),  # trade_date (well past min_hold_days)
        "POS-1",  # position_id
        10,  # quantity
        0,  # target_levels_hit
        90.0,  # current_stop_price
        None,
        None,
        None,  # t1/t2/t3 hit times
        None,  # last_partial_exit_date
        None,  # partial_exits_log
    )

    mock_cur = MagicMock()
    mock_cur.fetchall.return_value = [trade_row]
    mock_cur.fetchone.return_value = ("open", 10, 90.0)

    mock_ctx = MagicMock()
    mock_ctx.__enter__.return_value = mock_cur
    mock_ctx.__exit__.return_value = False

    with patch("algo.trading.exit_engine.TradeExecutor"):
        engine = ExitEngine(_mock_config())

        with (
            patch("algo.trading.exit_engine.DatabaseContext", return_value=mock_ctx),
            patch.object(engine, "_fetch_market_dist_days", return_value=set()),
            patch.object(engine, "_fetch_recent_prices", return_value=(101.0, 100.5)),
            # Isolates the caller-side contract under test (a None return from
            # _evaluate_position must be a clean no-op, not an error) from the real
            # strategy chain's own config dependencies, already covered separately above.
            patch.object(engine, "_evaluate_position", return_value=None),
        ):
            exits_executed, stop_raises_executed, trade_errors, #!/usr/bin/env python3
"""Regression test for the 2026-07-27 fix: _evaluate_position returned a truthy "hold"
dict ({"stage": "hold", "fraction": 0.0}, no "new_stop" key) whenever no exit strategy
triggered - which is the single most common outcome for a healthy, currently-holding
position. check_and_execute_exits' `if not exit_signal:` guard treats any non-empty
dict as an actionable signal, so this fell through into the stop-raise-only branch
downstream (fraction == 0 requires new_stop) and raised
"[EXIT_ENGINE] {symbol}: Stop-raise-only (fraction=0) requires new_stop price."

Live-reproduced 2026-07-27: a single run crashed this way for 7/7 open positions, every
one of them simply holding with no exit condition currently met.

_evaluate_position must return None (falsy) when there's nothing to do - exactly what the
caller's guard already checks for.
"""

from datetime import date
from decimal import Decimal
from unittest.mock import MagicMock, patch

from algo.trading.exit_engine import ExitEngine


def _engine(config):
    with patch("algo.trading.exit_engine.TradeExecutor"):
        return ExitEngine(config)


def _mock_config():
    return {
        "min_hold_days": 1,
        "max_hold_days": 60,
        "eight_week_rule_threshold_pct": 20.0,
        "eight_week_rule_window_days": 21,
        "exit_on_distribution_day": False,
        "max_distribution_days": 3,
        "move_be_at_r": 1.0,
        "chandelier_atr_mult": 3.0,
        "use_chandelier_trail": False,
        "exit_on_td_sequential": False,
        "exit_on_rs_line_break_50dma": False,
        "require_target_pullback": True,
        "execution_mode": "paper",
        "alpaca_paper_trading": True,
    }


def test_no_exit_condition_met_returns_none_not_a_hold_dict():
    """A position with no exit condition currently triggered (the common, everyday case)
    must return None, not a truthy dict that the caller misreads as actionable.

    ExitStrategyChain is mocked to a non-triggered signal (the real chain instantiates a
    fresh ExitEngine per strategy internally, which pulls in full TradeExecutor/
    TradeValidator config validation unrelated to what's under test here) - this isolates
    exactly the return-value contract this fix is about.
    """
    from algo.trading.exit_strategies import ExitSignal

    engine = _engine(_mock_config())

    with patch("algo.trading.exit_strategies.ExitStrategyChain") as mock_chain_cls:
        mock_chain_cls.return_value.evaluate.return_value = ExitSignal(
            triggered=False, stage="hold", reason="", fraction=0.0
        )
        decision = engine._evaluate_position(
            cur=None,
            symbol="HEALTHY",
            current_date=date(2026, 7, 27),
            cur_price=Decimal("101.00"),  # above stop, below t1 - nothing should trigger
            prev_close=Decimal("100.50"),
            entry_price=Decimal("100.00"),
            active_stop=Decimal("90.00"),
            init_stop=Decimal("90.00"),
            t1_price=Decimal("115.00"),
            t2_price=Decimal("130.00"),
            t3_price=Decimal("140.00"),
            target_hits=0,
            days_held=5,  # past min_hold_days, so the min-hold gate isn't what's being tested
            dist_days_today=0,
        )

    assert decision is None


def test_min_hold_days_gate_also_returns_none():
    """The min_hold_days gate (entry-day/near-entry hold) is a separate early-return with
    the exact same bug shape - must also return None, not a truthy 'hold' dict."""
    engine = _engine(_mock_config())

    decision = engine._evaluate_position(
        cur=None,
        symbol="TOONEW",
        current_date=date(2026, 7, 27),
        cur_price=Decimal("101.00"),
        prev_close=Decimal("100.50"),
        entry_price=Decimal("100.00"),
        active_stop=Decimal("90.00"),
        init_stop=Decimal("90.00"),
        t1_price=Decimal("115.00"),
        t2_price=Decimal("130.00"),
        t3_price=Decimal("140.00"),
        target_hits=0,
        days_held=0,
        dist_days_today=0,
    )

    assert decision is None


def test_check_and_execute_exits_does_not_crash_on_a_holding_position():
    """End-to-end: a single open position with nothing triggered must be processed as a
    clean hold (exits_executed=0, stop_raises_executed=0, trade_errors=0), not raise."""
    trade_row = (
        "TRD-1",  # trade_id
        "HEALTHY",  # symbol
        100.0,  # entry_price
        90.0,  # stop_loss_price
        115.0,
        130.0,
        140.0,  # t1/t2/t3 price
        date(2026, 7, 20),  # trade_date (well past min_hold_days)
        "POS-1",  # position_id
        10,  # quantity
        0,  # target_levels_hit
        90.0,  # current_stop_price
        None,
        None,
        None,  # t1/t2/t3 hit times
        None,  # last_partial_exit_date
        None,  # partial_exits_log
    )

    mock_cur = MagicMock()
    mock_cur.fetchall.return_value = [trade_row]
    mock_cur.fetchone.return_value = ("open", 10, 90.0)

    mock_ctx = MagicMock()
    mock_ctx.__enter__.return_value = mock_cur
    mock_ctx.__exit__.return_value = False

    with patch("algo.trading.exit_engine.TradeExecutor"):
        engine = ExitEngine(_mock_config())

        with (
            patch("algo.trading.exit_engine.DatabaseContext", return_value=mock_ctx),
            patch.object(engine, "_fetch_market_dist_days", return_value=set()),
            patch.object(engine, "_fetch_recent_prices", return_value=(101.0, 100.5)),
            # Isolates the caller-side contract under test (a None return from
            # _evaluate_position must be a clean no-op, not an error) from the real
            # strategy chain's own config dependencies, already covered separately above.
            patch.object(engine, "_evaluate_position", return_value=None),
        ):
            exits_executed, stop_raises_executed, trade_errors = engine.check_and_execute_exits(date(2026, 7, 27))

    assert (exits_executed, stop_raises_executed, trade_errors) == (0, 0, 0)
forced_closes_no_price = engine.check_and_execute_exits(date(2026, 7, 27))

    assert (exits_executed, stop_raises_executed, trade_errors) == (0, 0, 0)

