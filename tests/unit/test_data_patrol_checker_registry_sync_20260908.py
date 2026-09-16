"""Regression guard (/goal session, score/tie-out/CI sanity sweep): DataPatrol's checker
registry has already silently drifted out of sync three times - test_data_patrol_run_notify_
wired_20260901.py's own docstring documents ScoreRatioOutlierChecker/
CompositeScoreReconciliationChecker being missed, then XbrlConceptContinuityChecker being missed
again, each only caught because the unmocked checker happened to produce live findings against
a real on-disk cache during that specific test run - a checker that's silent on the mocked DB
connection (most of them) could be added to checks/__init__.py's __all__, forgotten in
DataPatrol.run()'s checkers list (base.py), and never actually execute in production, with
nothing failing to say so.

This asserts every checker exported from checks/__init__.py's __all__ is referenced in
DataPatrol.run()'s source - a cheap, structural guard against the exact silent-drop failure
mode that's already recurred twice, without needing to refactor the inline checker list into an
introspectable constant.
"""

import inspect

from algo.monitoring.data_patrol import checks
from algo.monitoring.data_patrol.base import DataPatrol


def test_every_exported_checker_is_registered_in_run() -> None:
    run_source = inspect.getsource(DataPatrol.run)
    missing = [name for name in checks.__all__ if name not in run_source]
    assert not missing, (
        f"checker(s) exported from checks/__init__.py's __all__ but never instantiated in "
        f"DataPatrol.run()'s checkers list: {missing} - they will never actually execute"
    )
