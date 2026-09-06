#!/usr/bin/env python3
"""Regression test for the 2026-07-27 stock-split price-rescale fix in position_monitor.py.

_apply_split_adjustment() used to update ONLY algo_positions.quantity and
current_stop_price when a stock split was detected. But the exit engine's R-multiple
math and every T1/T2/T3 profit-target comparison read entry_price/stop_loss_price/
target_N_price from algo_trades (joined per position in _evaluate_position), not
algo_positions - and those were never rescaled. After a real split, cur_price reflected
the new post-split price scale while entry_price/targets stayed at the old pre-split
scale, silently corrupting R-multiple and profit-target exit logic for the rest of the
position's life. Fixed by rescaling every price-scale column on both algo_trades (the
table the exit engine actually reads) and algo_positions (cache/display columns).
"""

import re
from unittest.mock import MagicMock, patch

from algo.monitoring.position_monitor import PositionMonitor


def _make_monitor() -> PositionMonitor:
    return PositionMonitor(config={})


class TestSplitAdjustmentRescalesTradePrices:
    def test_algo_trades_price_columns_rescaled_for_all_trade_ids(self) -> None:
        """A 2:1 split (100 -> 200 shares) must rescale algo_trades entry/stop/target
        prices for every trade_id in the position's trade_ids_arr, not just the
        position-level current_stop_price."""
        monitor = _make_monitor()
        cur = MagicMock()
        adjustments: list = []

        monitor._apply_split_adjustment(
            cur,
            pos_id=42,
            symbol="TEST",
            db_qty=100,
            db_stop=90.0,
            alpaca_qty=200,
            trade_ids_arr=[501, 502],
            adjustments=adjustments,
        )

        trades_calls = [c for c in cur.execute.call_args_list if "UPDATE algo_trades" in c.args[0]]
        assert len(trades_calls) == 1, "must issue exactly one algo_trades UPDATE for the split"

        sql, params = trades_calls[0].args
        assert "entry_price" in sql
        assert "stop_loss_price" in sql
        assert "target_1_price" in sql
        assert "target_2_price" in sql
        assert "target_3_price" in sql
        assert "trade_id = ANY(%s)" in sql
        # ratio params (5x) + the trade_ids_arr list itself
        assert params[-1] == [501, 502]
        for ratio_param in params[:-1]:
            assert ratio_param == 2.0

    def test_algo_positions_price_columns_rescaled_not_just_stop(self) -> None:
        """The algo_positions UPDATE must also rescale entry_price/avg_entry_price/
        stop_loss_price/current_stop_price/target_N_price/initial_risk_per_share, not just
        quantity/current_stop_price (the pre-fix behavior)."""
        monitor = _make_monitor()
        cur = MagicMock()
        adjustments: list = []

        monitor._apply_split_adjustment(
            cur,
            pos_id=42,
            symbol="TEST",
            db_qty=100,
            db_stop=90.0,
            alpaca_qty=200,
            trade_ids_arr=[501],
            adjustments=adjustments,
        )

        positions_calls = [c for c in cur.execute.call_args_list if "UPDATE algo_positions" in c.args[0]]
        assert len(positions_calls) == 1
        sql, params = positions_calls[0].args
        for col in (
            "entry_price",
            "avg_entry_price",
            "stop_loss_price",
            "current_stop_price",
            "target_1_price",
            "target_2_price",
            "target_3_price",
            "initial_risk_per_share",
        ):
            assert col in sql, f"{col} must be rescaled in the algo_positions UPDATE"

    def test_no_column_assigned_twice_in_positions_update(self) -> None:
        """Regression guard for the 2026-08-25 bug: `stop_loss_price` was assigned TWICE in
        the same UPDATE ... SET clause (once to a Python-computed value, once via
        ROUND(stop_loss_price / ratio, 2)) - PostgreSQL categorically rejects this
        ("multiple assignments to same column"), live-confirmed against a real connection.
        Every real stock-split adjustment crashed instead of applying. MagicMock's cursor
        never validates SQL syntax, so this must be checked structurally: every column name
        immediately followed by `=` in the SET clause must appear exactly once."""
        monitor = _make_monitor()
        cur = MagicMock()
        adjustments: list = []

        monitor._apply_split_adjustment(
            cur,
            pos_id=42,
            symbol="TEST",
            db_qty=100,
            db_stop=90.0,
            alpaca_qty=200,
            trade_ids_arr=[501],
            adjustments=adjustments,
        )

        positions_calls = [c for c in cur.execute.call_args_list if "UPDATE algo_positions" in c.args[0]]
        sql = positions_calls[0].args[0]
        set_clause = sql.split(" SET ", 1)[1].split(" WHERE ", 1)[0]
        # Each assignment is formatted one-per-line (`col = ...,`), so match column names at
        # the start of a line rather than naively splitting on every comma - `ROUND(x / %s,
        # 2)` contains a comma of its own that isn't a column separator.
        assigned_columns = re.findall(r"^\s*(\w+)\s*=", set_clause, flags=re.MULTILINE)
        duplicates = {col for col in assigned_columns if assigned_columns.count(col) > 1}
        assert not duplicates, f"column(s) assigned more than once in the same UPDATE: {duplicates}"

    def test_no_trade_ids_escalates_to_critical_alert_and_audit_severity(self) -> None:
        """If trade_ids_arr is empty/NULL, the stale-price gap must be surfaced loudly -
        a CRITICAL alert (2026-09-06 adversarial-review fix: this used to be only a
        logger.warning, inconsistent with every other consumer of an empty/NULL
        trade_ids_arr in this codebase, which all treat it as a real halt-worthy
        condition) and a CRITICAL algo_audit_log severity, not WARN."""
        monitor = _make_monitor()
        cur = MagicMock()
        adjustments: list = []

        with patch("algo.reporting.notify") as mock_notify:
            monitor._apply_split_adjustment(
                cur,
                pos_id=42,
                symbol="TEST",
                db_qty=100,
                db_stop=90.0,
                alpaca_qty=200,
                trade_ids_arr=None,
                adjustments=adjustments,
            )

        trades_calls = [c for c in cur.execute.call_args_list if "UPDATE algo_trades" in c.args[0]]
        assert len(trades_calls) == 0

        mock_notify.assert_called_once()
        assert mock_notify.call_args.args[0] == "CRITICAL"

        audit_calls = [c for c in cur.execute.call_args_list if "INSERT INTO algo_audit_log" in c.args[0]]
        assert len(audit_calls) == 1
        audit_params = audit_calls[0].args[1]
        assert audit_params[-1] == "CRITICAL"

    def test_trade_ids_present_uses_warn_audit_severity_no_alert(self) -> None:
        """The normal (non-orphaned) split path must stay a routine WARN audit entry with
        no CRITICAL alert - escalation is specifically for the empty/NULL trade_ids_arr
        case, not every split."""
        monitor = _make_monitor()
        cur = MagicMock()
        adjustments: list = []

        with patch("algo.reporting.notify") as mock_notify:
            monitor._apply_split_adjustment(
                cur,
                pos_id=42,
                symbol="TEST",
                db_qty=100,
                db_stop=90.0,
                alpaca_qty=200,
                trade_ids_arr=[501],
                adjustments=adjustments,
            )

        mock_notify.assert_not_called()
        audit_calls = [c for c in cur.execute.call_args_list if "INSERT INTO algo_audit_log" in c.args[0]]
        assert len(audit_calls) == 1
        audit_params = audit_calls[0].args[1]
        assert audit_params[-1] == "WARN"
