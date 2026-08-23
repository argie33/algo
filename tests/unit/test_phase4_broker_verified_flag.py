"""Regression test for migration 1216 (algo_reconciliation_log.broker_verified).

check_partial_fills() returns {"mismatches": 0, "no_broker": True} unconditionally in
paper-trading mode (no broker to check against) - match_percentage then comes out to a
vacuous 100% (0 mismatches / N positions), indistinguishable in the stored row from a
genuine broker-verified 100% match. phase4_reconciliation.py must persist broker_verified
so a reader of algo_reconciliation_log (or /api/algo/health's
phase_4_broker_reconciliation) can tell the difference.
"""

from datetime import date
from unittest.mock import MagicMock, patch

from algo.orchestrator.phase4_reconciliation import run


def _run_and_capture_insert(partial_fill_result):
    mock_config = MagicMock()
    mock_config.get.return_value = "auto"

    mock_recon = MagicMock()
    mock_recon.run_daily_reconciliation.return_value = {
        "success": True,
        "reason": "ok",
        "positions": 13,
    }
    mock_recon.check_partial_fills.return_value = partial_fill_result

    mock_cur = MagicMock()
    mock_ctx = MagicMock()
    mock_ctx.__enter__.return_value = mock_cur
    mock_ctx.__exit__.return_value = False

    with (
        patch("algo.infrastructure.reconciliation.DailyReconciliation", return_value=mock_recon),
        patch("utils.db.DatabaseContext", return_value=mock_ctx),
    ):
        run(
            config=mock_config,
            run_date=date(2026, 8, 22),
            dry_run=False,
            alerts=MagicMock(),
            verbose=False,
            log_phase_result_fn=lambda *a, **k: None,
        )

    insert_call = next(c for c in mock_cur.execute.call_args_list if "INSERT INTO algo_reconciliation_log" in c.args[0])
    return insert_call.args[1]  # bound params tuple


class TestPhase4BrokerVerifiedFlag:
    def test_no_broker_paper_mode_persists_unverified(self):
        """Paper mode (no_broker=True): mismatches is hardcoded 0, so match_pct is vacuous -
        broker_verified must be False, not True."""
        params = _run_and_capture_insert({"mismatches": 0, "no_broker": True})

        # (run_date, match_pct, positions_count, broker_verified)
        assert params[3] is False

    def test_real_broker_check_persists_verified(self):
        """A real check (broker responded, whether or not it found mismatches) must be
        recorded as broker_verified=True."""
        params = _run_and_capture_insert({"mismatches": 0, "no_broker": False})

        assert params[3] is True

    def test_real_broker_check_with_no_orders_persists_verified(self):
        """check_partial_fills' "no closed orders to check" case still means the broker was
        actually reached - not the same as no_broker=True."""
        params = _run_and_capture_insert({"mismatches": 0, "no_orders_available": True})

        assert params[3] is True
