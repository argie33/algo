"""Regression test for scripts/record_capital_flow.py, the capital-flow recording tool.

BUILT 2026-08-10: this script was referenced by name in comments across
algo/risk/circuit_breaker.py, algo/infrastructure/reconciliation.py, and
algo/trading/position_sizer.py as the way to record a deposit/withdrawal into
algo_capital_flows, but never actually existed - migration 1134 created the table and a
one-off backfill for 3 historical withdrawals, leaving no supported tool for the next one.
Without it, an unrecorded capital flow makes the drawdown circuit breaker misinterpret
account-size changes as trading performance (the exact incident migration 1134 itself
documents: 8+ months of permanent halt deadlock from an unrecorded withdrawal).

Live-verified separately (not just this mocked test): --list against the real local DB,
then a real $0.01 test deposit recorded and its exact effect on adjusted_equity confirmed
(shifted down by precisely $0.01 for the flow date only, prior dates unchanged - correctly
scoped by flow_date <= snapshot_date), then deleted and the adjusted series recomputed back
to its exact original values, confirmed via a fresh connection.
"""

from datetime import date
from decimal import Decimal
from unittest.mock import MagicMock, patch

import pytest

import scripts.record_capital_flow as record_capital_flow


class TestRecordCapitalFlowScript:
    def test_positive_amount_derives_deposit_type(self):
        mock_cur = MagicMock()
        mock_cur.fetchone.return_value = (42,)
        mock_cur.rowcount = 100
        mock_ctx = MagicMock()
        mock_ctx.__enter__.return_value = mock_cur
        mock_ctx.__exit__.return_value = False

        with patch.object(record_capital_flow, "DatabaseContext", return_value=mock_ctx):
            new_id = record_capital_flow.record_flow(date(2026, 8, 10), Decimal("10000"), "manual", "funding")

        assert new_id == 42
        insert_call = mock_cur.execute.call_args_list[0]
        assert "INSERT INTO algo_capital_flows" in insert_call.args[0]
        assert insert_call.args[1] == (date(2026, 8, 10), Decimal("10000"), "deposit", "manual", "funding")

    def test_negative_amount_derives_withdrawal_type(self):
        mock_cur = MagicMock()
        mock_cur.fetchone.return_value = (43,)
        mock_cur.rowcount = 100
        mock_ctx = MagicMock()
        mock_ctx.__enter__.return_value = mock_cur
        mock_ctx.__exit__.return_value = False

        with patch.object(record_capital_flow, "DatabaseContext", return_value=mock_ctx):
            record_capital_flow.record_flow(date(2026, 8, 10), Decimal("-5000"), "manual", "withdrawal to bank")

        insert_call = mock_cur.execute.call_args_list[0]
        assert insert_call.args[1] == (date(2026, 8, 10), Decimal("-5000"), "withdrawal", "manual", "withdrawal to bank")

    def test_recompute_query_runs_after_insert(self):
        """The core correctness property: recording a flow must also recompute the
        adjusted_equity/adjusted_running_peak/adjusted_drawdown_pct series, not just
        append a row - those columns are a cumulative-sum derived series, not independent
        per-row values."""
        mock_cur = MagicMock()
        mock_cur.fetchone.return_value = (1,)
        mock_cur.rowcount = 575
        mock_ctx = MagicMock()
        mock_ctx.__enter__.return_value = mock_cur
        mock_ctx.__exit__.return_value = False

        with patch.object(record_capital_flow, "DatabaseContext", return_value=mock_ctx):
            record_capital_flow.record_flow(date(2026, 8, 10), Decimal("1000"), "manual", None)

        assert mock_cur.execute.call_count == 2
        recompute_call = mock_cur.execute.call_args_list[1]
        assert "UPDATE algo_portfolio_snapshots" in recompute_call.args[0]
        assert "adjusted_equity" in recompute_call.args[0]
        assert "adjusted_running_peak" in recompute_call.args[0]
        assert "adjusted_drawdown_pct" in recompute_call.args[0]

    def test_zero_amount_rejected(self):
        with pytest.raises(ValueError, match="non-zero"):
            record_capital_flow.record_flow(date(2026, 8, 10), Decimal("0"), "manual", None)

    def test_future_date_rejected_by_main(self):
        import sys

        future = "2099-01-01"
        with patch.object(sys, "argv", ["record_capital_flow.py", "--amount", "100", "--date", future]):
            exit_code = record_capital_flow.main()

        assert exit_code == 1

    def test_invalid_amount_rejected_by_main(self):
        import sys

        with patch.object(sys, "argv", ["record_capital_flow.py", "--amount", "not-a-number"]):
            exit_code = record_capital_flow.main()

        assert exit_code == 1
