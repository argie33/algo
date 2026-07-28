"""Regression test for a reload-storm bug in dashboard.dashboard.run_watch()'s reload().

should_reload() fires when `time.monotonic() - last_load >= interval`. The success path and
the 20s-timeout path both advance `state.last_load` at the end of the try block. But a real
load_all() exception (a genuine error, not the timeout branch) was caught by the outer
`except Exception` and never advanced `state.last_load` - so once `interval` seconds had
elapsed since the last successful load, every subsequent failure left should_reload() true
forever. Combined with is_loading being reset to False right before the except block returns,
the very next 0.25s main-loop tick immediately spawns another reload thread - hammering the
backend with zero backoff for as long as the failure persists, instead of waiting a normal
`interval` between retries.

Fixed by also setting `state.last_load = time.monotonic()` in the except branch.
"""

import threading
from unittest.mock import patch

from dashboard import dashboard
from dashboard.watch.state import WatchState


def test_failed_reload_advances_last_load_so_retries_are_rate_limited() -> None:
    created_states = []

    class SpyWatchState(WatchState):
        def __init__(self) -> None:
            super().__init__()
            created_states.append(self)

    def failing_load_all():
        raise RuntimeError("simulated backend outage")

    def keypress_side_effect():
        # Stop the loop as soon as the reload thread's failure has been recorded.
        if created_states and created_states[0].error is not None:
            return "q"
        return ""

    with (
        patch("dashboard.dashboard.WatchState", side_effect=SpyWatchState),
        patch("dashboard.dashboard.load_all", side_effect=failing_load_all),
        patch("dashboard.dashboard._keypress", side_effect=keypress_side_effect),
        patch("dashboard.dashboard.Live"),
        patch("dashboard.dashboard.time.sleep", lambda _s: threading.Event().wait(0.01)),
    ):
        dashboard.run_watch(interval=30, compact=False)

    assert created_states, "expected run_watch to construct a WatchState"
    state = created_states[0]
    assert state.error is not None, "expected the simulated load_all() failure to be recorded"
    assert state.last_load > 0.0, (
        "state.last_load must advance on a genuine reload failure, not just on success/timeout - "
        "otherwise should_reload() stays true forever and the dashboard hammers the backend with "
        "no backoff for as long as the outage lasts"
    )


if __name__ == "__main__":
    import pytest

    pytest.main([__file__, "-v"])
