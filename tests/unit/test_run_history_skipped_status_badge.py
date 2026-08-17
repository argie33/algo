"""Regression test for the 2026-08-17 false-ERROR dashboard bug.

_build_run_history_section() reimplemented its own status->badge mapping instead of using
the module's SUCCESS_STATES/HALTED_STATES/SKIPPED_STATES/ERROR_STATES constants, and its
local version never recognized "skipped" or "blocked" - both fell into the else clause and
rendered as a red ERROR badge. Live-reproduced via run_id
LOCAL-MORNING-20260814-120000-000000: overall_status="skipped" (the outside-market-hours
guard working as designed, not a crash) rendered identically to a genuine phase failure.
"""

from rich.text import Text

from dashboard.panels.health import _build_run_history_section


def _render_status(status: str) -> str:
    run = {
        "status": status,
        "started_at": "2026-08-16T13:59:28",
        "completed_at": "2026-08-16T13:59:42",
        "halt_reason": "outside_market_hours: 18:34:44 ET",
        "phase_summary": {},
    }
    rows = _build_run_history_section([run])
    # rows[0] is the Rule separator, rows[1] is the header, rows[2] is the run line
    run_line = rows[2]
    assert isinstance(run_line, Text)
    return run_line.plain


class TestRunHistorySkippedStatusBadge:
    def test_skipped_status_is_not_rendered_as_error(self) -> None:
        line = _render_status("skipped")
        assert "SKIPPED" in line
        assert "ERROR" not in line

    def test_blocked_status_is_not_rendered_as_error(self) -> None:
        line = _render_status("blocked")
        assert "SKIPPED" in line
        assert "ERROR" not in line

    def test_genuine_error_status_still_renders_as_error(self) -> None:
        line = _render_status("error")
        assert "ERROR" in line

    def test_success_status_renders_as_ok(self) -> None:
        line = _render_status("success")
        assert "OK" in line
