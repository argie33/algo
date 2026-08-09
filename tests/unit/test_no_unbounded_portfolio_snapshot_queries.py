"""Regression test: no query may fetch the "latest" algo_portfolio_snapshots row
without bounding snapshot_date against a caller-provided date.

Guards against the bug class fixed 2026-08-09 across circuit_breaker.py,
phase8_entry_execution.py, position_sizer.py, var.py, reconciliation.py, and
position_monitor.py: `SELECT ... FROM algo_portfolio_snapshots ORDER BY
snapshot_date DESC LIMIT N` with no WHERE clause happily returns a stray
future-dated row (e.g. a leftover local `--date` simulation snapshot in the
shared dev DB) ahead of the real current one, silently corrupting drawdown/
risk-halt checks and position sizing. Live-reproduced 2026-08-09: a leftover
2026-08-11 test snapshot outranked the real current run's own 2026-08-07
snapshot in six different call sites.

The correct fix is either `WHERE snapshot_date <= %s` bound to the caller's
run_date/current_date/reconcile_date, or `WHERE snapshot_date <= CURRENT_DATE`
when no such parameter is in scope - never an unbounded ORDER BY.
"""

import re
from pathlib import Path

REPO_ROOT = Path(__file__).resolve().parents[2]
ALGO_DIR = REPO_ROOT / "algo"

# Matches "FROM algo_portfolio_snapshots" optionally followed by a WHERE clause,
# then "ORDER BY snapshot_date DESC". Captures the WHERE clause (if any) so we can
# check it actually bounds snapshot_date.
_QUERY_PATTERN = re.compile(
    r"FROM\s+algo_portfolio_snapshots(?:\s*\n\s*)?(WHERE[^\n]*\n\s*)?ORDER BY snapshot_date DESC",
    re.IGNORECASE,
)
_BOUND_PATTERN = re.compile(r"snapshot_date\s*(<=|<|=)")


def _find_unbounded_queries():
    violations = []
    for path in ALGO_DIR.rglob("*.py"):
        text = path.read_text(encoding="utf-8")
        for match in _QUERY_PATTERN.finditer(text):
            where_clause = match.group(1) or ""
            if not _BOUND_PATTERN.search(where_clause):
                line = text[: match.start()].count("\n") + 1
                violations.append(f"{path.relative_to(REPO_ROOT)}:{line}")
    return violations


def test_no_unbounded_latest_snapshot_queries():
    violations = _find_unbounded_queries()
    assert not violations, (
        "Found unbounded 'latest portfolio snapshot' queries (missing "
        "snapshot_date <= bound) - see module docstring for the bug this guards "
        f"against:\n" + "\n".join(violations)
    )
