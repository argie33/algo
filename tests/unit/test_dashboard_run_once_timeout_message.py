"""Regression test: run_once() gave up silently when no data loaded within 30s.

Live(console=CONSOLE, screen=True) uses the terminal's alternate screen buffer, which is
cleared the moment the `with Live(...)` block exits - so the "[DASHBOARD] run_once() exiting
after 30s with no data" line (logger.info, not console output) never reached the user. Someone
running `python dashboard.py` against a down dev_server just saw a loading spinner and then
their normal prompt back, with zero indication the run failed rather than completed. Fixed by
printing a visible message via CONSOLE once the Live context has exited (so it survives the
screen-buffer restore) whenever the loop broke out via the 30s give-up path specifically -
not on a deliberate 'q' quit or the already-logged CRITICAL render-failure path.
"""

from unittest.mock import patch

from dashboard import dashboard


def _run_once_with_no_data():
    call_count = [0]

    def fake_monotonic() -> float:
        call_count[0] += 1
        return 0.0 if call_count[0] <= 2 else 100.0

    with (
        patch("dashboard.dashboard.load_all", side_effect=dict),
        patch("dashboard.dashboard.time.monotonic", side_effect=fake_monotonic),
        patch("dashboard.dashboard.time.sleep", return_value=None),
        patch("dashboard.dashboard._keypress", return_value=""),
        patch("dashboard.dashboard.Live"),
        patch.object(dashboard, "CONSOLE") as mock_console,
    ):
        dashboard.run_once(compact=False)

    return mock_console


def test_timeout_prints_visible_message_after_live_exits() -> None:
    mock_console = _run_once_with_no_data()

    printed = " ".join(str(call.args[0]) for call in mock_console.print.call_args_list if call.args)
    assert "30 seconds" in printed or "30s" in printed, (
        f"expected a visible timeout message on CONSOLE after run_once() gives up, got: {printed!r}"
    )


def test_quit_keypress_does_not_print_timeout_message() -> None:
    """A deliberate 'q' quit is not a timeout - must not print the give-up message."""
    with (
        patch("dashboard.dashboard.load_all", side_effect=dict),
        patch("dashboard.dashboard.time.sleep", return_value=None),
        patch("dashboard.dashboard._keypress", return_value="q"),
        patch("dashboard.dashboard.Live"),
        patch.object(dashboard, "CONSOLE") as mock_console,
    ):
        dashboard.run_once(compact=False)

    printed = " ".join(str(call.args[0]) for call in mock_console.print.call_args_list if call.args)
    assert "30" not in printed
