"""Regression test: mark_completed()'s completion_pct must never exceed 100%.

Bug found 2026-08-10 via live DB evidence: buy_sell_daily's data_loader_status row showed
completion_pct=102.43% (symbols_loaded=4884, symbol_count=4768). loaders/load_buy_sell_daily.py
computes symbols_loaded from a universe-wide "symbols successfully processed" counter and
symbol_count from a same-date-scoped upstream price/technical-data availability count - two
not-strictly-nested populations, so the numerator can exceed the denominator. A completion
percentage over 100% is nonsensical wherever it's displayed (dashboards, the orchestrator's
proactive critical-loader-wait check in algo/orchestration/orchestrator.py). Fixed by clamping
actual_completion_pct at 100.0 in utils/loaders/status_manager.py.
"""

from unittest.mock import MagicMock, patch

from utils.loaders.status_manager import LoaderStatusManager


def _make_manager() -> LoaderStatusManager:
    with patch("utils.loaders.status_manager.DatabaseContext") as mock_db_ctx:
        mock_db_ctx.return_value.__enter__.return_value = MagicMock()
        mock_db_ctx.return_value.__exit__.return_value = False
        return LoaderStatusManager(table_name="buy_sell_daily")


def test_mark_completed_clamps_completion_pct_when_loaded_exceeds_total():
    manager = _make_manager()
    with patch("utils.loaders.status_manager.DatabaseContext") as mock_db_ctx:
        mock_cur = MagicMock()
        mock_db_ctx.return_value.__enter__.return_value = mock_cur
        mock_db_ctx.return_value.__exit__.return_value = False
        mock_cur.fetchone.side_effect = [
            (None, None, None, None, None, None, None),  # archive SELECT
        ]
        mock_cur.rowcount = 1

        # Mirrors the live bug: loaded (4884) exceeds total (4768) because they come from
        # different-scoped counts, not a true subset/superset relationship.
        manager.mark_completed(
            current_run_symbols_loaded=4884,
            current_run_symbol_count=4768,
            min_completion_pct=95.0,
        )

        update_call = None
        for call in mock_cur.execute.call_args_list:
            sql = call[0][0]
            if "UPDATE data_loader_status" in sql and "completion_pct" in sql:
                update_call = call
                break

        assert update_call is not None, "UPDATE query not found in execute calls"
        params = update_call[0][1]
        completion_pct_value = params[1]
        assert completion_pct_value == 100.0, f"completion_pct must be clamped at 100.0, got {completion_pct_value}"
