"""Regression test for dashboard/watch/manager.py::should_start_reload().

dashboard.py's run_watch() combines two independent reload triggers each tick:
should_reload (interval elapsed, already excludes an in-flight reload via is_loading) and
should_retry_load (recovery-triggered retry after a transient render failure, computed
from RenderRecovery's own error/retry state with no knowledge of is_loading at all).

Before this fix, the code did `if should_reload or should_retry_load:` with no is_loading
check on the combined expression - so a retry firing while an interval-triggered reload was
already running (is_loading=True) spawned a SECOND concurrent reload thread. Both threads
write WatchState.result independently with no ordering guarantee; whichever finishes last
wins. If that's the older/slower of the two, it silently overwrites fresher data with stale
data - the opposite of this codebase's explicit "never silently preserve stale data"
governance for a finance app.
"""

from dashboard.watch.manager import should_start_reload


class TestShouldStartReload:
    def test_does_not_start_second_reload_while_one_is_in_flight(self):
        # The exact bug: a retry trigger fires mid-reload. Must NOT start a second thread.
        assert should_start_reload(should_reload=False, should_retry_load=True, is_loading=True) is False

    def test_does_not_start_reload_when_interval_trigger_fires_mid_reload(self):
        # should_reload() itself already guards this, but the combining logic must respect it too.
        assert should_start_reload(should_reload=True, should_retry_load=False, is_loading=True) is False

    def test_starts_reload_on_interval_trigger_when_idle(self):
        assert should_start_reload(should_reload=True, should_retry_load=False, is_loading=False) is True

    def test_starts_reload_on_retry_trigger_when_idle(self):
        assert should_start_reload(should_reload=False, should_retry_load=True, is_loading=False) is True

    def test_no_reload_when_neither_trigger_fires(self):
        assert should_start_reload(should_reload=False, should_retry_load=False, is_loading=False) is False

    def test_no_reload_when_both_triggers_fire_but_already_loading(self):
        assert should_start_reload(should_reload=True, should_retry_load=True, is_loading=True) is False
