"""Regression test: Phase 8's per-signal failure branch must not raise KeyError when
trade_result has no "status" key.

Bug (found 2026-09-06, real-money-readiness audit): this branch used to do
`status = trade_result["status"]` (bare indexing). executor_entry_handler.py's
_validate_entry_phase returns error_details={} for several real validation failures
(missing stop_loss_price, NaN/Infinite entry or stop, stop <= 0, stop >= entry) - in
every one of those cases the returned dict has NO "status" key at all, only
"success"/"trade_id"/"message". Phase 8's outer per-signal exception handler does not
catch KeyError, so a validation failure of this shape would raise unhandled, terminating
the `for signal in qualified_trades` loop entirely and silently skipping every remaining
candidate in the run - a real violation of the "one bad signal must not abort the whole
run" contract this loop otherwise carefully maintains (see
test_phase8_duplicate_race_exception_handling.py for the sibling case this already
protects against).

Source inspection rather than a full mocked run: the surrounding loop has a large
dependency graph (matches this repo's existing precedent, e.g.
test_phase6_raise_stop_syncs_broker_before_write_20260824.py, for this exact file/class
of change).
"""

from pathlib import Path

REPO_ROOT = Path(__file__).resolve().parents[2]
SOURCE = (REPO_ROOT / "algo" / "orchestrator" / "phase8_entry_execution.py").read_text(encoding="utf-8")


def _failure_branch() -> str:
    marker = 'message = trade_result.get("message"'
    start = SOURCE.index("else:\n                            #", SOURCE.index("qualified_trades"))
    end = SOURCE.index(marker) + 400
    return SOURCE[start:end]


class TestTradeResultMissingStatusKeyNoKeyError:
    def test_status_read_via_get_not_bare_indexing(self):
        block = _failure_branch()
        assert 'trade_result["status"]' not in block, (
            "the failure branch must not bare-index trade_result for 'status' - "
            "executor_entry_handler.py's validation-failure return dict can omit this key "
            "entirely, and the outer exception handler does not catch KeyError."
        )
        assert 'trade_result.get("status"' in block

    def test_message_read_defensively_too(self):
        block = _failure_branch()
        assert 'trade_result["message"]' not in block
        assert 'trade_result.get("message"' in block
