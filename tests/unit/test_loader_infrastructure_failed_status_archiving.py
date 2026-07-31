"""Regression test for the 2026-07-27 fix: LoaderInfrastructure.update_loader_status()'s
FAILED/COMPLETED path updated data_loader_status but never archived to
data_loader_status_history, the same gap already fixed for OptimalLoader's own raw-SQL
writer (utils/optimal_loader.py). Since most loaders' FAILED runs go through this class
instead of OptimalLoader's writer, the dashboard's failure-pattern analysis
(dashboard/freshness_enhancements.py's enrich_health_item_with_failure_pattern) never saw
any FAILED-run history for them.

Fixed by adding the same SAVEPOINT-wrapped archive INSERT + 100-row retention DELETE.
"""

from unittest.mock import MagicMock, patch

from utils.loader_infrastructure import LoaderInfrastructure


def _make_infra():
    infra = LoaderInfrastructure.__new__(LoaderInfrastructure)
    infra.table_name = "price_daily"
    return infra


class TestFailedStatusArchiving:
    def test_failed_status_archives_to_history(self):
        infra = _make_infra()
        cur = MagicMock()
        cur.fetchone.return_value = (None, None, "connection timeout", 0, 0.0, 0, 500)

        with patch("utils.loader_infrastructure.DatabaseContext") as mock_ctx:
            mock_ctx.return_value.__enter__.return_value = cur
            infra.update_loader_status("FAILED")

        executed = [call.args[0] for call in cur.execute.call_args_list]
        assert any("SAVEPOINT archive_history" in sql for sql in executed)
        assert any("INSERT INTO data_loader_status_history" in sql for sql in executed)
        assert any("DELETE FROM data_loader_status_history" in sql for sql in executed)
        assert any("RELEASE SAVEPOINT archive_history" in sql for sql in executed)

    def test_archive_failure_rolls_back_savepoint_without_raising(self):
        infra = _make_infra()
        cur = MagicMock()

        def _execute(sql, *args, **kwargs):
            if "INSERT INTO data_loader_status_history" in sql:
                raise Exception("boom")

        cur.execute.side_effect = _execute

        with patch("utils.loader_infrastructure.DatabaseContext") as mock_ctx:
            mock_ctx.return_value.__enter__.return_value = cur
            infra.update_loader_status("FAILED")  # must not raise

        executed = [call.args[0] for call in cur.execute.call_args_list]
        assert any("ROLLBACK TO SAVEPOINT archive_history" in sql for sql in executed)
        # the real status UPDATE (issued before the archive block) must still have happened
        assert any("UPDATE data_loader_status SET status" in sql for sql in executed)
