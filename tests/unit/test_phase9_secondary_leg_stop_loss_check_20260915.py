"""Regression test: pyramid legs beyond trade_ids_arr[0] get their own stop-loss liveness
check, instead of no check at all.

BUG FOUND 2026-09-15 (real-money-readiness audit, continuation of the 2026-09-08 fix that
scoped check_and_repair_one_position's math to trade_ids_arr[0]'s own leg): that fix's own
comment explicitly flagged that trade_ids_arr[1:] still had NO independent Phase 9 liveness
check at all - a missing stop-loss leg on a second (or later) pyramid leg would never be
detected by anything, every cycle, forever. check_secondary_legs_one_position closes the
detection gap (deliberately not auto-repair - algo_positions has only one
standalone_stop_order_id column, position-level, so there is nowhere to durably track a
second leg's own repair order without a schema change).
"""

from unittest.mock import MagicMock

from algo.orchestrator.phase9_stop_loss_repair import check_secondary_legs_one_position


def _patch_db(monkeypatch, rows_by_trade_id: dict[str, tuple]) -> None:
    def fake_db_context(*_args, **_kwargs):
        ctx = MagicMock()
        cursor = MagicMock()

        def execute(query, params=None):
            trade_id = params[0] if params else None
            cursor.fetchone.return_value = rows_by_trade_id.get(trade_id)

        cursor.execute.side_effect = execute
        ctx.__enter__.return_value = cursor
        ctx.__exit__.return_value = False
        return ctx

    monkeypatch.setattr(
        "algo.orchestrator.phase9_stop_loss_repair.DatabaseContext",
        fake_db_context,
    )


def test_single_leg_position_returns_no_gaps_without_any_check(monkeypatch):
    order_mgr = MagicMock()
    gaps = check_secondary_legs_one_position(order_mgr, pos_id="pos-1", symbol="AAA", trade_ids_arr=["trade-1"])
    assert gaps == []
    order_mgr.check_stop_loss_leg_live.assert_not_called()


def test_second_leg_missing_stop_flagged_as_unprotected(monkeypatch):
    _patch_db(monkeypatch, {"trade-2": ("alpaca-order-2",)})
    order_mgr = MagicMock()
    order_mgr.check_stop_loss_leg_live.return_value = {
        "checked": True,
        "has_live_stop_loss": False,
        "message": "no live stop-loss leg found",
    }

    gaps = check_secondary_legs_one_position(
        order_mgr, pos_id="pos-2", symbol="BBB", trade_ids_arr=["trade-1", "trade-2"]
    )

    assert gaps == ["trade-2"]
    order_mgr.check_stop_loss_leg_live.assert_called_once_with("alpaca-order-2")


def test_second_leg_with_live_stop_is_not_flagged(monkeypatch):
    _patch_db(monkeypatch, {"trade-2": ("alpaca-order-2",)})
    order_mgr = MagicMock()
    order_mgr.check_stop_loss_leg_live.return_value = {"checked": True, "has_live_stop_loss": True}

    gaps = check_secondary_legs_one_position(
        order_mgr, pos_id="pos-3", symbol="CCC", trade_ids_arr=["trade-1", "trade-2"]
    )

    assert gaps == []


def test_third_leg_exception_treated_as_unprotected_not_silently_skipped(monkeypatch):
    _patch_db(monkeypatch, {"trade-2": ("alpaca-order-2",), "trade-3": ("alpaca-order-3",)})
    order_mgr = MagicMock()
    order_mgr.check_stop_loss_leg_live.side_effect = RuntimeError("Alpaca 500")

    gaps = check_secondary_legs_one_position(
        order_mgr, pos_id="pos-4", symbol="DDD", trade_ids_arr=["trade-1", "trade-2", "trade-3"]
    )

    assert gaps == ["trade-2", "trade-3"]


def test_leg_with_no_resolvable_order_is_skipped_not_flagged(monkeypatch):
    _patch_db(monkeypatch, {"trade-2": None})
    order_mgr = MagicMock()

    gaps = check_secondary_legs_one_position(
        order_mgr, pos_id="pos-5", symbol="EEE", trade_ids_arr=["trade-1", "trade-2"]
    )

    assert gaps == []
    order_mgr.check_stop_loss_leg_live.assert_not_called()


def test_paper_mode_unchecked_result_is_not_flagged(monkeypatch):
    _patch_db(monkeypatch, {"trade-2": ("alpaca-order-2",)})
    order_mgr = MagicMock()
    order_mgr.check_stop_loss_leg_live.return_value = {"checked": False}

    gaps = check_secondary_legs_one_position(
        order_mgr, pos_id="pos-6", symbol="FFF", trade_ids_arr=["trade-1", "trade-2"]
    )

    assert gaps == []
