"""Regression test for the 2026-09-07 fix in scripts/local_loader_scheduler.py:
_run_data_patrol_and_report() runs DataPatrol automatically after a local "metrics" pipeline
run (where financial_statements/XBRL data loads) and reports the same pass/fail signal
production's Phase 1 DataPatrol gate (see algo/orchestrator/phase1_data_freshness.py's
_check_data_patrol_results, fixed the same session) would halt trading on - closing the gap
where a local reload gave no equivalent signal short of manually remembering to run
`python algo/algo_data_patrol.py` afterward.
"""

from unittest.mock import MagicMock, patch

from scripts.local_loader_scheduler import _run_data_patrol_and_report


class TestRunDataPatrolAndReport:
    def test_ready_returns_zero(self):
        mock_patrol = MagicMock()
        mock_patrol.run.return_value = {"ready": True, "findings": [], "errors": 0, "warnings": 2}
        with patch("algo.monitoring.data_patrol.DataPatrol", return_value=mock_patrol):
            code = _run_data_patrol_and_report()
        assert code == 0

    def test_not_ready_returns_one_and_lists_blocking_findings(self):
        mock_patrol = MagicMock()
        mock_patrol.run.return_value = {
            "ready": False,
            "errors": 2,
            "warnings": 1,
            "findings": [
                {"check": "staleness", "severity": "critical", "target": "price_daily", "message": "stale: 3d"},
                {
                    "check": "balance_sheet_identity",
                    "severity": "error",
                    "target": "annual_balance_sheet",
                    "message": "mismatch",
                },
                {"check": "coverage", "severity": "warn", "target": "stock_symbols", "message": "low coverage"},
            ],
        }
        with patch("algo.monitoring.data_patrol.DataPatrol", return_value=mock_patrol):
            code = _run_data_patrol_and_report()
        assert code == 1

    def test_patrol_itself_raising_returns_one_not_crash(self):
        with patch("algo.monitoring.data_patrol.DataPatrol", side_effect=RuntimeError("db down")):
            code = _run_data_patrol_and_report()
        assert code == 1
