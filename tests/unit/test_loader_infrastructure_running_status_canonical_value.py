"""Regression test for the 2026-08-10 fix: LoaderInfrastructure.update_loader_status()'s
docstring documents consolidating this writer onto the canonical LoaderStatus vocabulary
(RUNNING/COMPLETED/FAILED - utils/loaders/status_enum.py), replacing an old ad-hoc lowercase
vocabulary ('loading'/'ok'/'error'). The COMPLETED/FAILED/INCOMPLETE branch was actually
fixed to use the canonical values, but the RUNNING branch still hardcoded the literal string
"loading" instead of the `db_status` variable it computes (and ignores) one line above -
the exact "third vocabulary" the docstring claims was removed, for the one status value
(RUNNING) most other code queries for directly (see algo/monitoring/pipeline_health.py's
_check_stuck_loaders: `WHERE status = 'RUNNING'`, and orchestrator.py's proactive
critical-loader wait: `WHERE status = 'RUNNING' OR completion_pct < 90.0`) - a loader marked
running via this writer would never match either check, silently invisible to both the
stuck-loader safety net and the orchestrator's own critical-loader wait.

Fixed by using `db_status` (== "RUNNING" for this call) in both the UPDATE and the
fallback INSERT, matching the COMPLETED/FAILED/INCOMPLETE branch's existing pattern.
"""

from unittest.mock import MagicMock, patch

from utils.loader_infrastructure import LoaderInfrastructure


def _make_infra():
    infra = LoaderInfrastructure.__new__(LoaderInfrastructure)
    infra.table_name = "market_health_daily"
    return infra


class TestRunningStatusCanonicalValue:
    def test_running_status_writes_canonical_uppercase_value(self):
        infra = _make_infra()
        cur = MagicMock()
        cur.rowcount = 1

        with patch("utils.loader_infrastructure.DatabaseContext") as mock_ctx:
            mock_ctx.return_value.__enter__.return_value = cur
            infra.update_loader_status("RUNNING")

        update_call = next(
            call for call in cur.execute.call_args_list
            if len(call.args) > 1 and "UPDATE data_loader_status SET status" in call.args[0]
        )
        assert update_call.args[1] == ("RUNNING", "market_health_daily")

    def test_running_status_fallback_insert_writes_canonical_uppercase_value(self):
        """When no existing row is found (rowcount == 0), the fallback INSERT must also
        use the canonical value, not the old ad-hoc "loading" string."""
        infra = _make_infra()
        cur = MagicMock()
        cur.rowcount = 0

        with patch("utils.loader_infrastructure.DatabaseContext") as mock_ctx:
            mock_ctx.return_value.__enter__.return_value = cur
            infra.update_loader_status("RUNNING")

        insert_call = next(
            call for call in cur.execute.call_args_list
            if len(call.args) > 1 and "INSERT INTO data_loader_status" in call.args[0]
        )
        assert insert_call.args[1] == ("market_health_daily", "RUNNING")
