#!/usr/bin/env python3
"""Regression test for phase9_reconciliation._generate_daily_report's audit-log persistence.

Live-reproduced 2026-08-10: a full local orchestrator run (all 8 other phases completed
normally, reconciliation itself succeeded) still ended with overall status FAILED. Root
cause: DailyFinanceReport.generate()'s sub-fetchers (_fetch_risk/_fetch_strategy/
_fetch_components/etc) return raw date/datetime values from DB rows without str()
conversion, and json.dumps(report) - used to persist the report to algo_audit_log - raised
TypeError: Object of type date is not JSON serializable. That TypeError isn't a
psycopg2.DatabaseError/OperationalError/RuntimeError, so it wasn't caught by the
surrounding except clause; it propagated uncaught out of Phase 9, marking the entire
orchestrator run failed and skipping the audit log INSERT entirely - on every run that
happened to include a raw date anywhere in the nested report structure.

Fixed with json.dumps(report, default=str) - the standard safe fallback for an archival
JSON text column.
"""

from datetime import date
from unittest.mock import MagicMock, patch

from algo.orchestrator.phase9_reconciliation import _generate_daily_report


def _report_with_nested_date():
    return {
        "date": "2026-08-10",
        "portfolio": {"current_value": 71520.03, "daily_pnl_pct": 0.42},
        # Mirrors the real bug: a sub-fetcher returning a raw, un-stringified date object
        # nested inside the report (e.g. a risk-metrics "as_of" field straight from a DB row).
        "risk": {"as_of": date(2026, 8, 10)},
    }


def test_nested_date_object_does_not_crash_audit_log_persistence():
    write_cur = MagicMock()
    write_cur.execute.return_value = None

    fake_report_instance = MagicMock()
    fake_report_instance.generate.return_value = _report_with_nested_date()
    fake_report_instance.format_text.return_value = "fake report text"

    logged = []

    def fake_log(*args, **kwargs):
        logged.append((args, kwargs))

    with (
        patch("algo.reporting.DailyFinanceReport", return_value=fake_report_instance),
        patch("algo.orchestrator.phase9_reconciliation.DatabaseContext") as mock_ctx,
        patch("algo.orchestrator.phase9_reconciliation.acquire_advisory_lock"),
        patch("algo.orchestrator.phase9_reconciliation.release_advisory_lock"),
    ):
        mock_ctx.return_value.__enter__.return_value = write_cur
        mock_ctx.return_value.__exit__.return_value = False

        # Must not raise - this is the exact live-reproduced crash.
        _generate_daily_report(run_date=date(2026, 8, 10), log_phase_result_fn=fake_log)

    insert_call = next(c for c in write_cur.execute.call_args_list if "INSERT INTO algo_audit_log" in c.args[0])
    persisted_json = insert_call.args[1][3]
    assert "2026-08-10" in persisted_json, "the nested date must be stringified, not dropped"

    # A "success" result must actually be reported for this phase, not silently skipped.
    assert any(args[2] == "success" for args, _kwargs in logged if len(args) > 2)
