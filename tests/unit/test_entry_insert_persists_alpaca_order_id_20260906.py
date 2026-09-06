#!/usr/bin/env python3
"""REAL-MONEY-READINESS FIX regression (2026-09-06): TradeInsertionRequest.alpaca_order_id
was populated on every request (the real submitted/verified Alpaca order id, threaded
through from executor_entry_handler.py's own _record_entry_phase) but the INSERT INTO
algo_trades column list never included it - live-confirmed 100% of algo_trades rows had
alpaca_order_id NULL.

This wasn't cosmetic: phase6_exit_execution.py's trailing-stop-raise path does
`SELECT alpaca_order_id FROM algo_trades WHERE trade_id = %s` and passes the result straight
to order_manager.sync_bracket_stop_loss(). With alpaca_order_id always NULL,
sync_bracket_stop_loss took its "no live Alpaca order to sync (paper/local mode)" branch and
returned success=True/synced=False UNCONDITIONALLY - even in live "auto" mode. Every
trailing-stop raise updated our own DB's belief (algo_positions.current_stop_price) while
NEVER pushing the tightened price to the broker's actual resting bracket stop-loss leg. The
2026-08-24 "fail closed on broker desync" fix for this exact gap could never engage, because
the id it depended on was never persisted in the first place.

This test asserts the INSERT actually carries alpaca_order_id through, for both a live order
id and the paper-mode empty-string case (which must be stored as NULL, not "").
"""

from datetime import date
from decimal import Decimal
from unittest.mock import MagicMock

from algo.trading.executor_entry_handler import EntryHandler


def _make_trade_context():
    ctx = MagicMock()
    ctx.signal_date = date(2026, 9, 6)
    ctx.entry_date = date(2026, 9, 6)
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


def _fetchone_side_effect_factory(cur: MagicMock):
    def _fetchone_side_effect():
        last_sql = str(cur.execute.call_args.args[0]) if cur.execute.call_args else ""
        if "exit_price" in last_sql and "algo_trades" in last_sql:
            return (None,)
        return None

    return _fetchone_side_effect


def _run_record_entry_phase(alpaca_order_id: str, order_status: str) -> tuple[str, tuple]:
    handler_context = MagicMock()
    handler_context.execution_mode = "paper"
    handler_context._get_portfolio_value.return_value = Decimal("100000")

    handler = EntryHandler(handler_context)
    cur = MagicMock()
    cur.fetchone.side_effect = _fetchone_side_effect_factory(cur)

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
        order_status=order_status,
        alpaca_order_id=alpaca_order_id,
        context=_make_trade_context(),
        rejection_reason=None,
        idempotency_key="idem-test-1",
        order_send_time=None,
    )

    trade_insert_calls = [c for c in cur.execute.call_args_list if "INSERT INTO algo_trades" in str(c.args[0])]
    assert trade_insert_calls, "expected an INSERT INTO algo_trades"
    sql_text, params = trade_insert_calls[0].args
    return sql_text, params


def test_live_alpaca_order_id_is_persisted_in_the_insert():
    sql_text, params = _run_record_entry_phase(alpaca_order_id="alpaca-order-abc123", order_status="filled")

    assert "alpaca_order_id" in sql_text, "INSERT column list must include alpaca_order_id"
    assert "alpaca_order_id = EXCLUDED.alpaca_order_id" in sql_text, (
        "ON CONFLICT UPDATE must also refresh alpaca_order_id on a retry"
    )
    assert "alpaca-order-abc123" in params, f"expected the real order id among INSERT params, got {params!r}"


def test_paper_mode_empty_string_order_id_is_stored_as_null_not_empty_string():
    _sql_text, params = _run_record_entry_phase(alpaca_order_id="", order_status="paper_pending")

    assert "" not in params, "an empty-string alpaca_order_id must be normalized to NULL, not stored literally"
