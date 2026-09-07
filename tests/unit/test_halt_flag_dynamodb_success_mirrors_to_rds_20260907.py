"""Regression test for a real-money-readiness audit finding: set_halt_flag/clear_halt_flag
only wrote to RDS's algo_runtime_state table on the DynamoDB-FAILURE fallback path. When
DynamoDB succeeded (the normal case - it's the store check_halt_flag/the orchestrator's real
trading gate treats as authoritative), RDS was never touched.

The dashboard/API (lambda/api/routes/algo_handlers/market/data_status.py) and TUI health panel
read algo_runtime_state in RDS directly, not DynamoDB - so a genuine halt could be actively
blocking new entries (correctly, via DynamoDB) while the dashboard kept showing "READY TO
TRADE" indefinitely, because algo_runtime_state.halt_flag was never set. Not a trading-safety
bug (the real gate still failed closed), but a real operator-visibility integrity bug for a
real-money system - a human relying on the dashboard during an incident would be misled.

Fix: best-effort mirror the successful DynamoDB write into RDS too, without affecting the
call's success/return value or raising on a mirror failure (DynamoDB already committed the
authoritative state).
"""

from datetime import datetime, timezone
from unittest.mock import MagicMock, patch

from algo.orchestration.halt_flag_manager import HaltFlagManager


def _manager() -> HaltFlagManager:
    return HaltFlagManager(alerts=MagicMock(), log_phase_result=MagicMock())


def _mock_dynamodb_table():
    table = MagicMock()
    table.update_item.return_value = {}
    table.get_item.return_value = {"Item": {"halt_count": 1, "triggered_at": datetime.now(timezone.utc).isoformat()}}
    table.put_item.return_value = {}
    return table


class TestSetHaltFlagMirrorsToRdsOnDynamoDbSuccess:
    def test_successful_dynamodb_set_still_writes_rds(self):
        manager = _manager()
        table = _mock_dynamodb_table()

        with (
            patch.dict("os.environ", {"AWS_ACCESS_KEY_ID": "fake", "LOCAL_MODE": "false"}, clear=False),
            patch("boto3.resource") as mock_resource,
            patch.object(manager, "_set_halt_flag_rds", return_value=True) as mock_rds_set,
            patch.object(manager, "_cancel_pending_entry_orders_on_halt"),
        ):
            mock_resource.return_value.Table.return_value = table

            result = manager.set_halt_flag(reason="test halt", triggered_by="phase2_circuit_breaker")

        assert result is True
        assert mock_rds_set.called, (
            "a halt that succeeded via DynamoDB must still mirror to RDS (best-effort) so the "
            "dashboard/API, which reads algo_runtime_state directly, doesn't show a stale "
            "'not halted' status while trading is genuinely halted."
        )

    def test_rds_mirror_failure_does_not_fail_the_halt(self):
        """A failure in the best-effort RDS mirror must not cause set_halt_flag to report
        failure or raise - DynamoDB already committed the authoritative halt."""
        manager = _manager()
        table = _mock_dynamodb_table()

        with (
            patch.dict("os.environ", {"AWS_ACCESS_KEY_ID": "fake", "LOCAL_MODE": "false"}, clear=False),
            patch("boto3.resource") as mock_resource,
            patch.object(manager, "_set_halt_flag_rds", side_effect=RuntimeError("RDS down")),
            patch.object(manager, "_cancel_pending_entry_orders_on_halt"),
        ):
            mock_resource.return_value.Table.return_value = table

            result = manager.set_halt_flag(reason="test halt", triggered_by="phase2_circuit_breaker")

        assert result is True, "DynamoDB-committed halt must still report success even if the RDS mirror fails"


class TestClearHaltFlagMirrorsToRdsOnDynamoDbSuccess:
    def test_successful_dynamodb_clear_still_writes_rds(self):
        manager = _manager()
        table = _mock_dynamodb_table()

        with (
            patch.dict("os.environ", {"AWS_ACCESS_KEY_ID": "fake", "LOCAL_MODE": "false"}, clear=False),
            patch("boto3.resource") as mock_resource,
            patch.object(manager, "_clear_halt_flag_rds", return_value=True) as mock_rds_clear,
        ):
            mock_resource.return_value.Table.return_value = table

            result = manager.clear_halt_flag(reason="verified fresh", force=True)

        assert result is True
        assert mock_rds_clear.called, (
            "a clear that succeeded via DynamoDB must still mirror to RDS so the dashboard "
            "doesn't keep showing a stale halted status."
        )

    def test_rds_mirror_failure_does_not_fail_the_clear(self):
        manager = _manager()
        table = _mock_dynamodb_table()

        with (
            patch.dict("os.environ", {"AWS_ACCESS_KEY_ID": "fake", "LOCAL_MODE": "false"}, clear=False),
            patch("boto3.resource") as mock_resource,
            patch.object(manager, "_clear_halt_flag_rds", side_effect=RuntimeError("RDS down")),
        ):
            mock_resource.return_value.Table.return_value = table

            result = manager.clear_halt_flag(reason="verified fresh", force=True)

        assert result is True, "DynamoDB-committed clear must still report success even if the RDS mirror fails"
