"""Regression test: Orchestrator._wait_for_critical_loaders_proactive()'s SQL filter must
compare status against the actual uppercase value the system writes, not lowercase.

Bug found 2026-08-10 via live DB evidence: `SELECT DISTINCT status FROM data_loader_status`
returns only uppercase values (RUNNING, COMPLETED, TIMEOUT, ...) - every write goes through
utils/loaders/status_manager.py using LoaderStatus.RUNNING.value == "RUNNING". But the
proactive-wait query filtered on `status = 'running'` (lowercase). Postgres string equality
is case-sensitive by default, so that half of the `(status = 'running' OR completion_pct <
90.0)` OR condition could never match a single row - silently narrowing the safety check to
completion_pct alone. Live-reproduced: a crashed mid-run left quality_metrics and
growth_metrics (both critical loaders) at status='RUNNING' with completion_pct 95.57% and
94.00% (both >= 90) - a genuinely stuck-mid-run critical loader that neither half of the
original condition would have caught.
"""

import ast
import re
from pathlib import Path

REPO_ROOT = Path(__file__).resolve().parents[2]
SOURCE = REPO_ROOT / "algo" / "orchestration" / "orchestrator.py"


def _find_method_source(name: str) -> str:
    tree = ast.parse(SOURCE.read_text(encoding="utf-8"))
    for node in ast.walk(tree):
        if isinstance(node, ast.FunctionDef) and node.name == name:
            return ast.unparse(node)
    raise AssertionError(f"Method {name} not found in {SOURCE}")


def test_proactive_wait_query_matches_actual_uppercase_running_status():
    method_src = _find_method_source("_wait_for_critical_loaders_proactive")

    assert "status = 'running'" not in method_src, (
        "Lowercase 'running' never matches this table's actual values - every write goes "
        "through LoaderStatus.RUNNING.value == 'RUNNING'. This condition would silently "
        "never match, defeating the point of checking loader status here."
    )
    assert re.search(r"status\s*=\s*'RUNNING'", method_src), (
        "Expected the proactive-wait query to filter on the actual stored value 'RUNNING' "
        "(uppercase), matching LoaderStatus.RUNNING.value."
    )
