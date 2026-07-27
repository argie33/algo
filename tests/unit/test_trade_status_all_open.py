#!/usr/bin/env python3
"""TradeStatus.all_open() is the shared "is this trade still live" definition used by
exit_engine.py, position_monitor.py, exposure_policy.py, trade_validator.py,
phase8_entry_execution.py, pretrade_checks.py, and data_patrol/checks/alignment.py's
duplicate/exit/exposure/alignment queries. It previously omitted PENDING and
PAPER_PENDING, and several of those call sites hand-rolled their own incomplete
('open', 'pending') tuple instead of calling it at all - see the individual fixes in each
file. This pins the contract so a future edit can't silently narrow it again.
"""

from utils.trading import TradeStatus


def test_all_open_covers_every_status_a_real_order_can_be_recorded_with():
    """Every literal status string executor_entry_handler.py's _record_entry_phase can pass
    as order_status for a trade that is NOT yet terminal must be present."""
    open_statuses = set(TradeStatus.all_open())
    assert open_statuses == {"open", "filled", "partially_filled", "active", "pending", "paper_pending"}


def test_all_open_excludes_terminal_statuses():
    open_statuses = set(TradeStatus.all_open())
    for terminal in ("closed", "cancelled", "orphaned"):
        assert terminal not in open_statuses
