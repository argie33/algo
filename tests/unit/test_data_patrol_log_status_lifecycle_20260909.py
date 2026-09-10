"""Regression tests for PatrolLogger.log_results' status lifecycle (algo/monitoring/data_patrol/
logger.py).

Added 2026-09-09 (goal session: "is our XBRL/tie-out validation actually working"). `status` on
data_patrol_log was a dead column - live-verified 100% NULL across 7,208 rows, no code ever wrote
to it, oldest unresolved finding from 2026-06-27, the same ~77 (check_name, target_table) combos
re-logged on effectively every run since. This wires up a supersede-on-reinsert lifecycle: a
(check_name, target_table) firing again marks its prior 'open' row(s) 'resolved' before the new
one is inserted as 'open', so `status = 'open'` always reflects only the latest run's state
instead of an ever-growing unfiltered feed.
"""

from unittest.mock import MagicMock

from algo.monitoring.data_patrol.base import CheckResult
from algo.monitoring.data_patrol.config import WARN
from algo.monitoring.data_patrol.logger import PatrolLogger


def test_no_results_does_nothing() -> None:
    cur = MagicMock()
    PatrolLogger("run-1").log_results(cur, [])
    cur.executemany.assert_not_called()
    cur.execute.assert_not_called()


def test_supersedes_prior_open_rows_before_inserting() -> None:
    cur = MagicMock()
    finding = CheckResult(
        check_name="revenue_yoy_magnitude_jump",
        severity=WARN,
        target_table="annual_income_statement",
        message="60 symbol/year(s) show a swing",
    )
    PatrolLogger("run-2").log_results(cur, [finding])

    assert cur.executemany.call_count == 2
    resolve_sql, resolve_args = cur.executemany.call_args_list[0][0]
    assert "SET status = 'resolved'" in resolve_sql
    assert "WHERE status = 'open'" in resolve_sql
    assert resolve_args == [("revenue_yoy_magnitude_jump", "annual_income_statement")]

    insert_sql, insert_rows = cur.executemany.call_args_list[1][0]
    assert "'open'" in insert_sql
    assert "status" not in insert_rows[0]  # status is a literal in the SQL, not a bound param
    assert len(insert_rows[0]) == 6


def test_dedupes_resolve_keys_across_multiple_results_for_same_check() -> None:
    cur = MagicMock()
    findings = [
        CheckResult(check_name="net_income_yoy_magnitude_jump", severity=WARN, target_table="x", message="a"),
        CheckResult(check_name="net_income_yoy_magnitude_jump", severity=WARN, target_table="x", message="b"),
    ]
    PatrolLogger("run-3").log_results(cur, findings)
    _, resolve_args = cur.executemany.call_args_list[0][0]
    assert resolve_args == [("net_income_yoy_magnitude_jump", "x")]
