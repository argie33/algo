"""Regression test: DailyReconciliation.run_daily_reconciliation()'s broker-connected code
path (self.broker is not None - only reached when execution_mode == "auto", i.e. real
trading) must return a dict containing "reason", same as the self.broker is None DB-fallback
path already does.

phase4_reconciliation.py::run() unconditionally requires "reason" on the returned dict
(raises RuntimeError if absent) for both success and failure. The self.broker is None
fallback path always includes it, and every paper-mode test run takes that path - execution_mode
!= "auto" forces self.broker to None in __init__ regardless of credential availability (see
reconciliation.py __init__). So a missing "reason" on the real broker-connected path was
invisible in every paper-mode run and would only surface the moment execution_mode switches
to "auto" for real trading, breaking Phase 4 on its very first successful reconciliation.

Fully mocking the DB call chain to drive run_daily_reconciliation() to completion through its
broker-connected branch would require reproducing ~40 sequential queries end to end, which is
too brittle to be a useful regression signal. Instead this asserts directly on the source: both
return statements in the self.broker is not None branch must have literal "reason" keys - this
targets the exact shape of the original bug and fails immediately if either return statement
drops the key again, regardless of how the surrounding logic is refactored.
"""

import ast
import inspect
import textwrap

from algo.infrastructure.reconciliation import DailyReconciliation


def _dict_return_statements_in_broker_connected_branch() -> list[ast.Dict]:
    source = textwrap.dedent(inspect.getsource(DailyReconciliation.run_daily_reconciliation))
    tree = ast.parse(source)
    func_def = tree.body[0]
    assert isinstance(func_def, ast.FunctionDef)

    # Locate the `if self.broker is None:` branch and only walk the *rest* of the function
    # body (the else-implicit broker-connected path) - the DB-fallback branch inside that
    # `if` already has "reason" and isn't what this test is protecting.
    broker_none_check_index = None
    for i, node in enumerate(func_def.body):
        if (
            isinstance(node, ast.If)
            and isinstance(node.test, ast.Compare)
            and isinstance(node.test.left, ast.Attribute)
            and node.test.left.attr == "broker"
        ):
            broker_none_check_index = i
            break
    assert broker_none_check_index is not None, (
        "Could not locate 'if self.broker is None:' in run_daily_reconciliation - "
        "the function may have been restructured; update this test's detection logic."
    )

    broker_connected_body = func_def.body[broker_none_check_index + 1 :]
    dict_returns = []
    for node in ast.walk(ast.Module(body=broker_connected_body, type_ignores=[])):
        if isinstance(node, ast.Return) and isinstance(node.value, ast.Dict):
            dict_returns.append(node.value)
    return dict_returns


def test_broker_connected_returns_all_have_reason_key():
    dict_returns = _dict_return_statements_in_broker_connected_branch()
    assert len(dict_returns) >= 2, (
        f"expected at least 2 dict-literal return statements (success + exception-handler "
        f"failure) in the broker-connected branch, found {len(dict_returns)} - "
        "confirm the function still has both paths before trusting this count."
    )

    for dict_node in dict_returns:
        keys = [k.value for k in dict_node.keys if isinstance(k, ast.Constant)]
        assert "reason" in keys, (
            f"a return statement in run_daily_reconciliation's broker-connected branch is "
            f"missing 'reason' (keys found: {keys}). phase4_reconciliation.py::run() requires "
            f"'reason' unconditionally and raises RuntimeError without it - this is invisible "
            f"in paper mode (self.broker is always None there) and would break Phase 4 the "
            f"moment execution_mode switches to 'auto' for real trading."
        )


if __name__ == "__main__":
    import pytest

    pytest.main([__file__, "-v"])
