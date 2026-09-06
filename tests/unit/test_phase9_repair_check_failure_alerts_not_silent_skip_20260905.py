"""Regression test: a transient exception while verifying a position's stop-loss protection
must surface as "unrepairable" (which the caller alerts loudly on), not a silent "skipped"
(which the caller treats identically to a benign no-trade-id/paper-mode skip - just `continue`,
no alert at all).

BUG FOUND 2026-09-05 (real-money-readiness audit): both `is_order_still_live` (verifying a
prior repair's standalone stop) and `check_stop_loss_leg_live` (verifying the original bracket
leg) had their exception handlers return "skipped" instead of "unrepairable". A persistently
failing verification call for one symbol's order could recur every single cycle, forever,
with nothing beyond a `logger.warning` - never reaching a human. Since "unrepairable" is
already the exact code path the caller (phase9_reconciliation.py's
_verify_open_position_stop_loss_protection_step) alerts on for a confirmed-missing stop, a
false-positive alert here (position may actually still be protected) is far safer than a
silent miss on the position this check exists to protect.
"""

from unittest.mock import MagicMock

from algo.orchestrator.phase9_stop_loss_repair import check_and_repair_one_position


def test_is_order_still_live_exception_returns_unrepairable_not_skipped():
    order_mgr = MagicMock()
    order_mgr.is_order_still_live.side_effect = RuntimeError("Alpaca 500")

    outcome = check_and_repair_one_position(
        order_mgr,
        pos_id="pos-1",
        symbol="TESTSYM",
        trade_ids_arr=["trade-1"],
        quantity=10.0,
        current_stop_price=95.0,
        standalone_stop_order_id="prior-repair-order-1",
    )

    assert outcome == "unrepairable"


def test_check_stop_loss_leg_live_exception_returns_unrepairable_not_skipped(monkeypatch):
    order_mgr = MagicMock()
    order_mgr.check_stop_loss_leg_live.side_effect = RuntimeError("Alpaca timeout")

    fake_cursor = MagicMock()
    fake_cursor.fetchone.return_value = ("alpaca-order-1",)
    fake_ctx = MagicMock()
    fake_ctx.__enter__.return_value = fake_cursor
    fake_ctx.__exit__.return_value = False
    monkeypatch.setattr(
        "algo.orchestrator.phase9_stop_loss_repair.DatabaseContext",
        MagicMock(return_value=fake_ctx),
    )

    outcome = check_and_repair_one_position(
        order_mgr,
        pos_id="pos-2",
        symbol="TESTSYM2",
        trade_ids_arr=["trade-2"],
        quantity=10.0,
        current_stop_price=95.0,
        standalone_stop_order_id=None,
    )

    assert outcome == "unrepairable"
