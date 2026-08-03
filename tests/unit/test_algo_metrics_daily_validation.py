#!/usr/bin/env python3
"""Regression test: algo_metrics_daily must not fail-close on a valid low-audit-volume day.

fetch_global previously raised ValueError whenever entries+exits (counted from
algo_trades.entry_date/exit_date) exceeded total_actions (COUNT(*) of ALL
algo_audit_log rows for the day - circuit breaker checks, position monitor ticks,
reconciliation events, etc). These are two unrelated tables with no subset
relationship: entries in particular are never written to algo_audit_log at all
(only exits are, via executor_exit_handler.py). On a real day with several trade
entries but little other audit-log activity, entries+exits > total_actions is a
valid state, not evidence of bad data - the old check would have wrongly marked
the whole day's metrics data_unavailable.
"""

from datetime import date
from unittest.mock import MagicMock, patch

from loaders.load_algo_metrics_daily import AlgoMetricsDailyLoader


def _db_context_mock(audit_row, trade_row):
    mock_cur = MagicMock()
    mock_cur.fetchone.side_effect = [audit_row, trade_row]
    mock_ctx = MagicMock()
    mock_ctx.__enter__.return_value = mock_cur
    return mock_ctx


def test_entries_exceeding_total_actions_is_not_an_error():
    # total_actions=2 (light audit-log day), but 5 real entries happened -
    # entries are never audit-logged, so this is a legitimate combination.
    audit_row = (2, 75.0)  # total_actions, avg_signal_score
    trade_row = (5, 0)  # entries, exits

    loader = AlgoMetricsDailyLoader.__new__(AlgoMetricsDailyLoader)
    with patch(
        "loaders.load_algo_metrics_daily.DatabaseContext",
        return_value=_db_context_mock(audit_row, trade_row),
    ):
        rows = loader.fetch_global(since=None)

    assert len(rows) == 1
    row = rows[0]
    # CRITICAL FIX (2026-08-02): Loader consolidation - Phase 9 is exclusive writer
    # This loader verifies metrics but doesn't persist (returns data_unavailable=True with reason_type="not_applicable")
    # to prevent race conditions between Phase 9 orchestrator and scheduled loader
    assert row["data_unavailable"] is True, "Loader should report verification-only (not persisting)"
    assert row["reason"] == "metrics_written_by_phase9_orchestrator"
    assert row["reason_type"] == "not_applicable"


def test_normal_high_audit_volume_day_still_works():
    audit_row = (573, 82.5)
    trade_row = (12, 0)

    loader = AlgoMetricsDailyLoader.__new__(AlgoMetricsDailyLoader)
    with patch(
        "loaders.load_algo_metrics_daily.DatabaseContext",
        return_value=_db_context_mock(audit_row, trade_row),
    ):
        rows = loader.fetch_global(since=None)

    # CRITICAL FIX (2026-08-02): Loader consolidation - Phase 9 is exclusive writer
    assert rows[0]["data_unavailable"] is True, "Loader should report verification-only (not persisting)"
    assert rows[0]["reason"] == "metrics_written_by_phase9_orchestrator"
