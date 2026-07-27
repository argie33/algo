#!/usr/bin/env python3
"""Regression test: a position created for a "paper_pending" trade (paper mode, Alpaca
unavailable at submission time - see executor_entry_handler.py's execute_entry) must be
recorded with algo_positions.status='open', not the undeclared literal "paper_open".

"paper_open" isn't in the PositionStatus enum at all, and almost every real position query
in this codebase (exit_engine.py's core exit-candidate query, circuit_breaker.py's
_check_total_risk/_check_win_rate_floor/_check_sector_drawdown/_check_sector_concentration,
position_monitor.py) checks against PositionStatus.OPEN.value ("open") specifically. A
position stuck at "paper_open" would be invisible to every automated stop-loss/target exit
check and every risk-limit halt check - the same "no bypasses" bug class as this session's
TradeStatus.all_open() fixes, just on the PositionStatus side.
"""

from datetime import date
from decimal import Decimal
from unittest.mock import MagicMock

from algo.trading.executor_entry_handler import EntryHandler
from utils.trading import PositionStatus


def _make_trade_context():
    ctx = MagicMock()
    ctx.signal_date = date(2026, 7, 24)
    ctx.entry_date = date(2026, 7, 24)
    ctx.sqs = 75
    ctx.signals.trend_score = 80
    ctx.signals.base_type = "flat_base"
    ctx.signals.base_quality = "A"
    ctx.signals.stage_phase = "mid"
    ctx.signals.rs_percentile = 90
    ctx.signals.advanced_components = None
    ctx.market.sector = "Technology"
    ctx.market.industry = "Software"
    ctx.market.market_exposure_at_entry = 50.0
    ctx.market.exposure_tier_at_entry = "full"
    ctx.execution.stop_method = "atr"
    ctx.execution.stop_reasoning = "atr_based"
    return ctx


def test_paper_pending_trade_creates_position_with_open_status_not_paper_open():
    handler_context = MagicMock()
    handler_context.execution_mode = "paper"
    handler_context._get_portfolio_value.return_value = Decimal("100000")

    handler = EntryHandler(handler_context)
    cur = MagicMock()

    handler._record_entry_phase(
        cur=cur,
        trade_id="TRD-TEST1",
        symbol="TEST",
        shares=Decimal("10"),
        entry_price=Decimal("100.00"),
        executed_price=Decimal("100.00"),
        stop_loss_price=Decimal("90.00"),
        target_1_price=Decimal("110.00"),
        target_2_price=None,
        target_3_price=None,
        order_status="paper_pending",
        alpaca_order_id="",
        context=_make_trade_context(),
        rejection_reason="Paper mode - Alpaca unavailable: connection timeout",
        idempotency_key="idem-test-1",
        order_send_time=None,
    )

    position_insert_calls = [
        c for c in cur.execute.call_args_list if "INSERT INTO algo_positions" in str(c.args[0])
    ]
    assert position_insert_calls, "expected a position to be created for a paper_pending trade"
    params = position_insert_calls[0].args[1]
    # position_status is the 8th positional value in the INSERT's VALUES tuple
    # (position_id, symbol, quantity, avg_entry_price, entry_price, current_price,
    #  position_value, status, ...)
    assert PositionStatus.OPEN.value in params, f"expected 'open' status among INSERT params, got {params!r}"
    assert "paper_open" not in params, "must not use the undeclared 'paper_open' status"
