"""Regression test for the 2026-07-27 fix: get_run_details() called json.loads() on the
phase_results column, but that column is JSONB - psycopg2 already deserializes it to a
Python list before it ever reaches this code. json.loads(list) raises TypeError, which
isn't a json.JSONDecodeError, so the existing `except json.JSONDecodeError` didn't catch
it and the function crashed on every real row.

Live-reproduced 2026-07-27: calling get_run_details() on an actual completed orchestrator
run - the documented way to inspect phase-by-phase results per this module's own
docstring - raised "TypeError: the JSON object must be str, bytes or bytearray, not list"
instead of returning the run detail dict.

Fixed by using the already-deserialized value directly instead of re-parsing it.
"""

from unittest.mock import MagicMock, patch

from utils.ops.orchestrator_query import get_run_details


def _row_with_jsonb_phase_results():
    phase_results = [{"name": "entry_execution", "phase": "8", "status": "degraded"}]
    return (
        "LOCAL-MORNING-TEST",  # run_id
        None,  # run_date
        None,  # started_at
        None,  # completed_at
        "degraded",  # overall_status
        phase_results,  # phase_results - psycopg2 hands back a list, not a JSON string
        "1 trades executed, 2 failed",  # summary
        None,  # halt_reason
        9,  # phases_completed
        0,  # phases_halted
        0,  # phases_errored
    )


class TestGetRunDetailsHandlesPreDeserializedJsonb:
    def test_does_not_raise_on_list_valued_phase_results(self):
        cur = MagicMock()
        cur.fetchone.return_value = _row_with_jsonb_phase_results()

        class _Ctx:
            def __enter__(self):
                return cur

            def __exit__(self, *a):
                return False

        with patch("utils.ops.orchestrator_query.DatabaseContext", return_value=_Ctx()):
            details = get_run_details("LOCAL-MORNING-TEST")

        assert details["phase_results"] == [{"name": "entry_execution", "phase": "8", "status": "degraded"}]
